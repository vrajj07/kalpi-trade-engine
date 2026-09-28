"""Column types shared by the models."""
from sqlalchemy import Enum


def enum_column(cls: type) -> Enum:
    # Stored as VARCHAR + CHECK rather than a native Postgres ENUM: adding a member
    # does not need an ALTER TYPE.
    return Enum(cls, native_enum=False, length=20)
