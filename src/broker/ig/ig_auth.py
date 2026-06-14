from datetime import datetime, timezone
from urllib.request import urlopen

from .ig_rest_client import request_json
from .models import IGSession


def create_session(config, opener=urlopen) -> IGSession:
    headers = {
        "X-IG-API-KEY": config.api_key, "Content-Type": "application/json",
        "Accept": "application/json; charset=UTF-8", "Version": str(config.session_version),
    }
    body, response_headers = request_json(
        f"{config.rest_base_url}/session", "POST", headers,
        {"identifier": config.username, "password": config.password},
        opener=opener,
    )
    cst = response_headers.get("CST") or response_headers.get("Cst")
    token = response_headers.get("X-SECURITY-TOKEN") or response_headers.get("X-Security-Token")
    if not cst or not token:
        raise RuntimeError("IG session response did not contain CST and X-SECURITY-TOKEN")
    return IGSession(
        cst=cst, security_token=token,
        account_id=body.get("currentAccountId") or config.account_id,
        lightstreamer_endpoint=body.get("lightstreamerEndpoint", ""),
        created_at=datetime.now(timezone.utc), raw_account_info=body,
    )


def refresh_or_recreate_session(config, existing: IGSession | None, opener=urlopen) -> IGSession:
    return existing if existing and existing.cst and existing.security_token else create_session(config, opener)


def logout(session: IGSession, config=None, opener=urlopen) -> None:
    if config is None:
        return
    from .ig_rest_client import IGRestClient
    IGRestClient(config, session, opener).close()
