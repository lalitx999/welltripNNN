from decimal import Decimal
from django import forms
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot, FoodWellnessCategory
from apps.core.services.media import sanitize_and_strip_image


class FoodMenuForm(forms.ModelForm):
    class Meta:
        model = FoodMenu
        fields = ['name', 'description', 'price', 'wellness_category', 'calorie_estimate', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'placeholder': 'ชื่อเมนูสุขภาพ'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'rows': 2}),
            'price': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 1, 'step': '0.01'}),
            'wellness_category': forms.Select(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'calorie_estimate': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'placeholder': 'เช่น 250 kcal'}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'file'):
            return sanitize_and_strip_image(image)
        return image


class WellnessServiceForm(forms.ModelForm):
    class Meta:
        model = WellnessService
        fields = ['name', 'description', 'price', 'duration_minutes', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'placeholder': 'เช่น นวดประคบสมุนไพรสด'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'rows': 2}),
            'price': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 1, 'step': '0.01'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 15, 'step': 15}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'file'):
            return sanitize_and_strip_image(image)
        return image


class WellnessTimeSlotForm(forms.ModelForm):
    class Meta:
        model = WellnessTimeSlot
        fields = ['date', 'start_time', 'end_time', 'capacity_total']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest'}),
            'capacity_total': forms.NumberInput(attrs={'class': 'px-3 py-2 rounded-xl border border-gray-200 text-xs focus:ring-2 focus:ring-forest', 'min': 1}),
        }
