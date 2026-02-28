"""Simple obfuscation (XOR + base64) for storing the API key in the settings table."""

import base64
import hashlib
import socket

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from logger.models import Setting

SETTINGS_KEY = "anthropic_api_key"


def _derive_key() -> bytes:
    """Derive a repeatable obfuscation key from the hostname."""
    hostname = socket.gethostname()
    return hashlib.sha256(hostname.encode()).digest()


def _xor_bytes(data: bytes, key: bytes) -> bytes:
    return bytes(b ^ key[i % len(key)] for i, b in enumerate(data))


def _obfuscate(api_key: str) -> str:
    key = _derive_key()
    xored = _xor_bytes(api_key.encode(), key)
    return base64.b64encode(xored).decode()


def _deobfuscate(stored: str) -> str:
    key = _derive_key()
    xored = base64.b64decode(stored)
    return _xor_bytes(xored, key).decode()


async def save_api_key(api_key: str, db: AsyncSession) -> None:
    """Obfuscate and upsert the API key into settings."""
    obfuscated = _obfuscate(api_key)
    result = await db.execute(select(Setting).where(Setting.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()
    if setting:
        setting.value = obfuscated
    else:
        db.add(Setting(key=SETTINGS_KEY, value=obfuscated))
    await db.commit()


async def get_api_key(db: AsyncSession) -> str | None:
    """Deobfuscate and return the stored API key, or None."""
    result = await db.execute(select(Setting).where(Setting.key == SETTINGS_KEY))
    setting = result.scalar_one_or_none()
    if not setting:
        return None
    try:
        return _deobfuscate(setting.value)
    except Exception:
        return None


async def has_api_key(db: AsyncSession) -> bool:
    """Check whether an API key is stored."""
    result = await db.execute(select(Setting).where(Setting.key == SETTINGS_KEY))
    return result.scalar_one_or_none() is not None
