from decimal import Decimal
from django import forms
from apps.accommodations.models import Accommodation, Room, RoomPricingCalendar
from apps.core.services.media import sanitize_and_strip_image


class AccommodationForm(forms.ModelForm):
    class Meta:
        model = Accommodation
        fields = ['name', 'description', 'address', 'subdistrict', 'district', 'province', 'postal_code']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'rows': 3}),
            'address': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'subdistrict': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'district': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'province': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'postal_code': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
        }


class RoomForm(forms.ModelForm):
    class Meta:
        model = Room
        fields = ['name', 'room_type', 'capacity_people', 'base_price_per_night', 'total_rooms_count']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'placeholder': 'เช่น ห้องระเบียงชมดาว'}),
            'room_type': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'capacity_people': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 1}),
            'base_price_per_night': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 1, 'step': '0.01'}),
            'total_rooms_count': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 1}),
        }


class RoomPricingCalendarForm(forms.ModelForm):
    class Meta:
        model = RoomPricingCalendar
        fields = ['date', 'price', 'available_count']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest'}),
            'price': forms.NumberInput(attrs={'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest', 'step': '0.01'}),
            'available_count': forms.NumberInput(attrs={'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest', 'min': 0}),
        }
