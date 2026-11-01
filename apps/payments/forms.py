from django import forms
from django.core.exceptions import ValidationError
from apps.payments.models import PaymentSlip, SlipVerificationStatus
from apps.core.services.media import sanitize_and_strip_image
from django.utils.translation import gettext as _, gettext_lazy


class SlipUploadForm(forms.ModelForm):
    """
    Form for tourists to upload bank transfer slip evidence.
    Validates image, strips EXIF, and checks for duplicate bank transfer references.
    """
    provider_reference = forms.CharField(
        label=gettext_lazy("รหัสอ้างอิงธุรกรรมธนาคาร (Transaction Ref)"),
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': gettext_lazy("เช่น 20261027XXXXXX (ระบุเพื่อความรวดเร็วในการตรวจสอบ)"),
        }),
        help_text=gettext_lazy("รหัสอ้างอิงที่ระบุบนสลิปของธนาคาร (ถ้ามี)")
    )

    image = forms.ImageField(
        label=gettext_lazy("รูปภาพสลิปการโอนเงิน"),
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': 'image/jpeg,image/png,image/webp',
            '@change': 'previewImage($event)',
        })
    )

    class Meta:
        model = PaymentSlip
        fields = ['image', 'provider_reference']

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'file'):
            return sanitize_and_strip_image(image)
        return image

    def clean_provider_reference(self):
        ref = self.cleaned_data.get('provider_reference')
        if ref:
            ref = ref.strip().upper()
            # Anti-Duplicate Check
            if PaymentSlip.objects.filter(
                provider_reference=ref,
                verification_status=SlipVerificationStatus.VERIFIED,
            ).exists():
                raise ValidationError(_("รหัสอ้างอิงสลิปนี้ถูกใช้งานและยืนยันการชำระเงินไปแล้วในระบบ"))
        return ref
