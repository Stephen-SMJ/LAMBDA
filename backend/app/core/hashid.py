"""Hash ID encoding/decoding for conversation IDs."""

from hashids import Hashids

SALT = "lambda-conversation-hash-2024"
MIN_LENGTH = 8

_hashids = Hashids(salt=SALT, min_length=MIN_LENGTH)


def encode_id(id: int) -> str:
    """Encode an integer ID to a short hash string."""
    return _hashids.encode(id)


def decode_id(hash_id: str) -> int | None:
    """Decode a hash string back to an integer ID."""
    try:
        decoded = _hashids.decode(hash_id)
        return decoded[0] if decoded else None
    except Exception:
        return None
