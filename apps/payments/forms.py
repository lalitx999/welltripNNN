from django import forms
from django.core.exceptions import ValidationError
from apps.payments.models import PaymentSlip, SlipVerificationStatus
from apps.core.services.media import sanitize_and_strip_image


class SlipUploadForm(forms.ModelForm):
    """
    Form for tourists to upload bank transfer slip evidence.
    Validates image, strips EXIF, and checks for duplicate bank transfer references.
    """
    provider_reference = forms.CharField(
        label="รหัสอ้างอิงธุรกรรมธนาคาร (Transaction Ref)",
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest font-mono',
            'placeholder': 'เช่น 20261027XXXXXX (ระบุเพื่อความรวดเร็วในการตรวจสอบ)',
        }),
        help_text="รหัสอ้างอิงที่ระบุบนสลิปของธนาคาร (ถ้ามี)"
    )

    image = forms.ImageField(
        label="รูปภาพสลิปการโอนเงิน",
        required=True,
        widget=forms.FileInput(attrs={
            'class': 'block w-full text-xs text-slate-500 file:mr-4 file:py-2.5 file:px-4 file:rounded-xl file:border-0 file:text-xs file:font-semibold file:bg-forest file:text-white hover:file:bg-forest-dark cursor-pointer',
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
                raise ValidationError("รหัสอ้างอิงสลิปนี้ถูกใช้งานและยืนยันการชำระเงินไปแล้วในระบบ")
        return ref
