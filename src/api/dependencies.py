"""Request-scoped dependencies shared by the routers."""
from typing import Annotated

from fastapi import Header

UserId = Annotated[str, Header(
    alias="X-User-Id", min_length=1, max_length=64,
    description="The authenticated user, set by the upstream API gateway. This service trusts it and "
                "must not be exposed publicly: it is an internal service behind the gateway.")]
