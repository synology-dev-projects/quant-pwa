import hmac
import hashlib
import base64
import json
import time
import secrets
from typing import Optional, Tuple, Dict, Any
from app.config import settings


def _urlsafe_b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode('utf-8').rstrip('=')


def _urlsafe_b64decode(data: str) -> bytes:
    padding = '=' * (4 - (len(data) % 4)) if (len(data) % 4) != 0 else ''
    return base64.urlsafe_b64decode(data + padding)


def _get_signing_key() -> bytes:
    key_str = settings.SESSION_SECRET_KEY or settings.APP_PASSCODE or "quant-session-secret-key-fallback"
    return key_str.encode('utf-8')


def validate_master_password(password: str) -> bool:
    """
    Validates entered password against APP_PASSCODE using constant-time comparison.
    """
    if not settings.APP_PASSCODE:
        return True
    return secrets.compare_digest(password.strip(), settings.APP_PASSCODE.strip())


def create_session_token(expires_in_hours: Optional[int] = None) -> Tuple[str, int]:
    """
    Generates a cryptographically signed HMAC-SHA256 session token with expiration.
    Returns (token_string, expires_at_timestamp).
    """
    hours = expires_in_hours if expires_in_hours is not None else settings.SESSION_EXPIRY_HOURS
    now = int(time.time())
    expires_at = now + (hours * 3600)

    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": "quant-user",
        "iat": now,
        "exp": expires_at,
        "jti": secrets.token_hex(8)
    }

    header_b64 = _urlsafe_b64encode(json.dumps(header, separators=(',', ':')).encode('utf-8'))
    payload_b64 = _urlsafe_b64encode(json.dumps(payload, separators=(',', ':')).encode('utf-8'))
    
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(_get_signing_key(), signing_input, hashlib.sha256).digest()
    signature_b64 = _urlsafe_b64encode(signature)

    token = f"{header_b64}.{payload_b64}.{signature_b64}"
    return token, expires_at


def verify_session_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies token signature and checks if expiration timestamp is valid.
    Returns payload dictionary if valid, None otherwise.
    """
    if not token or not isinstance(token, str):
        return None

    parts = token.split('.')
    if len(parts) != 3:
        return None

    header_b64, payload_b64, signature_b64 = parts

    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    expected_signature = hmac.new(_get_signing_key(), signing_input, hashlib.sha256).digest()
    expected_signature_b64 = _urlsafe_b64encode(expected_signature)

    if not secrets.compare_digest(signature_b64, expected_signature_b64):
        return None

    try:
        payload_bytes = _urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode('utf-8'))
        
        # Verify expiration
        exp = payload.get("exp")
        if not exp or not isinstance(exp, (int, float)):
            return None
            
        if time.time() > exp:
            return None  # Expired
            
        return payload
    except Exception:
        return None
