"""
Google sign-in using the OAuth Authorization Code flow with PKCE.
Redirect-based, so the site loads no Google script and the CSP stays strict.
Google sign-ups are always tourists; merchants still apply through the KYC form.
"""
import base64
import binascii
import hashlib
import json
import logging
import secrets
import time
from urllib.parse import urlencode, urlparse

import requests
from django.conf import settings
from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils.crypto import constant_time_compare
from django.utils.translation import gettext as _

from apps.accounts.models import User, UserRoles
from apps.accounts.services import email_verification_service

logger = logging.getLogger(__name__)

AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
VALID_ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
TOKEN_REQUEST_TIMEOUT_SECONDS = 10


class GoogleAuthError(Exception):
    """Sign-in was refused; the message is safe to show to the user."""


def _client_id() -> str:
    return settings.GOOGLE_OAUTH_CLIENT_IDS.split(",")[0].strip()


def _redirect_uri() -> str:
    # From settings, not the Host header, and must match the Google Console entry exactly
    return settings.SITE_URL.rstrip("/") + reverse("accounts:google_callback")


def is_enabled() -> bool:
    return bool(_client_id() and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def canonical_login_url(request) -> str | None:
    """
    Google always returns to SITE_URL, and the flow lives in a host-only session cookie.
    A visitor starting on another host (www) must move first, or the callback finds no flow.
    """
    site = urlparse(settings.SITE_URL)
    if request.get_host() == site.netloc:
        return None
    return f"{site.scheme}://{site.netloc}{request.get_full_path()}"


def begin_login() -> tuple[str, dict]:
    """Return Google's consent URL and the values the callback must check."""
    flow = {
        "state": secrets.token_urlsafe(32),
        "nonce": secrets.token_urlsafe(32),
        "code_verifier": secrets.token_urlsafe(64),
    }
    challenge = base64.urlsafe_b64encode(
        hashlib.sha256(flow["code_verifier"].encode()).digest()
    ).rstrip(b"=").decode()
    query = urlencode({
        "client_id": _client_id(),
        "redirect_uri": _redirect_uri(),
        "response_type": "code",
        "scope": "openid email profile",
        "state": flow["state"],
        "nonce": flow["nonce"],
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "prompt": "select_account",
    })
    return f"{AUTHORIZATION_URL}?{query}", flow


def _decode_id_token_claims(id_token: str) -> dict:
    # The token comes straight from Google over TLS, so OIDC allows skipping the signature check
    try:
        payload = id_token.split(".")[1]
        padded = payload + "=" * (-len(payload) % 4)
        claims = json.loads(base64.urlsafe_b64decode(padded))
    except (IndexError, ValueError, binascii.Error) as exc:
        raise GoogleAuthError(_("เข้าสู่ระบบด้วย Google ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")) from exc
    if not isinstance(claims, dict):
        raise GoogleAuthError(_("เข้าสู่ระบบด้วย Google ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"))
    return claims


def fetch_identity(code: str, flow: dict) -> dict:
    """Exchange the one-time code for the user's validated identity claims."""
    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": _client_id(),
                "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
                "redirect_uri": _redirect_uri(),
                "grant_type": "authorization_code",
                "code_verifier": flow["code_verifier"],
            },
            timeout=TOKEN_REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        id_token = response.json()["id_token"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        logger.error("Google token exchange failed: %s", type(exc).__name__)
        raise GoogleAuthError(_("เข้าสู่ระบบด้วย Google ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")) from exc

    claims = _decode_id_token_claims(id_token)
    is_valid = (
        claims.get("iss") in VALID_ISSUERS
        and claims.get("aud") == _client_id()
        and isinstance(claims.get("exp"), (int, float))
        and claims["exp"] > time.time()
        and constant_time_compare(str(claims.get("nonce", "")), flow["nonce"])
        and claims.get("sub")
        and claims.get("email")
    )
    if not is_valid:
        logger.warning("Rejected a Google ID token with invalid claims")
        raise GoogleAuthError(_("เข้าสู่ระบบด้วย Google ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง"))
    if claims.get("email_verified") is not True:
        raise GoogleAuthError(_("อีเมลของบัญชี Google นี้ยังไม่ได้รับการยืนยัน"))
    return claims


def _create_user(claims: dict, email: str) -> User:
    try:
        with transaction.atomic():
            return User.objects.create_user(
                email=email,
                first_name=str(claims.get("given_name", ""))[:150],
                last_name=str(claims.get("family_name", ""))[:150],
                role=UserRoles.TOURIST,
                email_verified=True,
                google_sub=claims["sub"],
            )
    except IntegrityError as exc:
        # Two sign-ins raced for the same email
        raise GoogleAuthError(_("เข้าสู่ระบบด้วย Google ไม่สำเร็จ กรุณาลองใหม่อีกครั้ง")) from exc


def _link_existing_user(user: User, sub: str) -> None:
    user.google_sub = sub
    if user.needs_email_verification:
        # Whoever set this password never proved they own the email. Google just proved
        # the real owner is here, so a pre-registered password must not survive.
        user.set_unusable_password()
        user.save(update_fields=["google_sub", "password"])
        email_verification_service.mark_email_verified(user)
    elif not user.email_verified and not user.is_merchant:
        user.email_verified = True
        user.save(update_fields=["google_sub", "email_verified"])
    else:
        # Legacy merchants stay unverified: that flag keeps them in the KYC queue
        user.save(update_fields=["google_sub"])


def get_or_create_user(claims: dict) -> tuple[User, bool]:
    """Match by Google's stable ID, then by email. Returns (user, created)."""
    sub = claims["sub"]
    email = claims["email"].strip().lower()

    user = User.objects.filter(google_sub=sub).first()
    needs_link = False
    if user is None:
        user = User.objects.filter(email=email).first()
        if user is None:
            return _create_user(claims, email), True
        if user.google_sub:
            raise GoogleAuthError(_("อีเมลนี้เชื่อมกับบัญชี Google อื่นอยู่แล้ว"))
        needs_link = True

    if not user.is_active:
        raise GoogleAuthError(_("บัญชีนี้ถูกระงับการใช้งาน กรุณาติดต่อผู้ดูแลระบบ"))
    if user.is_staff or user.is_community_admin:
        raise GoogleAuthError(_("บัญชีผู้ดูแลระบบต้องเข้าสู่ระบบด้วยรหัสผ่าน"))

    if needs_link:
        _link_existing_user(user, sub)
    return user, False
