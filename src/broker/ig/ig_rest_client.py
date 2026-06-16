import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .models import IGSession


class IGAPIError(RuntimeError):
    pass


class IGAuthenticationError(IGAPIError):
    def __init__(self, message: str, status_code: int | None = None,
                 error_code: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class IGRateLimitError(IGAPIError):
    pass


def request_json(url: str, method: str, headers: dict, payload: dict | None = None,
                 opener=urlopen) -> tuple[dict, dict]:
    body = json.dumps(payload).encode() if payload is not None else None
    request = Request(url, data=body, method=method, headers=headers)
    try:
        with opener(request, timeout=30) as response:
            content = response.read()
            return (json.loads(content) if content else {}), dict(response.headers.items())
    except HTTPError as exc:
        content = exc.read().decode(errors="replace")
        if exc.code == 429 or "allowance" in content.lower():
            raise IGRateLimitError(f"IG rate limit reached ({exc.code}): {content[:300]}") from exc
        if exc.code in {401, 403}:
            try:
                error_code = json.loads(content).get("errorCode")
            except (json.JSONDecodeError, AttributeError):
                error_code = None
            detail = f": {error_code}" if error_code else ""
            raise IGAuthenticationError(
                f"IG authentication failed ({exc.code}){detail}",
                status_code=exc.code,
                error_code=error_code,
            ) from exc
        raise IGAPIError(f"IG REST error ({exc.code}): {content[:300]}") from exc
    except URLError as exc:
        raise IGAPIError(f"IG REST connection failed: {exc.reason}") from exc


class IGRestClient:
    def __init__(self, config, session: IGSession, opener=urlopen):
        self.config, self.session, self.opener = config, session, opener

    def _headers(self, version: int = 1) -> dict:
        return {
            "X-IG-API-KEY": self.config.api_key, "CST": self.session.cst,
            "X-SECURITY-TOKEN": self.session.security_token,
            "Content-Type": "application/json", "Accept": "application/json; charset=UTF-8",
            "Version": str(version),
        }

    def _get(self, path: str, version: int = 1, query: dict | None = None) -> dict:
        suffix = f"?{urlencode(query)}" if query else ""
        try:
            return request_json(
                f"{self.config.rest_base_url}{path}{suffix}", "GET", self._headers(version),
                opener=self.opener,
            )[0]
        except IGAuthenticationError:
            from .ig_auth import create_session
            from .token_store import save_session
            self.session = create_session(self.config, self.opener)
            if self.config.token_cache_enabled:
                save_session(self.session, self.config.token_cache_path)
            return request_json(
                f"{self.config.rest_base_url}{path}{suffix}", "GET", self._headers(version),
                opener=self.opener,
            )[0]

    def _post(self, path: str, payload: dict, version: int = 1) -> dict:
        return request_json(
            f"{self.config.rest_base_url}{path}", "POST", self._headers(version), payload,
            opener=self.opener,
        )[0]

    def get_accounts(self):
        return self._get("/accounts", 1)

    def get_session_details(self):
        return self._get("/session", 1, {"fetchSessionTokens": "false"})

    def search_markets(self, search_term: str):
        return self._get("/markets", 1, {"searchTerm": search_term})

    def get_market(self, epic: str):
        return self._get(f"/markets/{epic}", 3)

    def get_open_positions(self):
        return self._get("/positions", 2)

    def get_position(self, deal_id: str):
        return self._get(f"/positions/{deal_id}", 2)

    def get_confirms(self, deal_reference: str):
        return self._get(f"/confirms/{deal_reference}", 1)

    def get_historical_prices(self, epic: str, resolution: str, num_points: int):
        return self._get(f"/prices/{epic}/{resolution}/{num_points}", 2)

    def create_demo_position(self, payload: dict):
        if self.config.env != "DEMO" or self.config.acc_type != "DEMO":
            raise ValueError("Position creation is restricted to IG DEMO")
        if not self.config.order_execution_enabled or self.config.dry_run_only:
            raise ValueError("IG DEMO order execution is not enabled")
        return self._post("/positions/otc", payload, 2)

    def close(self):
        request_json(
            f"{self.config.rest_base_url}/session", "DELETE", self._headers(1),
            opener=self.opener,
        )
