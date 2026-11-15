"""Partner storefront: details and up to 3 photos, editable from sign-up onwards."""
from django.db import transaction
from django.utils.translation import gettext as _

from apps.accounts.models import MerchantProfile, MerchantShopImage
from apps.accounts.services.audit import record_audit_log


def add_shop_image(request, profile, image):
    """Returns (ok, message). Locks the profile so two uploads cannot both take the last slot."""
    with transaction.atomic():
        MerchantProfile.objects.select_for_update().filter(pk=profile.pk).first()
        count = profile.shop_images.count()
        if count >= MerchantShopImage.MAX_PER_SHOP:
            return False, _("ใส่รูปร้านได้สูงสุด {n} รูป กรุณาลบรูปเดิมก่อน").format(n=MerchantShopImage.MAX_PER_SHOP)
        shot = MerchantShopImage.objects.create(profile=profile, image=image, order=count)
    record_audit_log(request=request, action="CREATE", model_name="MerchantShopImage", object_id=str(shot.id),
                     changes={"business_name": profile.business_name})
    return True, _("เพิ่มรูปร้านแล้ว ({n}/{max})").format(n=count + 1, max=MerchantShopImage.MAX_PER_SHOP)


def delete_shop_image(request, profile, image_id):
    shot = profile.shop_images.filter(pk=image_id).first()
    if shot is None:
        return False, _("ไม่พบรูปนี้")
    with transaction.atomic():
        shot.image.delete(save=False)
        shot.delete()
        for index, rest in enumerate(profile.shop_images.order_by("order", "id")):
            if rest.order != index:
                rest.order = index
                rest.save(update_fields=["order"])
    record_audit_log(request=request, action="DELETE", model_name="MerchantShopImage", object_id=str(image_id))
    return True, _("ลบรูปแล้ว")


def make_cover(request, profile, image_id):
    """Moves a photo to the front: the first photo is the shop's cover."""
    images = list(profile.shop_images.order_by("order", "id"))
    chosen = next((i for i in images if i.pk == int(image_id)), None) if str(image_id).isdigit() else None
    if chosen is None:
        return False, _("ไม่พบรูปนี้")
    with transaction.atomic():
        for index, shot in enumerate([chosen] + [i for i in images if i.pk != chosen.pk]):
            if shot.order != index:
                shot.order = index
                shot.save(update_fields=["order"])
    return True, _("ตั้งเป็นรูปหน้าปกร้านแล้ว")
