from django.test import TestCase, Client
from django.conf import settings
from django.contrib.auth.hashers import get_hasher


class SecuritySettingsTestCase(TestCase):
    """
    Automated Security Tests verifying non-negotiable security requirements.
    """

    def setUp(self):
        self.client = Client()

    def test_argon2_is_primary_password_hasher(self):
        """
        WHY: Argon2 is memory-hard and GPU-resistant.
        Verifies Argon2 is the first hasher in PASSWORD_HASHERS.
        """
        hasher = get_hasher('default')
        self.assertEqual(hasher.algorithm, 'argon2')

    def test_session_cookie_security_flags(self):
        """
        WHY: Prevents session theft via XSS (HttpOnly) and CSRF (SameSite=Lax).
        """
        self.assertTrue(settings.SESSION_COOKIE_HTTPONLY)
        self.assertEqual(settings.SESSION_COOKIE_SAMESITE, 'Lax')
        # Absolute session limit must not exceed 12 hours (43200s)
        self.assertLessEqual(settings.SESSION_COOKIE_AGE, 43200)

    def test_csrf_cookie_security_flags(self):
        """
        WHY: Prevents CSRF token extraction via client scripts.
        """
        self.assertTrue(settings.CSRF_COOKIE_HTTPONLY)
        self.assertEqual(settings.CSRF_COOKIE_SAMESITE, 'Lax')

    def test_browser_hardening_headers(self):
        """
        WHY: Prevents Clickjacking (X-Frame-Options: DENY) and MIME sniffing.
        """
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get('X-Frame-Options'), 'DENY')
        self.assertEqual(response.headers.get('X-Content-Type-Options'), 'nosniff')

    def test_content_security_policy_present(self):
        """
        WHY: Restricts execution of unauthorized third-party scripts.
        """
        response = self.client.get('/')
        self.assertIn('Content-Security-Policy', response.headers)
        csp = response.headers.get('Content-Security-Policy')
        self.assertIn("default-src 'self'", csp)

    def test_home_page_injects_htmx_csrf(self):
        """
        WHY: Guarantees every AJAX/HTMX request passes Django's CSRF guard.
        """
        response = self.client.get('/')
        self.assertContains(response, 'hx-headers')
        self.assertContains(response, 'X-CSRFToken')
