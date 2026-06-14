import json
from datetime import datetime
from pathlib import Path

from .models import IGSession


def save_session(session: IGSession, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "cst": session.cst, "security_token": session.security_token,
        "account_id": session.account_id, "lightstreamer_endpoint": session.lightstreamer_endpoint,
        "created_at": session.created_at.isoformat(),
        "expires_at": session.expires_at.isoformat() if session.expires_at else None,
    }))
    path.chmod(0o600)


def load_session(path: str | Path) -> IGSession | None:
    path = Path(path)
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    return IGSession(
        cst=data["cst"], security_token=data["security_token"], account_id=data["account_id"],
        lightstreamer_endpoint=data["lightstreamer_endpoint"],
        created_at=datetime.fromisoformat(data["created_at"]),
        expires_at=datetime.fromisoformat(data["expires_at"]) if data.get("expires_at") else None,
    )


def delete_session(path: str | Path) -> None:
    Path(path).unlink(missing_ok=True)
