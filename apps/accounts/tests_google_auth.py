import base64
import json
import time
from unittest import mock
from urllib.parse import parse_qs, urlparse

import requests
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import AuditLog, MerchantProfile, User, UserRoles
from apps.accounts.services import google_auth_service

PASSWORD = "Str0ng-Pass!word"
CLIENT_ID = "123-test.apps.googleusercontent.com"
TOKEN_POST = "apps.accounts.services.google_auth_service.requests.post"


def id_token_for(**claims):
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    return f"header.{payload}.signature"


@override_settings(
    GOOGLE_OAUTH_CLIENT_IDS=CLIENT_ID,
    GOOGLE_OAUTH_CLIENT_SECRET="test-secret",
    SITE_URL="https://welltrip.test",
    ADMIN_EMAIL="admin@example.com",
)
class GoogleSignInTestCase(TestCase):
    def setUp(self):
        # The per-IP rate limit counts in the cache, which outlives each test's rollback
        cache.clear()
        self.client = self.client_class(headers={"host": "welltrip.test"})

    def start_flow(self, query=""):
        response = self.client.get(reverse("accounts:google_login") + query)
        self.assertEqual(response.status_code, 302)
        params = parse_qs(urlparse(response.url).query)
        return params["state"][0], params["nonce"][0]

    def sign_in(self, overrides=None, query="", **identity):
        """Run the whole flow with Google's token endpoint replaced by a canned answer."""
        state, nonce = self.start_flow(query)
        claims = {
            "iss": "https://accounts.google.com",
            "aud": CLIENT_ID,
            "exp": time.time() + 300,
            "nonce": nonce,
            "sub": "google-1",
            "email": "person@example.com",
            "email_verified": True,
            "given_name": "สมชาย",
            "family_name": "ใจดี",
            **identity,
            **(overrides or {}),
        }
        answer = mock.Mock()
        answer.json.return_value = {"id_token": id_token_for(**claims)}
        with mock.patch(TOKEN_POST, return_value=answer) as post:
            response = self.client.get(reverse("accounts:google_callback"), {"state": state, "code": "abc"})
        self.last_token_request = post.call_args
        return response

    def assertLoggedInAs(self, email):
        self.assertEqual(self.client.session.get("_auth_user_id"), str(User.objects.get(email=email).pk))

    def assertNotLoggedIn(self):
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_login_redirects_to_google_with_pkce_and_fixed_redirect_uri(self):
        response = self.client.get(reverse("accounts:google_login"))

        params = parse_qs(urlparse(response.url).query)
        self.assertTrue(response.url.startswith(google_auth_service.AUTHORIZATION_URL))
        self.assertEqual(params["client_id"], [CLIENT_ID])
        self.assertEqual(params["redirect_uri"], ["https://welltrip.test/accounts/google/callback/"])
        self.assertEqual(params["code_challenge_method"], ["S256"])

    def test_other_hosts_move_to_the_site_host_before_starting(self):
        response = self.client.get(
            reverse("accounts:google_login") + "?next=/bookings/cart/", headers={"host": "www.welltrip.test"}
        )

        self.assertEqual(
            response.url, "https://welltrip.test/accounts/google/login/?next=/bookings/cart/"
        )
        self.assertNotIn("google_oauth_flow", self.client.session)

    def test_new_user_becomes_verified_tourist_without_otp(self):
        response = self.sign_in()

        self.assertRedirects(response, reverse("core:home"))
        user = User.objects.get(email="person@example.com")
        self.assertLoggedInAs(user.email)
        self.assertEqual(user.role, UserRoles.TOURIST)
        self.assertTrue(user.email_verified)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(user.first_name, "สมชาย")
        self.assertEqual(mail.outbox, [])
        self.assertTrue(AuditLog.objects.filter(user=user, action="REGISTER_GOOGLE").exists())

    def test_token_request_carries_the_code_verifier_and_secret(self):
        self.sign_in()

        data = self.last_token_request.kwargs["data"]
        self.assertEqual(data["client_secret"], "test-secret")
        self.assertTrue(data["code_verifier"])
        self.assertEqual(data["redirect_uri"], "https://welltrip.test/accounts/google/callback/")

    def test_returning_user_matches_by_google_id_even_after_email_change(self):
        self.sign_in()
        self.client.logout()

        self.sign_in(email="renamed@example.com")

        self.assertLoggedInAs("person@example.com")
        self.assertEqual(User.objects.count(), 1)

    def test_verified_password_account_links_and_keeps_its_password(self):
        user = User.objects.create_user(email="person@example.com", password=PASSWORD, email_verified=True)

        self.sign_in()

        user.refresh_from_db()
        self.assertLoggedInAs(user.email)
        self.assertEqual(user.google_sub, "google-1")
        self.assertTrue(user.check_password(PASSWORD))

    def test_preregistered_unverified_account_loses_the_squatters_password(self):
        user = User.objects.create_user(
            email="person@example.com", password=PASSWORD, email_verification_required=True
        )

        self.sign_in()

        user.refresh_from_db()
        self.assertLoggedInAs(user.email)
        self.assertTrue(user.email_verified)
        self.assertFalse(user.has_usable_password())

    def test_unverified_merchant_verifies_and_alerts_admin(self):
        merchant = User.objects.create_user(
            email="person@example.com", password=PASSWORD, role=UserRoles.HOMESTAY_OWNER,
            email_verification_required=True,
        )
        MerchantProfile.objects.create(user=merchant, business_name="บ้านสวน")

        self.sign_in()

        self.assertEqual([m.to[0] for m in mail.outbox], ["admin@example.com"])

    def test_legacy_merchant_stays_in_the_kyc_queue(self):
        merchant = User.objects.create_user(
            email="person@example.com", password=PASSWORD, role=UserRoles.HOMESTAY_OWNER
        )

        self.sign_in()

        merchant.refresh_from_db()
        self.assertEqual(merchant.google_sub, "google-1")
        self.assertFalse(merchant.email_verified)

    def test_legacy_tourist_becomes_verified_and_keeps_password(self):
        tourist = User.objects.create_user(email="person@example.com", password=PASSWORD)

        self.sign_in()

        tourist.refresh_from_db()
        self.assertTrue(tourist.email_verified)
        self.assertTrue(tourist.check_password(PASSWORD))

    def test_admin_accounts_must_use_their_password(self):
        admin = User.objects.create_user(
            email="person@example.com", password=PASSWORD, role=UserRoles.COMMUNITY_ADMIN, email_verified=True
        )

        self.sign_in()

        admin.refresh_from_db()
        self.assertNotLoggedIn()
        self.assertIsNone(admin.google_sub)

    def test_suspended_account_is_refused(self):
        User.objects.create_user(email="person@example.com", password=PASSWORD, is_active=False)

        self.sign_in()

        self.assertNotLoggedIn()

    def test_email_linked_to_another_google_account_is_refused(self):
        User.objects.create_user(email="person@example.com", password=PASSWORD, google_sub="google-other")

        self.sign_in()

        self.assertNotLoggedIn()

    def test_invalid_claims_are_refused(self):
        cases = [
            {"aud": "someone-elses-client"},
            {"iss": "https://evil.example.com"},
            {"exp": time.time() - 1},
            {"nonce": "replayed"},
            {"email_verified": False},
        ]
        for overrides in cases:
            with self.subTest(overrides):
                self.sign_in(overrides=overrides)
                self.assertNotLoggedIn()
        self.assertFalse(User.objects.exists())

    def test_wrong_state_never_reaches_google(self):
        self.start_flow()

        with mock.patch(TOKEN_POST) as post:
            response = self.client.get(reverse("accounts:google_callback"), {"state": "forged", "code": "abc"})

        self.assertRedirects(response, reverse("accounts:login"))
        post.assert_not_called()

    def test_state_is_single_use(self):
        state, _nonce = self.start_flow()
        self.client.get(reverse("accounts:google_callback"), {"state": state, "error": "access_denied"})

        with mock.patch(TOKEN_POST) as post:
            self.client.get(reverse("accounts:google_callback"), {"state": state, "code": "abc"})

        post.assert_not_called()

    def test_google_outage_shows_login_page(self):
        state, _nonce = self.start_flow()

        with mock.patch(TOKEN_POST, side_effect=requests.ConnectionError("down")):
            response = self.client.get(reverse("accounts:google_callback"), {"state": state, "code": "abc"})

        self.assertRedirects(response, reverse("accounts:login"))
        self.assertNotLoggedIn()

    def test_malformed_id_token_is_refused(self):
        state, _nonce = self.start_flow()
        answer = mock.Mock()
        answer.json.return_value = {"id_token": "not-a-jwt"}

        with mock.patch(TOKEN_POST, return_value=answer):
            response = self.client.get(reverse("accounts:google_callback"), {"state": state, "code": "abc"})

        self.assertRedirects(response, reverse("accounts:login"))

    def test_next_is_followed_only_when_local(self):
        response = self.sign_in(query="?next=/bookings/cart/")
        self.assertEqual(response.url, "/bookings/cart/")
        self.client.logout()

        response = self.sign_in(query="?next=//evil.example.com/")
        self.assertRedirects(response, reverse("core:home"))

    def test_button_shows_on_tourist_pages_only(self):
        google_url = reverse("accounts:google_login")
        self.assertContains(self.client.get(reverse("accounts:login")), google_url)
        self.assertContains(self.client.get(reverse("accounts:register")), google_url)
        self.assertNotContains(self.client.get(reverse("accounts:login") + "?role=merchant"), google_url)
        self.assertNotContains(self.client.get(reverse("accounts:register_merchant")), google_url)

    @override_settings(GOOGLE_OAUTH_CLIENT_SECRET="")
    def test_without_a_secret_the_feature_stays_off(self):
        self.assertNotContains(self.client.get(reverse("accounts:login")), reverse("accounts:google_login"))
        self.assertRedirects(self.client.get(reverse("accounts:google_login")), reverse("accounts:login"))
