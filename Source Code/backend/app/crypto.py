"""
At-rest encryption for credential data (Phase 5 security work).

Design: card UIDs are stored encrypted (Fernet — AES-128-CBC + HMAC-SHA256,
authenticated so tampering is detected, not just confidentiality) rather
than in plaintext. Because the ingestion path (MQTT event handler) and the
API both need to find "the credential with this UID" without decrypting
every row on every lookup, each credential also stores a keyed HMAC-SHA256
"blind index" of the UID. The index is deterministic (same UID -> same
index) so it supports equality lookup via a plain indexed column, but it
is not reversible on its own — an attacker with DB access but not the
index key cannot recover UIDs from it, and an attacker with only the
encryption key (not the index key) still can't correlate rows by UID
without decrypting them one at a time.

Fingerprint templates are never stored at all here — only a hash of the
template (`fp_template_hash`), consistent with the Phase 1 System Design
Document's schema and the Phase 2 firmware README's note that biometric
matching happens on the sensor module itself.
"""
from __future__ import annotations

import base64
import hashlib
import hmac

from cryptography.fernet import Fernet, InvalidToken

from .config import settings


def _dev_fallback_key(seed: str) -> bytes:
    # Deterministic per-process dev fallback so repeated test runs and a
    # single dev session behave consistently, without ever being mistaken
    # for a real secret (it's derived from a fixed string, not random).
    digest = hashlib.sha256(seed.encode()).digest()
    return base64.urlsafe_b64encode(digest)


_ENC_KEY = settings.CREDENTIAL_ENCRYPTION_KEY.encode() if settings.CREDENTIAL_ENCRYPTION_KEY else _dev_fallback_key("dev-only-encryption-key")
_INDEX_KEY = settings.CREDENTIAL_INDEX_KEY.encode() if settings.CREDENTIAL_INDEX_KEY else _dev_fallback_key("dev-only-index-key")

_fernet = Fernet(_ENC_KEY)


def encrypt_uid(plain_uid: str) -> str:
    """Returns a Fernet token (base64 text, safe for a VARCHAR column)."""
    return _fernet.encrypt(plain_uid.encode()).decode()


def decrypt_uid(token: str) -> str | None:
    """Returns the plaintext UID, or None if the token is invalid/corrupt
    (e.g. wrong key, or tampered ciphertext) rather than raising — callers
    treat a None the same as "credential not found" instead of crashing."""
    try:
        return _fernet.decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def uid_index(plain_uid: str) -> str:
    """Deterministic keyed HMAC of the UID, used as an indexed lookup
    column. Not reversible without INDEX_KEY, and even with INDEX_KEY it
    only lets you test equality against a known candidate UID — it does
    not let you enumerate stored UIDs."""
    return hmac.new(_INDEX_KEY, plain_uid.encode(), hashlib.sha256).hexdigest()
