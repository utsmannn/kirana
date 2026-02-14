import hashlib
import hmac
import secrets
from typing import Tuple


def generate_api_key() -> Tuple[str, str, str]:
    random_chars = secrets.token_urlsafe(24).replace("-", "").replace("_", "")[:32]
    raw_key = f"kir_{random_chars}"
    prefix = raw_key[:8]
    hashed_key = hashlib.sha256(raw_key.encode()).hexdigest()
    return raw_key, hashed_key, prefix

def verify_api_key(raw_key: str, hashed_key: str) -> bool:
    computed = hashlib.sha256(raw_key.encode()).hexdigest()
    return hmac.compare_digest(computed, hashed_key)
