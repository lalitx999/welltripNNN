from django import forms

from apps.community.models import Event, MapLocation
from apps.core.services.media import sanitize_and_strip_image
from django.utils.translation import gettext as _, gettext_lazy


class EventForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = [
            "title", "title_en", "category", "summary", "summary_en",
            "start_date", "end_date", "date_note", "date_note_en",
            "venue", "venue_en", "google_maps_url", "check_in_point",
            "organizer", "source_url", "image", "is_published",
        ]
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "title_en": forms.TextInput(attrs={"class": "form-control"}),
            "category": forms.Select(attrs={"class": "form-select"}),
            "summary": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "summary_en": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "start_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "end_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}, format="%Y-%m-%d"),
            "date_note": forms.TextInput(attrs={"class": "form-control", "placeholder": gettext_lazy("12–13 และ 19–20 ธ.ค.")}),
            "date_note_en": forms.TextInput(attrs={"class": "form-control", "placeholder": "12–13 & 19–20 Dec"}),
            "venue": forms.TextInput(attrs={"class": "form-control"}),
            "venue_en": forms.TextInput(attrs={"class": "form-control"}),
            "google_maps_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://maps.app.goo.gl/..."}),
            "check_in_point": forms.Select(attrs={"class": "form-select"}),
            "organizer": forms.TextInput(attrs={"class": "form-control"}),
            "source_url": forms.URLInput(attrs={"class": "form-control"}),
            "image": forms.ClearableFileInput(attrs={"class": "form-control", "accept": "image/jpeg,image/png,image/webp"}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["check_in_point"].queryset = MapLocation.objects.filter(is_active=True).only("id", "title").order_by("title")

    def clean_image(self):
        image = self.cleaned_data.get("image")
        # Only re-encode fresh uploads; an unchanged existing file passes through
        if image and hasattr(image, "content_type"):
            return sanitize_and_strip_image(image)
        return image

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get("start_date"), cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", _("วันสิ้นสุดต้องไม่ก่อนวันเริ่มงาน"))
        return cleaned
