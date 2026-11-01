"""
Create or update a WellTrip super admin without putting the password in code.

Usage (on the server):
    docker compose exec backend python manage.py create_admin you@example.com
The password is prompted interactively and never echoed or stored in git.
"""
import getpass

from django.contrib.auth import get_user_model, password_validation
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import UserRoles


class Command(BaseCommand):
    help = "Create or update a SUPER_ADMIN account (password is prompted, not passed as an argument)."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **options):
        User = get_user_model()
        email = User.objects.normalize_email(options["email"]).lower()

        password = getpass.getpass("รหัสผ่านใหม่: ")
        if password != getpass.getpass("ยืนยันรหัสผ่าน: "):
            raise CommandError("รหัสผ่านทั้งสองครั้งไม่ตรงกัน")

        user = User.objects.filter(email__iexact=email).first() or User(email=email)
        try:
            password_validation.validate_password(password, user)
        except ValidationError as exc:
            raise CommandError(" ".join(exc.messages))

        created = user._state.adding
        user.role = UserRoles.SUPER_ADMIN
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.email_verified = True
        user.set_password(password)
        user.save()

        action = "สร้าง" if created else "อัปเดต"
        self.stdout.write(self.style.SUCCESS(f"{action}บัญชีแอดมิน {email} เรียบร้อย"))
