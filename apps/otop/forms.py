from decimal import Decimal
from django import forms
from apps.otop.models import OTOPProduct, OTOPCategory
from apps.core.services.media import sanitize_and_strip_image


class OTOPProductForm(forms.ModelForm):
    class Meta:
        model = OTOPProduct
        fields = ['name', 'category', 'description', 'price', 'stock_quantity', 'image']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'placeholder': 'ชื่อผลิตภัณฑ์ OTOP'}),
            'category': forms.Select(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'rows': 2}),
            'price': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 1, 'step': '0.01'}),
            'stock_quantity': forms.NumberInput(attrs={'class': 'w-full px-4 py-2.5 rounded-xl border border-gray-200 text-sm focus:ring-2 focus:ring-forest', 'min': 0}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if image and hasattr(image, 'file'):
            return sanitize_and_strip_image(image)
        return image


class StockAdjustmentForm(forms.Form):
    """Used by HTMX inline stock updater to adjust inventory quantities."""
    delta = forms.IntegerField(required=True)
