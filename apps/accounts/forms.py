from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from apps.accounts.models import MerchantProfile, User, UserRoles
from django.utils.translation import gettext as _, gettext_lazy


class LoginForm(forms.Form):
    """
    Secure Login Form validating credentials through Django's authentication backend.
    """
    email = forms.EmailField(
        label=gettext_lazy("อีเมล"),
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'name@example.com',
            'autocomplete': 'email',
        })
    )
    password = forms.CharField(
        label=gettext_lazy("รหัสผ่าน"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
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
                raise ValidationError(_("อีเมลหรือรหัสผ่านไม่ถูกต้อง โปรดตรวจสอบอีกครั้ง"))
            elif not self.user_cache.is_active:
                raise ValidationError(_("บัญชีนี้ถูกระงับการใช้งาน กรุณาติดต่อผู้ดูแลระบบ"))

        return cleaned_data

    def get_user(self):
        return self.user_cache


class EmailOTPForm(forms.Form):
    """Rejects malformed input up front so a typo does not use up an OTP attempt."""
    code = forms.RegexField(
        regex=r'^[0-9]{6}$',
        label=gettext_lazy("รหัส OTP"),
        error_messages={
            'required': gettext_lazy("กรุณากรอกรหัส OTP"),
            'invalid': gettext_lazy("กรุณากรอกรหัสตัวเลข 6 หลัก"),
        },
    )


class UserRegistrationForm(forms.ModelForm):
    """
    User Registration Form with strict input validation and password checks.
    """
    password = forms.CharField(
        label=gettext_lazy("รหัสผ่าน"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': gettext_lazy("อย่างน้อย 10 ตัวอักษร"),
            'autocomplete': 'new-password',
        })
    )
    confirm_password = forms.CharField(
        label=gettext_lazy("ยืนยันรหัสผ่าน"),
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': gettext_lazy("กรอกรหัสผ่านซ้ำอีกครั้ง"),
            'autocomplete': 'new-password',
        })
    )

    # Merchants must sign up through MerchantRegistrationForm so they get a KYC profile
    ALLOWED_REGISTRATION_ROLES = [
        (UserRoles.TOURIST, gettext_lazy("นักท่องเที่ยว (Tourist)")),
    ]

    role = forms.ChoiceField(
        choices=ALLOWED_REGISTRATION_ROLES,
        label=gettext_lazy("ประเภทผู้ใช้งาน"),
        widget=forms.Select(attrs={
            'class': 'form-select',
        })
    )

    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name', 'phone_number', 'role']
        widgets = {
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'name@example.com'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '0812345678'}),
        }

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError(_("อีเมลนี้ถูกใช้งานแล้วในระบบ"))
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        if not phone:
            return ""
        # Clean non-digits
        digits = ''.join(c for c in phone if c.isdigit())
        if digits and len(digits) < 9:
            raise ValidationError(_("หมายเลขโทรศัพท์ต้องมีอย่างน้อย 9-10 หลัก"))
        return digits

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', _("รหัสผ่านทั้งสองช่องไม่ตรงกัน"))
            else:
                try:
                    validate_password(password)
                except ValidationError as e:
                    self.add_error('password', e)

        return cleaned_data

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password'])
        user.email_verification_required = True
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
        ("HOMESTAY", gettext_lazy("โฮมสเตย์ / ที่พักชุมชน (บ้านพัก ที่พักนิเวศ รีสอร์ทชุมชน)")),
        ("RESTAURANT", gettext_lazy("ร้านอาหารเพื่อสุขภาพ (อาหารออร์แกนิก สมุนไพร อาหารพื้นบ้าน)")),
        ("WELLNESS", gettext_lazy("บริการสุขภาพ & สปา (นวดแผนไทย สปาอโรมา วารีบำบัด)")),
        ("OTOP", gettext_lazy("สินค้า OTOP ชุมชน (สินค้าชุมชน ผลิตภัณฑ์สมุนไพร หัตถกรรม)")),
    ]

    # Step 1: Business Category
    business_category = forms.ChoiceField(
        choices=CATEGORY_CHOICES,
        initial="HOMESTAY",
        label=gettext_lazy("ประเภทสถานประกอบการ"),
    )

    # Step 2: Personal Account Info
    first_name = forms.CharField(max_length=150, label=gettext_lazy("ชื่อเจ้าของร้าน / ผู้ดูแล"))
    last_name = forms.CharField(max_length=150, label=gettext_lazy("นามสกุล"))
    phone_number = forms.CharField(max_length=20, label=gettext_lazy("เบอร์โทรศัพท์ติดต่อ"))
    email = forms.EmailField(label=gettext_lazy("อีเมลเข้าสู่ระบบ"))
    password = forms.CharField(label=gettext_lazy("รหัสผ่าน"), widget=forms.PasswordInput)
    confirm_password = forms.CharField(label=gettext_lazy("ยืนยันรหัสผ่าน"), widget=forms.PasswordInput)

    # Step 3: Business Profile Info
    business_name = forms.CharField(max_length=200, label=gettext_lazy("ชื่อสถานประกอบการ / ร้านค้า"))
    opening_hours = forms.CharField(
        max_length=150, required=False, initial=gettext_lazy("08:00 - 18:00 น."), label=gettext_lazy("วันและเวลาเปิดทำการ")
    )
    google_maps_url = forms.URLField(
        max_length=500, required=False, label=gettext_lazy("ลิงก์ Google Maps ของร้าน")
    )
    description = forms.CharField(
        widget=forms.Textarea, required=False, label=gettext_lazy("คำอธิบายร้านค้า / จุดเด่นของบริการ")
    )

    def clean_email(self):
        email = self.cleaned_data.get('email', '').lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError(_("อีเมลนี้ถูกลงทะเบียนไว้ในระบบแล้ว กรุณาเข้าสู่ระบบ"))
        return email

    def clean_phone_number(self):
        phone = self.cleaned_data.get('phone_number', '').strip()
        digits = ''.join(c for c in phone if c.isdigit())
        if len(digits) < 9:
            raise ValidationError(_("หมายเลขโทรศัพท์ต้องมีอย่างน้อย 9-10 หลัก"))
        return digits

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')

        if password and confirm_password:
            if password != confirm_password:
                self.add_error('confirm_password', _("รหัสผ่านทั้งสองช่องไม่ตรงกัน"))
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
            email_verification_required=True,
        )

        from apps.accounts.models import MerchantProfile, MerchantApprovalStatus
        merchant_profile = MerchantProfile.objects.create(
            user=user,
            business_name=data['business_name'],
            business_category=data['business_category'],
            description=data.get('description', ''),
            google_maps_url=data.get('google_maps_url', ''),
            phone_number=data['phone_number'],
            opening_hours=data.get('opening_hours', _("08:00 - 18:00 น.")),
            status=MerchantApprovalStatus.PENDING,
        )

        return user, merchant_profile



class ShopProfileForm(forms.ModelForm):
    """Storefront details a partner can edit any time, including while awaiting approval."""

    class Meta:
        model = MerchantProfile
        fields = ['business_name', 'description', 'phone_number', 'opening_hours', 'google_maps_url']
        labels = {
            'business_name': gettext_lazy("ชื่อร้าน"),
            'description': gettext_lazy("แนะนำร้าน"),
            'phone_number': gettext_lazy("เบอร์ติดต่อ"),
            'opening_hours': gettext_lazy("เวลาเปิด-ปิด"),
            'google_maps_url': gettext_lazy("ลิงก์ Google Maps ของร้าน"),
        }
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'maxlength': 1500,
                                                 'placeholder': gettext_lazy("เล่าเรื่องร้าน จุดเด่น และสิ่งที่ลูกค้าจะได้รับ")}),
            'phone_number': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'tel'}),
            'opening_hours': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น ทุกวัน 08:00 - 18:00 น.")}),
            'google_maps_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://maps.app.goo.gl/...'}),
        }

    def clean_business_name(self):
        name = self.cleaned_data['business_name'].strip()
        if '@' in name:
            raise forms.ValidationError(gettext_lazy("ชื่อร้านต้องไม่ใช่อีเมล"))
        return name

    def clean_description(self):
        return self.cleaned_data['description'].strip()[:1500]


class ShopImageForm(forms.Form):
    image = forms.ImageField(widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp'}))

    def clean_image(self):
        from apps.core.services.media import sanitize_and_strip_image
        return sanitize_and_strip_image(self.cleaned_data['image'])


class ExtraServicesForm(forms.Form):
    """Partner ticks the other kinds of business their shop runs (opens at once)."""
    services = forms.MultipleChoiceField(
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label=gettext_lazy("บริการที่เปิดเพิ่ม"),
    )

    def __init__(self, *args, profile, **kwargs):
        from apps.accounts.models import SERVICE_CATEGORY_CHOICES
        super().__init__(*args, **kwargs)
        # The main category is always on, so it is not offered again
        self.fields['services'].choices = [
            (code, label) for code, label in SERVICE_CATEGORY_CHOICES if code != profile.business_category
        ]
        self.profile = profile
        if not self.is_bound:
            self.initial['services'] = profile.service_categories[1:]

    def clean_services(self):
        chosen = self.cleaned_data['services']
        closing = [c for c in self.profile.service_categories[1:] if c not in chosen]
        labels = dict(self.fields['services'].choices)
        for code in closing:
            if live_listing_count(self.profile.user, code):
                raise forms.ValidationError(
                    gettext_lazy("ยังมีรายการ \"{service}\" เปิดขายอยู่ ปิดการขายรายการเหล่านั้นก่อน แล้วค่อยปิดบริการนี้").format(
                        service=labels.get(code, code))
                )
        return chosen


def live_listing_count(owner, category):
    """Listings of one service category the owner still has open to customers."""
    from apps.accommodations.models import Accommodation, AccommodationStatus
    from apps.otop.models import OTOPProduct
    from apps.services.models import FoodMenu, WellnessService

    if category == 'HOMESTAY':
        return Accommodation.objects.filter(owner=owner, status=AccommodationStatus.ACTIVE).count()
    if category == 'RESTAURANT':
        return FoodMenu.objects.filter(owner=owner, is_available=True).count()
    if category == 'WELLNESS':
        return WellnessService.objects.filter(owner=owner, is_active=True).count()
    if category == 'OTOP':
        return OTOPProduct.objects.filter(owner=owner, is_active=True).count()
    return 0


class PayoutAccountForm(forms.ModelForm):
    """Bank account the admin transfers the partner's share to after settling the books."""

    class Meta:
        model = MerchantProfile
        fields = ['payout_bank', 'payout_account_number', 'payout_account_name', 'promptpay_id']
        labels = {
            'payout_bank': gettext_lazy("ธนาคาร"),
            'payout_account_number': gettext_lazy("เลขที่บัญชี"),
            'payout_account_name': gettext_lazy("ชื่อบัญชี (ชื่อผู้รับในธนาคาร)"),
            'promptpay_id': gettext_lazy("พร้อมเพย์ (ไม่บังคับ)"),
        }
        help_texts = {
            'payout_account_name': gettext_lazy("พิมพ์ให้ตรงกับชื่อในสมุดบัญชี"),
            'promptpay_id': gettext_lazy("เบอร์มือถือ 10 หลัก หรือเลขบัตรประชาชน 13 หลัก"),
        }
        widgets = {
            'payout_bank': forms.Select(attrs={'class': 'form-select'}),
            'payout_account_number': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric',
                                                            'autocomplete': 'off', 'placeholder': 'xxx-x-xxxxx-x'}),
            'payout_account_name': forms.TextInput(attrs={'class': 'form-control', 'maxlength': 200, 'autocomplete': 'off'}),
            'promptpay_id': forms.TextInput(attrs={'class': 'form-control', 'inputmode': 'numeric', 'autocomplete': 'off',
                                                   'placeholder': gettext_lazy("เช่น 0812345678")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('payout_bank', 'payout_account_number', 'payout_account_name'):
            self.fields[name].required = True
        self.fields['payout_bank'].choices = [('', gettext_lazy("— เลือกธนาคาร —"))] + [
            c for c in self.fields['payout_bank'].choices if c[0]
        ]

    @staticmethod
    def _digits(value):
        # People type dashes and spaces, e.g. 123-4-56789-0 or 081 234 5678
        cleaned = str(value or '').replace('-', '').replace(' ', '').strip()
        if cleaned and not cleaned.isdigit():
            raise forms.ValidationError(gettext_lazy("กรอกเป็นตัวเลขเท่านั้น"))
        return cleaned

    def clean_payout_account_number(self):
        number = self._digits(self.cleaned_data['payout_account_number'])
        if not 10 <= len(number) <= 15:
            raise forms.ValidationError(gettext_lazy("เลขที่บัญชีต้องมี 10-15 หลัก"))
        return number

    def clean_payout_account_name(self):
        return ' '.join(self.cleaned_data['payout_account_name'].split())

    def clean_promptpay_id(self):
        pp = self._digits(self.cleaned_data.get('promptpay_id'))
        if pp and len(pp) not in (10, 13):
            raise forms.ValidationError(gettext_lazy("พร้อมเพย์ต้องเป็นเบอร์มือถือ 10 หลัก หรือเลขบัตรประชาชน 13 หลัก"))
        if len(pp) == 10 and not pp.startswith('0'):
            raise forms.ValidationError(gettext_lazy("เบอร์มือถือต้องขึ้นต้นด้วย 0"))
        return pp
