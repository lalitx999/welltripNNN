"""Thai banks a partner can receive payouts to (admins transfer after settling the books)."""
from django.db import models
from django.utils.translation import gettext_lazy


class ThaiBank(models.TextChoices):
    KBANK = "KBANK", gettext_lazy("ธนาคารกสิกรไทย")
    BBL = "BBL", gettext_lazy("ธนาคารกรุงเทพ")
    KTB = "KTB", gettext_lazy("ธนาคารกรุงไทย")
    SCB = "SCB", gettext_lazy("ธนาคารไทยพาณิชย์")
    BAY = "BAY", gettext_lazy("ธนาคารกรุงศรีอยุธยา")
    TTB = "TTB", gettext_lazy("ธนาคารทหารไทยธนชาต (ttb)")
    GSB = "GSB", gettext_lazy("ธนาคารออมสิน")
    BAAC = "BAAC", gettext_lazy("ธนาคารเพื่อการเกษตรและสหกรณ์การเกษตร (ธ.ก.ส.)")
    GHB = "GHB", gettext_lazy("ธนาคารอาคารสงเคราะห์")
    UOB = "UOB", gettext_lazy("ธนาคารยูโอบี")
    CIMB = "CIMB", gettext_lazy("ธนาคารซีไอเอ็มบี ไทย")
    LHB = "LHB", gettext_lazy("ธนาคารแลนด์ แอนด์ เฮ้าส์")
    KKP = "KKP", gettext_lazy("ธนาคารเกียรตินาคินภัทร")
    TISCO = "TISCO", gettext_lazy("ธนาคารทิสโก้")
    ISBT = "ISBT", gettext_lazy("ธนาคารอิสลามแห่งประเทศไทย")


def mask_number(value: str) -> str:
    """Keep only the last 4 digits, for audit logs and emails."""
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    if not digits:
        return ""
    return "x" * max(0, len(digits) - 4) + digits[-4:]
