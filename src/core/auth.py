"""Authentication: who the caller is.

The upstream API gateway authenticates the user and forwards their id in X-User-Id. This
service trusts that header, so it is internal only and must never be exposed publicly.

authenticate_request is applied to every protected router in api/__init__.py, so a new endpoint
is authenticated by default and opting out is explicit (health). Handlers that need the id take
a CurrentUser parameter: the same dependency, which FastAPI runs once per request.
Replacing the header with a verified token (a signed JWT) changes only this file.
"""
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import APIKeyHeader

from src.utils.exceptions import UnauthorizedError

MAX_USER_ID_LENGTH = 64  # the width of every user_id column

_user_header = APIKeyHeader(
    name="X-User-Id", auto_error=False, scheme_name="GatewayUser",
    description="The authenticated user, set by the upstream API gateway.",
)


async def authenticate_request(request: Request, user_id: str | None = Security(_user_header)) -> str:
    if not user_id or len(user_id) > MAX_USER_ID_LENGTH:
        raise UnauthorizedError("Missing or invalid X-User-Id header")
    request.state.user_id = user_id
    return user_id


CurrentUser = Annotated[str, Depends(authenticate_request)]
