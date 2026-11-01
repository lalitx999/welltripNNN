from decimal import Decimal
from django import forms
from apps.services.models import FoodMenu, WellnessService, WellnessTimeSlot, FoodWellnessCategory
from apps.core.services.media import sanitize_and_strip_image
from django.utils.translation import gettext_lazy


class FoodMenuForm(forms.ModelForm):
    class Meta:
        model = FoodMenu
        fields = ['name', 'description', 'price', 'wellness_category', 'calorie_estimate', 'image']
        widgets = {
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("ชื่อเมนูสุขภาพ")}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '0.01'}),
            'wellness_category': forms.Select(attrs={'class': 'form-select'}),
            'calorie_estimate': forms.NumberInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น 250 kcal")}),
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
            'image': forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': 'image/jpeg,image/png,image/webp'}),
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': gettext_lazy("เช่น นวดประคบสมุนไพรสด")}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'price': forms.NumberInput(attrs={'class': 'form-control', 'min': 1, 'step': '0.01'}),
            'duration_minutes': forms.NumberInput(attrs={'class': 'form-control', 'min': 15, 'step': 15}),
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
            'date': forms.DateInput(attrs={'type': 'date', 'class': 'form-control'}),
            'start_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'end_time': forms.TimeInput(attrs={'type': 'time', 'class': 'form-control'}),
            'capacity_total': forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
        }
