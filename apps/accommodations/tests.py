import io
from datetime import date
from decimal import Decimal
from PIL import Image
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError
from django.test import TestCase

from apps.accounts.models import User, UserRoles
from apps.accommodations.models import Accommodation, Room, RoomPricingCalendar
from apps.core.services.media import (
    secure_upload_path,
    validate_magic_bytes,
    sanitize_and_strip_image,
)


class CatalogAndMediaSecurityTestCase(TestCase):
    """
    Security Test Suite for EP 3:
    Verifies path traversal defense, magic byte verification, EXIF stripping,
    and database integrity constraints.
    """

    def setUp(self):
        self.owner = User.objects.create_user(
            email="homestay_owner@example.com",
            password="StrongPassword123!",
            role=UserRoles.HOMESTAY_OWNER,
        )

    def test_secure_upload_path_prevents_path_traversal(self):
        """
        WHY: Path traversal attacks (e.g., ../../etc/passwd) must never
        influence the filesystem destination.
        """
        accommodation = Accommodation.objects.create(
            owner=self.owner,
            name="บ้านริมสวน",
        )
        malicious_filename = "../../../etc/cron.d/shell.php.jpg"
        clean_path = secure_upload_path(accommodation, malicious_filename, model_subdir="accommodations")

        # Verify no directory traversal dots exist in path
        self.assertNotIn("..", clean_path)
        self.assertTrue(clean_path.startswith("accommodations/"))
        self.assertTrue(clean_path.endswith(".jpg"))

    def test_magic_bytes_blocks_disguised_file(self):
        """
        WHY: Attackers often rename executable shell scripts to .jpg to bypass extensions.
        Magic byte checking reads the binary header to prevent this.
        """
        fake_image = io.BytesIO(b"<?php echo 'malicious webshell'; ?>")
        with self.assertRaises(ValidationError) as ctx:
            validate_magic_bytes(fake_image, ext="jpg")
        self.assertIn("Magic Byte Mismatch", str(ctx.exception))

    def test_sanitize_and_strip_image_processes_valid_image(self):
        """
        WHY: Valid images must be re-encoded cleanly through Pillow to strip EXIF.
        """
        # Create a small valid 100x100 RGB image in memory
        img = Image.new("RGB", (100, 100), color="green")
        buf = io.BytesIO()
        img.save(buf, format="JPEG")
        buf.seek(0)

        uploaded = SimpleUploadedFile("test.jpg", buf.read(), content_type="image/jpeg")
        cleaned_file = sanitize_and_strip_image(uploaded)

        self.assertIsNotNone(cleaned_file)
        self.assertEqual(cleaned_file.content_type, "image/jpeg")

        # Verify Pillow can open the sanitized image and it contains no EXIF
        opened = Image.open(cleaned_file)
        self.assertEqual(opened.size, (100, 100))
        self.assertIsNone(opened.getexif().get(0x0112))  # EXIF Orientation check

    def test_room_pricing_calendar_unique_together(self):
        """
        WHY: Guarantees that there is only one inventory row per room per date.
        """
        accommodation = Accommodation.objects.create(
            owner=self.owner,
            name="โฮมสเตย์ภูมินทร์",
        )
        room = Room.objects.create(
            accommodation=accommodation,
            name="ห้องสวนไผ่",
            base_price_per_night=Decimal("800.00"),
            total_rooms_count=2,
        )

        test_date = date(2026, 12, 1)
        RoomPricingCalendar.objects.create(
            room=room,
            date=test_date,
            price=Decimal("800.00"),
            available_count=2,
        )

        # Attempting duplicate insert for the same room and date must raise IntegrityError
        with self.assertRaises(IntegrityError):
            RoomPricingCalendar.objects.create(
                room=room,
                date=test_date,
                price=Decimal("900.00"),
                available_count=2,
            )

    def test_accommodation_slug_auto_generation(self):
        """Verifies slug is automatically populated on save without crashing."""
        accommodation = Accommodation.objects.create(
            owner=self.owner,
            name="บ้านสวนริมธาร ขุนหาญ",
        )
        self.assertTrue(bool(accommodation.slug))
        self.assertTrue(accommodation.slug.startswith("บ"))
