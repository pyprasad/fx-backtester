from .models import redact


SENSITIVE_KEYS = {
    "password", "api_key", "x-ig-api-key", "cst", "x-security-token",
    "security_token", "access_token", "refresh_token",
}


def redact_mapping(data: dict) -> dict:
    return {
        key: ("***" if key.lower() in SENSITIVE_KEYS else redact(value) if key.lower() == "account_id" else value)
        for key, value in data.items()
    }
