import hmac
import hashlib
import base64
import json
import time
import secrets
from typing import Optional, Tuple, Dict, Any
from fastapi import HTTPException, status, Header
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
    Enforces fail-closed validation: returns False if APP_PASSCODE is empty or unconfigured.
    """
    if not settings.APP_PASSCODE or not settings.APP_PASSCODE.strip() or not password:
        return False
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


# --- Brute Force & Rate Limiting Defense ---
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_DURATION_SECONDS = 900   # 15 minutes
ATTEMPT_WINDOW_SECONDS = 300     # 5 minutes

_ip_attempt_tracker: Dict[str, Dict[str, Any]] = {}


def check_rate_limit(client_ip: str) -> Tuple[bool, int]:
    """
    Checks if client IP is currently locked out.
    Returns (is_allowed, seconds_remaining_if_locked).
    """
    now = time.time()
    
    # Cleanup old entries periodically (more than 30 minutes old)
    if len(_ip_attempt_tracker) > 1000:
        stale_ips = [ip for ip, data in _ip_attempt_tracker.items() if now > data.get("locked_until", 0) + 1800]
        for ip in stale_ips:
            _ip_attempt_tracker.pop(ip, None)

    record = _ip_attempt_tracker.get(client_ip)
    if not record:
        return True, 0

    locked_until = record.get("locked_until", 0)
    if locked_until > now:
        return False, int(locked_until - now)

    # If lockout expired, clear record
    if locked_until > 0 and now >= locked_until:
        _ip_attempt_tracker.pop(client_ip, None)
        return True, 0

    # If attempt window expired without lockout, reset
    first_failed_at = record.get("first_failed_at", 0)
    if now - first_failed_at > ATTEMPT_WINDOW_SECONDS:
        _ip_attempt_tracker.pop(client_ip, None)
        return True, 0

    return True, 0


def record_failed_attempt(client_ip: str) -> Tuple[int, bool, int]:
    """
    Records a failed login attempt for the client IP.
    Returns (attempts_remaining, is_locked_now, lockout_seconds).
    """
    now = time.time()
    record = _ip_attempt_tracker.get(client_ip, {
        "count": 0,
        "first_failed_at": now,
        "locked_until": 0
    })

    # Reset if window expired
    if now - record.get("first_failed_at", now) > ATTEMPT_WINDOW_SECONDS:
        record["count"] = 0
        record["first_failed_at"] = now

    record["count"] += 1

    if record["count"] >= MAX_FAILED_ATTEMPTS:
        record["locked_until"] = now + LOCKOUT_DURATION_SECONDS
        _ip_attempt_tracker[client_ip] = record
        return 0, True, LOCKOUT_DURATION_SECONDS

    _ip_attempt_tracker[client_ip] = record
    attempts_remaining = max(0, MAX_FAILED_ATTEMPTS - record["count"])
    return attempts_remaining, False, 0


def record_successful_attempt(client_ip: str) -> None:
    """
    Resets failed attempt count upon successful authentication.
    """
    _ip_attempt_tracker.pop(client_ip, None)


def verify_app_passcode(authorization: Optional[str] = Header(None)) -> str:
    """
    Validates Authorization Bearer token header.
    Accepts valid HMAC-SHA256 session tokens (within 6h expiration)
    or direct APP_PASSCODE matching (fallback).
    Enforces fail-closed passcode validation.
    """
    if not settings.APP_PASSCODE or not settings.APP_PASSCODE.strip():
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server passcode unconfigured.",
        )
        
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or malformed Authorization Bearer header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = authorization.split("Bearer ")[1].strip()
    
    # 1. Check if token is a valid signed session token
    session_payload = verify_session_token(token)
    if session_payload is not None:
        return session_payload.get("sub", "quant-user")

    # 2. Check direct master password match using constant-time comparison (fallback for scripts / tooling)
    if secrets.compare_digest(token, settings.APP_PASSCODE.strip()) or validate_master_password(token):
        return "quant-master"
        
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Session expired or invalid passcode. Please unlock the app again.",
        headers={"WWW-Authenticate": "Bearer"},
    )


get_current_user = verify_app_passcode


