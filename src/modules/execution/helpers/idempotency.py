"""Request fingerprint: tells a replay (same key, same body) from a key reused for a new intent."""
import hashlib

from src.schemas.execution import ExecutionCreate


def request_hash(request: ExecutionCreate) -> str:
    return hashlib.sha256(request.model_dump_json().encode()).hexdigest()
