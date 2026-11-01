from decimal import Decimal
from django import forms
from apps.accommodations.models import Accommodation, Room, RoomPricingCalendar
from apps.core.services.media import sanitize_and_strip_image
from django.utils.translation import gettext_lazy


class AccommodationForm(forms.ModelForm):
    class Meta:
        model = Accommodation
        fields = ['name', 'description', 'address', 'subdistrict', 'district', 'province', 'postal_code', 'google_maps_url']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'subdistrict': forms.TextInput(attrs={'class': 'form-control'}),
            'district': forms.TextInput(attrs={'class': 'form-control'}),
            'province': forms.TextInput(attrs={'class': 'form-control'}),
            'postal_code': forms.TextInput(attrs={'class': 'form-control'}),
            'google_maps_url': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น https://maps.app.goo.gl/... หรือ 15.1186, 104.3225")}),
        }


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'room_type', 'capacity_people', 'base_price_per_night', 'total_rooms_count']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น ห้องระเบียงชมดาว")}),
            'room_type': forms.TextInput(attrs={'class': 'form-control'}),
            'capacity_people': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            'base_price_per_night': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '0.01'}),
            'total_rooms_count': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }


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
