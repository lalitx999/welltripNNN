from decimal import Decimal
from django import forms
from apps.accommodations.models import Accommodation, Room, RoomCooling, RoomPricingCalendar
from apps.core.services.media import sanitize_and_strip_image
from django.utils.translation import gettext_lazy


class AccommodationForm(forms.ModelForm):
    class Meta:
        model = Accommodation
        fields = ['name', 'profile_image', 'description', 'address', 'subdistrict', 'district', 'province', 'postal_code', 'google_maps_url']
        widgets = {
            'profile_image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp'}),
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'subdistrict': forms.TextInput(attrs={'class': 'form-control'}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'google_maps_url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น https://maps.app.goo.gl/... หรือ 15.1186, 104.3225")}),
        }

    def clean_profile_image(self):
        image = self.cleaned_data.get('profile_image')
        # Only re-encode a fresh upload; an unchanged existing file passes through
        if image and hasattr(image, 'content_type'):
            return sanitize_and_strip_image(image)
        return image


class RoomForm(forms.ModelForm):
    """A house in the homestay network: its type, guests and how it is priced."""

    class Meta:
        model = Room
        fields = ['name', 'cooling', 'capacity_people', 'pricing_mode', 'base_price_per_night', 'air_price_per_night', 'total_rooms_count']
        labels = {
            'name': gettext_lazy("ชื่อบ้าน"),
            'cooling': gettext_lazy("ประเภทห้อง"),
            'capacity_people': gettext_lazy("ผู้เข้าพักสูงสุด (คน)"),
            'pricing_mode': gettext_lazy("วิธีคิดราคา"),
            'base_price_per_night': gettext_lazy("ราคา (บาท/คืน)"),
            'air_price_per_night': gettext_lazy("ราคาห้องแอร์ (บาท/คืน)"),
            'total_rooms_count': gettext_lazy("จำนวนหลัง/ห้องแบบนี้"),
        }
        help_texts = {
            'base_price_per_night': gettext_lazy("ราคาที่คุณได้รับ ถ้ามีทั้งพัดลมและแอร์ ใส่ราคาห้องพัดลม ลูกค้าจะเห็นราคานี้บวกค่าบริการแพลตฟอร์ม"),
            'air_price_per_night': gettext_lazy("ใส่เฉพาะบ้านที่มีทั้งพัดลมและแอร์"),
        }
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น บ้านแม่บุญมา")}),
            'cooling': forms.Select(attrs={'class': 'form-select'}),
            'capacity_people': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'pricing_mode': forms.Select(attrs={'class': 'form-select'}),
            'base_price_per_night': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '1'}),
            'air_price_per_night': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '1'}),
            'total_rooms_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get('cooling') == RoomCooling.BOTH:
            if not cleaned.get('air_price_per_night'):
                self.add_error('air_price_per_night', gettext_lazy("บ้านที่มีทั้งพัดลมและแอร์ต้องใส่ราคาห้องแอร์ด้วย"))
        else:
            cleaned['air_price_per_night'] = None
        return cleaned


class RoomImageForm(forms.Form):
    """A room photo upload, re-encoded to strip EXIF and embedded payloads."""
    image = forms.ImageField(widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp'}))

    def clean_image(self):
        return sanitize_and_strip_image(self.cleaned_data['image'])


class RoomPricingCalendarForm(forms.ModelForm):
    class Meta:
        model = RoomPricingCalendar
        fields = ['date', 'price', 'available_count']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
            'available_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 0}),
        }
