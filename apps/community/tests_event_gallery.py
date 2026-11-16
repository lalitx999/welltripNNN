import io
import shutil
import tempfile
from datetime import timedelta

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import AuditLog, User, UserRoles
from apps.community.models import Event, EventImage

MEDIA = tempfile.mkdtemp()


def png(name="photo.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (40, 30), (20, 140, 80)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


@override_settings(MEDIA_ROOT=MEDIA)
class EventGalleryTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA, ignore_errors=True)

    def setUp(self):
        today = timezone.localdate()
        self.event = Event.objects.create(
            title="งานทุเรียนภูเขาไฟ", start_date=today, end_date=today + timedelta(days=2), is_published=True,
        )
        self.admin = User.objects.create_user(email="gallery_admin@example.com", password="x", role=UserRoles.COMMUNITY_ADMIN)
        self.tourist = User.objects.create_user(email="gallery_tourist@example.com", password="x", role=UserRoles.TOURIST)
        self.add_url = reverse("accounts:admin_event_gallery_add", args=[self.event.id])

    def test_admin_uploads_several_photos_at_once(self):
        self.client.force_login(self.admin)
        response = self.client.post(self.add_url, {"images": [png("a.png"), png("b.png"), png("c.png")]})
        self.assertRedirects(response, reverse("accounts:admin_event_edit", args=[self.event.id]), fetch_redirect_response=False)
        photos = list(self.event.gallery.all())
        self.assertEqual([p.order for p in photos], [0, 1, 2])
        self.assertTrue(AuditLog.objects.filter(model_name="Event", object_id=str(self.event.id)).exists())

    def test_gallery_is_capped_at_ten_photos(self):
        for i in range(EventImage.MAX_PER_EVENT - 1):
            EventImage.objects.create(event=self.event, image=png(f"{i}.png"), order=i)
        self.client.force_login(self.admin)
        self.client.post(self.add_url, {"images": [png("x.png"), png("y.png")]})
        self.assertEqual(self.event.gallery.count(), EventImage.MAX_PER_EVENT - 1)
        self.client.post(self.add_url, {"images": [png("z.png")]})
        self.assertEqual(self.event.gallery.count(), EventImage.MAX_PER_EVENT)

    def test_files_that_are_not_images_are_rejected(self):
        self.client.force_login(self.admin)
        fake = SimpleUploadedFile("shell.png", b"<?php echo 1; ?>", content_type="image/png")
        self.client.post(self.add_url, {"images": [fake]})
        self.assertFalse(self.event.gallery.exists())

    def test_only_admins_can_change_the_gallery(self):
        photo = EventImage.objects.create(event=self.event, image=png(), order=0)
        self.client.force_login(self.tourist)
        self.client.post(self.add_url, {"images": [png()]})
        self.client.post(reverse("accounts:admin_event_gallery_delete", args=[photo.id]))
        self.assertEqual(self.event.gallery.count(), 1)

    def test_admin_deletes_a_photo(self):
        photo = EventImage.objects.create(event=self.event, image=png(), order=0)
        self.client.force_login(self.admin)
        self.client.post(reverse("accounts:admin_event_gallery_delete", args=[photo.id]))
        self.assertFalse(self.event.gallery.exists())

    def test_event_page_shows_the_gallery(self):
        EventImage.objects.create(event=self.event, image=png(), order=0)
        EventImage.objects.create(event=self.event, image=png(), order=1)
        response = self.client.get(reverse("community:event_detail", args=[self.event.id]))
        self.assertContains(response, "บรรยากาศในงาน")
        self.assertContains(response, 'loading="lazy"', count=2)

    def test_event_page_without_photos_has_no_gallery(self):
        response = self.client.get(reverse("community:event_detail", args=[self.event.id]))
        self.assertNotContains(response, "บรรยากาศในงาน")

    def test_admin_edit_page_shows_upload_form(self):
        self.client.force_login(self.admin)
        response = self.client.get(reverse("accounts:admin_event_edit", args=[self.event.id]))
        self.assertContains(response, "แกลเลอรีรูปภาพ")
        self.assertContains(response, self.add_url)
