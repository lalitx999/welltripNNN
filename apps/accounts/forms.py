from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from apps.accounts.models import User, UserRoles


class LoginForm(forms.Form):
    """
    Secure Login Form validating credentials through Django's authentication backend.
    """
    email = forms.EmailField(
        label="อีเมล",
        widget=forms.EmailInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest',
            'placeholder': 'name@example.com',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label="รหัสผ่าน",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest',
            'placeholder': '••••••••••',
            'autocomplete': 'current-password',
        })
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        email = cleaned_data.get('email')
        password = cleaned_data.get('password')

        if email and password:
            # Authenticate against custom user backend using normalized email
            self.user_cache = authenticate(
                self.request,
                email=email.lower().strip(),
                password=password
            )
            if self.user_cache is None:
                raise ValidationError("อีเมลหรือรหัสผ่านไม่ถูกต้อง โปรดตรวจสอบอีกครั้ง")
            elif not self.user_cache.is_active:
                raise ValidationError("บัญชีนี้ถูกระงับการใช้งาน กรุณาติดต่อผู้ดูแลระบบ")

        return cleaned_data

    def get_user(self):
        return self.user_cache


class UserRegistrationForm(forms.ModelForm):
    """
    User Registration Form with strict input validation and password checks.
    """
    password = forms.CharField(
        label="รหัสผ่าน",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest',
            'placeholder': 'อย่างน้อย 10 ตัวอักษร',
            'autocomplete': 'new-password',
        })
    )
    confirm_password = forms.CharField(
        label="ยืนยันรหัสผ่าน",
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest',
            'placeholder': 'กรอกรหัสผ่านซ้ำอีกครั้ง',
            'autocomplete': 'new-password',
        })
    )

    ALLOWED_REGISTRATION_ROLES = [
        (UserRoles.TOURIST, "นักท่องเที่ยว (Tourist)"),
        (UserRoles.HOMESTAY_OWNER, "เจ้าของที่พัก / โฮมสเตย์ (Homestay Owner)"),
        (UserRoles.RESTAURANT_OWNER, "เจ้าของร้านอาหารสุขภาพ (Restaurant Owner)"),
        (UserRoles.WELLNESS_OWNER, "เจ้าของบริการนวด / สปา (Wellness Owner)"),
        (UserRoles.OTOP_OWNER, "เจ้าของสินค้าชุมชน OTOP (OTOP Owner)"),
    ]

    role = forms.ChoiceField(
        choices=ALLOWED_REGISTRATION_ROLES,
        label="ประเภทผู้ใช้งาน",
        widget=forms.Select(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest',
        })
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone_number', 'role']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest', 'placeholder': 'name@example.com'}),
            'first_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest'}),
            'phone_number': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:outline-none focus:ring-2 focus:ring-forest', 'placeholder': '0812345678'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("อีเมลนี้ถูกใช้งานแล้วในระบบ")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone:
            return ""
        # Clean non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        if digits and len(digits) < 9:
            raise ValidationError("หมายเลขโทรศัพท์ต้องมีอย่างน้อย 9-10 หลัก")
        return digits

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', "รหัสผ่านทั้งสองช่องไม่ตรงกัน")
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error('password', e)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user
