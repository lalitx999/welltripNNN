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


class MerchantRegistrationForm(forms.Form):
    """
    Comprehensive Merchant / Vendor Registration Form (3-Step Wizard compatible).
    Saves both the User account (with role corresponding to business category)
    and the associated MerchantProfile (status=PENDING for Admin KYC review).
    """
    CATEGORY_CHOICES = [
        ("HOMESTAY", "โฮมสเตย์ / ที่พักชุมชน (บ้านพัก ที่พักนิเวศ รีสอร์ทชุมชน)"),
        ("RESTAURANT", "ร้านอาหารเพื่อสุขภาพ (อาหารออร์แกนิก สมุนไพร อาหารพื้นบ้าน)"),
        ("WELLNESS", "บริการสุขภาพ & สปา (นวดแผนไทย สปาอโรมา วารีบำบัด)"),
        ("OTOP", "สินค้า OTOP ชุมชน (สินค้าชุมชน ผลิตภัณฑ์สมุนไพร หัตถกรรม)"),
    ]

    # Step 1: Business Category
    business_category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        initial="HOMESTAY",
        label="ประเภทสถานประกอบการ",
    )

    # Step 2: Personal Account Info
    first_name = forms.CharField(max_length=150, label="ชื่อเจ้าของร้าน / ผู้ดูแล")
    last_name = forms.CharField(max_length=150, label="นามสกุล")
    phone_number = forms.CharField(max_length=20, label="เบอร์โทรศัพท์ติดต่อ")
    email = forms.EmailField(label="อีเมลเข้าสู่ระบบ")
    password = forms.CharField(label="รหัสผ่าน", widget=forms.PasswordInput)
    confirm_password = forms.CharField(label="ยืนยันรหัสผ่าน", widget=forms.PasswordInput)

    # Step 3: Business Profile Info
    business_name = forms.CharField(max_length=200, label="ชื่อสถานประกอบการ / ร้านค้า")
    opening_hours = forms.CharField(
        max_length=150, required=False, initial="08:00 - 18:00 น.", label="วันและเวลาเปิดทำการ"
    )
    google_maps_url = forms.URLField(
        max_length=500, required=False, label="ลิงก์ Google Maps ของร้าน"
    )
    description = forms.CharField(
        widget=forms.Textarea, required=False, label="คำอธิบายร้านค้า / จุดเด่นของบริการ"
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError("อีเมลนี้ถูกลงทะเบียนไว้ในระบบแล้ว กรุณาเข้าสู่ระบบ")
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) < 9:
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

    def save(self):
        data = self.cleaned_data
        cat_to_role = {
            "HOMESTAY": UserRoles.HOMESTAY_OWNER,
            "RESTAURANT": UserRoles.RESTAURANT_OWNER,
            "WELLNESS": UserRoles.WELLNESS_OWNER,
            "OTOP": UserRoles.OTOP_OWNER,
        }
        user_role = cat_to_role.get(data['business_category'], UserRoles.HOMESTAY_OWNER)

        user = User.objects.create_user(
            email=data['email'],
            password=data['password'],
            first_name=data['first_name'],
            last_name=data['last_name'],
            phone_number=data['phone_number'],
            role=user_role,
        )

        from apps.accounts.models import MerchantProfile, MerchantApprovalStatus
        merchant_profile = MerchantProfile.objects.create(
            user=user,
            business_name=data['business_name'],
            business_category=data['business_category'],
            description=data.get('description', ''),
            google_maps_url=data.get('google_maps_url', ''),
            phone_number=data['phone_number'],
            opening_hours=data.get('opening_hours', '08:00 - 18:00 น.'),
            status=MerchantApprovalStatus.PENDING,
        )

        return user, merchant_profile

