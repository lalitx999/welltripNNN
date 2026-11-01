from django import template
from django.utils.translation import get_language

register = template.Library()


@register.filter
def loc(obj, field):
    """
    Bilingual model fields: `{{ event|loc:"title" }}` gives title_en when the
    site is in English and it is filled in, otherwise the Thai `title`.
    """
    if (get_language() or "").startswith("en"):
        english = getattr(obj, f"{field}_en", "")
        if english:
            return english
    return getattr(obj, field, "")


_TH_MONTHS = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.", "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]
_EN_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _is_english():
    return (get_language() or "").startswith("en")


@register.filter
def month_label(day):
    """'พฤศจิกายน 2569' or 'November 2026' for a calendar month heading."""
    if _is_english():
        return day.strftime("%B %Y")
    full = ["มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
            "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม"]
    return f"{full[day.month - 1]} {day.year + 543}"


@register.filter
def event_dates(event):
    """
    Short date range in the active language, Thai years in B.E.:
    '6–7 พ.ย. 2569', '25 พ.ย. – 2 ธ.ค. 2569', '6–7 Nov 2026'. date_note wins when set.
    """
    note = loc(event, "date_note")
    if note:
        return note
    months = _EN_MONTHS if _is_english() else _TH_MONTHS
    start, end = event.start_date, event.end_date
    year = end.year if _is_english() else end.year + 543
    if start == end:
        return f"{start.day} {months[start.month - 1]} {year}"
    if (start.year, start.month) == (end.year, end.month):
        return f"{start.day}–{end.day} {months[end.month - 1]} {year}"
    return f"{start.day} {months[start.month - 1]} – {end.day} {months[end.month - 1]} {year}"


# Sisaket districts and the province: stored in Thai, shown in English on the EN site
_PLACE_EN = {
    "ศรีสะเกษ": "Sisaket", "จังหวัดศรีสะเกษ": "Sisaket Province",
    "เมืองศรีสะเกษ": "Mueang Sisaket", "กันทรลักษ์": "Kantharalak", "กันทรารมย์": "Kanthararom",
    "ขุนหาญ": "Khun Han", "ราษีไศล": "Rasi Salai", "อุทุมพรพิสัย": "Uthumphon Phisai",
    "ปรางค์กู่": "Prang Ku", "ขุขันธ์": "Khukhan", "ไพรบึง": "Phrai Bueng", "ห้วยทับทัน": "Huai Thap Than",
    "โนนคูณ": "Non Khun", "ศรีรัตนะ": "Si Rattana", "น้ำเกลี้ยง": "Nam Kliang", "วังหิน": "Wang Hin",
    "ภูสิงห์": "Phu Sing", "เมืองจันทร์": "Mueang Chan", "เบญจลักษ์": "Benchalak", "พยุห์": "Phayu",
    "โพธิ์ศรีสุวรรณ": "Pho Si Suwan", "ศิลาลาด": "Sila Lat", "บึงบูรพ์": "Bueng Bun", "ยางชุมน้อย": "Yang Chum Noi",
}


@register.filter
def place_name(value):
    """English name for a Sisaket district/province on the EN site; anything else unchanged."""
    if _is_english() and value:
        return _PLACE_EN.get(str(value).strip(), value)
    return value
