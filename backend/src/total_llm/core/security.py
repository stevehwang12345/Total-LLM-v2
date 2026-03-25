from datetime import datetime, timedelta, timezone

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from total_llm.core.config import get_settings

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(subject: str, expires_minutes: int | None = None) -> str:
    settings = get_settings()
    auth = settings.model_dump()["auth"]
    minutes = expires_minutes or int(auth["expire_minutes"])
    payload = {
        "sub": subject,
        "exp": datetime.now(timezone.utc) + timedelta(minutes=minutes),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, str(auth["jwt_secret"]), algorithm=str(auth["algorithm"]))


def verify_token(token: str) -> dict:
    settings = get_settings()
    auth = settings.model_dump()["auth"]
    try:
        return jwt.decode(token, str(auth["jwt_secret"]), algorithms=[str(auth["algorithm"])])
    except JWTError as exc:
        raise ValueError("Invalid token") from exc


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict | None:
    if credentials is None:
        return None
    try:
        payload = verify_token(credentials.credentials)
    except ValueError:
        return None
    request.state.current_user = payload
    return payload
