"""
BCH address generation for RAMEN users.

Uses bitcash library to generate deterministic addresses for each user.
These addresses will be used for eventual CashToken distribution.
"""
from bitcash import PrivateKey
from django.conf import settings
import hashlib
import logging

logger = logging.getLogger(__name__)


def generate_bch_address(user_id: int) -> str:
    """
    Generate a deterministic BCH address for a user.

    Uses RAMEN_SALT + user_id to derive a unique, reproducible address.
    The same user_id will always generate the same address.

    Args:
        user_id: The database ID of the user

    Returns:
        A BCH address in cashaddr format (bitcoincash:qp...)
    """
    # Create deterministic seed from salt + user_id
    salt = getattr(settings, 'RAMEN_SALT', 'default_salt_change_me')
    seed = f"{salt}:user:{user_id}".encode('utf-8')

    # Hash to get 32 bytes for private key
    private_key_bytes = hashlib.sha256(seed).digest()

    # Create key from raw bytes using the secret parameter
    key = PrivateKey.from_bytes(private_key_bytes)

    logger.info(f"Generated BCH address for user {user_id}: {key.address}")

    return key.address
