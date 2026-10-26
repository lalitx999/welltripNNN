import time
from django.test import TestCase, Client
from django.urls import reverse
from apps.accounts.models import User, UserRoles, AuditLog
from apps.accounts.permissions import can_edit_object, can_delete_object


class MockOwnedObject:
    def __init__(self, owner_id, status="DRAFT"):
        self.owner_id = owner_id
        self.status = status


class AccountsSecurityTestCase(TestCase):
    """
    Security Test Suite for EP 2:
    Verifies Authentication, Session rotation, Row-level authorization (Anti-IDOR),
    Audit Logging, and Idle Timeout.
    """

    def setUp(self):
        self.client = Client()
        self.password = "StrongPass12345!"

        # Create Tourist
        self.tourist = User.objects.create_user(
            email="tourist@example.com",
            password=self.password,
            role=UserRoles.TOURIST,
            first_name="Somchai",
            last_name="Jaidee"
        )

        # Create Homestay Owner
        self.owner = User.objects.create_user(
            email="owner@example.com",
            password=self.password,
            role=UserRoles.HOMESTAY_OWNER,
            first_name="Boonmee",
            last_name="Supan"
        )

        # Create Community Admin
        self.admin = User.objects.create_user(
            email="admin@example.com",
            password=self.password,
            role=UserRoles.COMMUNITY_ADMIN,
            first_name="Wichai",
            last_name="Admin"
        )

    def test_user_registration_argon2_password(self):
        """Verifies new user passwords are saved with Argon2 hasher."""
        user = User.objects.get(email="tourist@example.com")
        self.assertTrue(user.password.startswith("argon2"))
        self.assertTrue(user.check_password(self.password))

    def test_login_records_audit_log_and_rotates_session(self):
        """
        WHY: Prevents Session Fixation and ensures accountability via AuditLog.
        """
        # Initial request to establish session
        self.client.get(reverse('accounts:login'))
        old_session_key = self.client.session.session_key

        response = self.client.post(reverse('accounts:login'), {
            'email': 'tourist@example.com',
            'password': self.password,
        })
        self.assertEqual(response.status_code, 302)

        # Verify session key changed (rotated)
        new_session_key = self.client.session.session_key
        self.assertNotEqual(old_session_key, new_session_key)

        # Verify AuditLog recorded LOGIN
        log = AuditLog.objects.filter(action="LOGIN", user=self.tourist).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.model_name, "User")
        self.assertEqual(log.object_id, str(self.tourist.id))

    def test_role_required_blocks_tourist_from_partner_portal(self):
        """
        WHY: Enforces role isolation. Tourists must NOT access the Partner Portal.
        """
        self.client.force_login(self.tourist)
        response = self.client.get(reverse('accounts:portal_dashboard'))

        # Should be strictly blocked with HTTP 403 Forbidden
        self.assertEqual(response.status_code, 403)

        # Verify AuditLog logged PERMISSION_DENIED
        denied_log = AuditLog.objects.filter(action="PERMISSION_DENIED", user=self.tourist).first()
        self.assertIsNotNone(denied_log)
        self.assertIn("HOMESTAY_OWNER", denied_log.changes["required_roles"])

    def test_role_required_allows_homestay_owner_into_portal(self):
        """Verifies authorized merchant can access Partner Portal."""
        self.client.force_login(self.owner)
        response = self.client.get(reverse('accounts:portal_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Partner Studio")

    def test_ownership_guard_anti_idor(self):
        """
        WHY: Prevents Insecure Direct Object References (IDOR).
        Owner 1 must never be allowed to edit or delete Owner 2's entity.
        """
        other_user = User.objects.create_user(
            email="other_owner@example.com",
            password=self.password,
            role=UserRoles.HOMESTAY_OWNER
        )

        obj_owned_by_owner = MockOwnedObject(owner_id=self.owner.id)

        # Owner can edit their own object
        self.assertTrue(can_edit_object(self.owner, obj_owned_by_owner))

        # Other owner CANNOT edit this object (IDOR blocked!)
        self.assertFalse(can_edit_object(other_user, obj_owned_by_owner))

        # Tourist CANNOT edit this object
        self.assertFalse(can_edit_object(self.tourist, obj_owned_by_owner))

        # Admin CAN edit for moderation purposes
        self.assertTrue(can_edit_object(self.admin, obj_owned_by_owner))

    def test_session_idle_timeout_middleware(self):
        """
        WHY: Enforces 30-minute idle session termination (OWASP).
        """
        self.client.force_login(self.owner)

        # Simulate inactivity beyond 1800 seconds (30 mins)
        session = self.client.session
        session['last_activity'] = int(time.time()) - 2000
        session.save()

        # Next request must be redirected to login due to expiration
        response = self.client.get(reverse('accounts:portal_dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse('accounts:login'), response.url)
