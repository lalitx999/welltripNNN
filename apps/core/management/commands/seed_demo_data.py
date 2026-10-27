import uuid
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from datetime import timedelta
from apps.accounts.models import User, UserRoles
from apps.accommodations.models import Accommodation, Room, RoomPricingCalendar, AccommodationStatus
from apps.services.models import FoodMenu, FoodWellnessCategory, WellnessService, WellnessTimeSlot
from apps.otop.models import OTOPProduct, OTOPCategory
from apps.community.models import MapLocation, MapLocationCategory, Coupon, EditorialEntry


class Command(BaseCommand):
    help = "Seeds initial demo data for WellTrip Sisaket platform"

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding WellTrip demo data...")

        # 1. Users
        admin_user, _ = User.objects.get_or_create(
            email="admin@welltrip.com",
            defaults={
                "username": "admin",
                "first_name": "ผู้ดูแลระบบ",
                "last_name": "WellTrip",
                "role": UserRoles.SUPER_ADMIN,
                "is_staff": True,
                "is_superuser": True,
                "email_verified": True,
            },
        )
        admin_user.set_password("admin12345")
        admin_user.save()

        merchant_user, _ = User.objects.get_or_create(
            email="merchant@welltrip.com",
            defaults={
                "username": "merchant_homestay",
                "first_name": "บุญมี",
                "last_name": "รักษ์ถิ่น",
                "role": UserRoles.HOMESTAY_OWNER,
                "phone_number": "0812345678",
                "email_verified": True,
            },
        )
        merchant_user.set_password("merchant12345")
        merchant_user.save()

        restaurant_user, _ = User.objects.get_or_create(
            email="restaurant@welltrip.com",
            defaults={
                "username": "merchant_food",
                "first_name": "มาลี",
                "last_name": "ครัวสุขภาพ",
                "role": UserRoles.RESTAURANT_OWNER,
                "phone_number": "0898765432",
                "email_verified": True,
            },
        )
        restaurant_user.set_password("merchant12345")
        restaurant_user.save()

        wellness_user, _ = User.objects.get_or_create(
            email="wellness@welltrip.com",
            defaults={
                "username": "merchant_wellness",
                "first_name": "สมคิด",
                "last_name": "นวดไทยโบราณ",
                "role": UserRoles.WELLNESS_OWNER,
                "phone_number": "0865432198",
                "email_verified": True,
            },
        )
        wellness_user.set_password("merchant12345")
        wellness_user.save()

        otop_user, _ = User.objects.get_or_create(
            email="otop@welltrip.com",
            defaults={
                "username": "merchant_otop",
                "first_name": "สมปอง",
                "last_name": "ไหมมัดหมี่",
                "role": UserRoles.OTOP_OWNER,
                "phone_number": "0843219876",
                "email_verified": True,
            },
        )
        otop_user.set_password("merchant12345")
        otop_user.save()

        tourist_user, _ = User.objects.get_or_create(
            email="tourist@welltrip.com",
            defaults={
                "username": "tourist_somchai",
                "first_name": "สมชาย",
                "last_name": "สายเที่ยวสุขภาวะ",
                "role": UserRoles.TOURIST,
                "phone_number": "0851122334",
                "email_verified": True,
            },
        )
        tourist_user.set_password("tourist12345")
        tourist_user.save()

        # 2. Accommodations & Rooms
        acc1, _ = Accommodation.objects.get_or_create(
            name="บ้านสวนริมธาร ขุนหาญ อีโค่คอทเทจ",
            defaults={
                "owner": merchant_user,
                "description": "โฮมสเตย์เชิงเกษตรอินทรีย์ริมธารน้ำธรรมชาติขุนหาญ สัมผัสวิถีชีวิตชาวสวนทุเรียนภูเขาไฟ อากาศบริสุทธิ์ อาหารสุขภาพจากวัตถุดิบสวนหลังบ้าน",
                "address": "124 หมู่ 4 ต.บักดอง",
                "subdistrict": "บักดอง",
                "district": "ขุนหาญ",
                "province": "ศรีสะเกษ",
                "postal_code": "33150",
                "latitude": Decimal("14.6185200"),
                "longitude": Decimal("104.4258900"),
                "status": AccommodationStatus.ACTIVE,
            },
        )
        room1, _ = Room.objects.get_or_create(
            accommodation=acc1,
            name="เรือนริมธาร วิวสวนทุเรียนภูเขาไฟ",
            defaults={
                "room_type": "Eco-Villa",
                "capacity_people": 2,
                "base_price_per_night": Decimal("1250.00"),
                "total_rooms_count": 4,
                "is_active": True,
            },
        )
        room2, _ = Room.objects.get_or_create(
            accommodation=acc1,
            name="เรือนไม้ครอบครัว พักผ่อนธรรมชาติ",
            defaults={
                "room_type": "Family Cottage",
                "capacity_people": 4,
                "base_price_per_night": Decimal("2400.00"),
                "total_rooms_count": 2,
                "is_active": True,
            },
        )

        # Seed Room Pricing Calendars for next 14 days
        today = timezone.localdate()
        for i in range(14):
            d = today + timedelta(days=i)
            RoomPricingCalendar.objects.get_or_create(
                room=room1,
                date=d,
                defaults={
                    "price": room1.base_price_per_night,
                    "available_count": room1.total_rooms_count,
                },
            )
            RoomPricingCalendar.objects.get_or_create(
                room=room2,
                date=d,
                defaults={
                    "price": room2.base_price_per_night,
                    "available_count": room2.total_rooms_count,
                },
            )

        acc2, _ = Accommodation.objects.get_or_create(
            name="เฮือนภูไฟ ฟาร์มสเตย์ & เวลเนส กันทรลักษ์",
            defaults={
                "owner": merchant_user,
                "description": "ที่พักสุขภาพท่ามกลางสวนเกษตรผสมผสานดินภูเขาไฟ ใกล้อุทยานแห่งชาติเขาพระวิหาร ผ่อนคลายด้วยโปรแกรมดีท็อกซ์ธรรมชาติ",
                "address": "88 หมู่ 7 ต.เสาธงชัย",
                "subdistrict": "เสาธงชัย",
                "district": "กันทรลักษ์",
                "province": "ศรีสะเกษ",
                "postal_code": "33110",
                "latitude": Decimal("14.5421000"),
                "longitude": Decimal("104.7189000"),
                "status": AccommodationStatus.ACTIVE,
            },
        )
        room3, _ = Room.objects.get_or_create(
            accommodation=acc2,
            name="พาวิลเลียนดินเผา ดีไซน์รับลมธรรมชาติ",
            defaults={
                "room_type": "Clay Pavilion",
                "capacity_people": 2,
                "base_price_per_night": Decimal("1800.00"),
                "total_rooms_count": 3,
                "is_active": True,
            },
        )
        for i in range(14):
            d = today + timedelta(days=i)
            RoomPricingCalendar.objects.get_or_create(
                room=room3,
                date=d,
                defaults={
                    "price": room3.base_price_per_night,
                    "available_count": room3.total_rooms_count,
                },
            )

        # 3. Healthy Dining
        FoodMenu.objects.get_or_create(
            name="แกงอ่อมปลาคังสมุนไพรพื้นบ้าน (โซเดียมต่ำ)",
            defaults={
                "owner": restaurant_user,
                "description": "ปลาคังสดจากลำน้ำมูล ปรุงด้วยสมุนไพรสด 7 ชนิด ปราศจากผงชูรสและลดโซเดียม 50% เสิร์ฟพร้อมข้าวกล้องหอมมะลิศรีสะเกษ",
                "price": Decimal("180.00"),
                "wellness_category": FoodWellnessCategory.LOW_SODIUM,
                "calorie_estimate": 280,
                "is_available": True,
            },
        )
        FoodMenu.objects.get_or_create(
            name="สลัดผักออร์แกนิกดินภูเขาไฟ & น้ำสลัดหอมแดงศรีสะเกษ GI",
            defaults={
                "owner": restaurant_user,
                "description": "ผักสลัดสดกรอบจากแปลงเกษตรอินทรีย์ขุนหาญ คลุกเคล้าน้ำสลัดสูตรพิเศษจากหอมแดง GI ศรีสะเกษ รสชาติกลมกล่อมดีต่อหัวใจ",
                "price": Decimal("150.00"),
                "wellness_category": FoodWellnessCategory.ORGANIC,
                "calorie_estimate": 210,
                "is_available": True,
            },
        )

        # 4. Wellness Treatments
        well1, _ = WellnessService.objects.get_or_create(
            name="นวดแผนไทยสมุนไพรโบราณ & ประคบร้อนสมุนไพรศรีสะเกษ",
            defaults={
                "owner": wellness_user,
                "description": "นวดกดจุดคลายกล้ามเนื้อตามศาสตร์การแพทย์แผนไทย ผสานลูกประคบสมุนไพรอินทรีย์สด ช่วยบรรเทาอาการออฟฟิศซินโดรมและกระตุ้นการไหลเวียนโลหิต",
                "duration_minutes": 90,
                "price": Decimal("750.00"),
                "is_active": True,
            },
        )
        well2, _ = WellnessService.objects.get_or_create(
            name="อบสมุนไพรพื้นบ้านดีท็อกซ์ & นวดอโรมาน้ำมันรำข้าวอินทรีย์",
            defaults={
                "owner": wellness_user,
                "description": "เข้ากระโจมอบไอสมุนไพรขมิ้น ไพล ตะไคร้ และใบมะขาม ตามด้วยนวดน้ำมันรำข้าวบำรุงผิวพรรณอย่างล้ำลึก",
                "duration_minutes": 60,
                "price": Decimal("650.00"),
                "is_active": True,
            },
        )

        # Time slots
        from datetime import time
        for i in range(7):
            d = today + timedelta(days=i)
            WellnessTimeSlot.objects.get_or_create(
                service=well1,
                date=d,
                start_time=time(10, 0),
                defaults={
                    "end_time": time(11, 30),
                    "capacity_total": 4,
                    "capacity_available": 4,
                    "is_available": True,
                },
            )
            WellnessTimeSlot.objects.get_or_create(
                service=well1,
                date=d,
                start_time=time(14, 0),
                defaults={
                    "end_time": time(15, 30),
                    "capacity_total": 4,
                    "capacity_available": 4,
                    "is_available": True,
                },
            )

        # 5. OTOP Products
        OTOPProduct.objects.get_or_create(
            name="ผ้าไหมมัดหมี่ลายลูกแก้ว ย้อมสีธรรมชาติมะเกลือ",
            defaults={
                "owner": otop_user,
                "category": OTOPCategory.TEXTILE,
                "description": "ผ้าไหมแท้ทอมือ 100% ลายเอกลักษณ์ประจำจังหวัดศรีสะเกษ ย้อมสีดำขลับจากผลมะเกลือธรรมชาติ เนื้อผ้านุ่มเงางาม ทนทาน",
                "price": Decimal("2850.00"),
                "stock_quantity": 15,
                "is_active": True,
            },
        )
        OTOPProduct.objects.get_or_create(
            name="หอมแดงศรีสะเกษ GI เกรดคัดพิเศษ อบแห้งพร้อมปรุง",
            defaults={
                "owner": otop_user,
                "category": OTOPCategory.HERBAL_PRODUCT,
                "description": "หอมแดงสิ่งบ่งชี้ทางภูมิศาสตร์ (GI) ปลูกในดินภูเขาไฟ กลิ่นหอมฉุนเด่นชัด อุดมด้วยสารต้านอนุมูลอิสระเควอร์ซิทีน บรรจุสุญญากาศ",
                "price": Decimal("190.00"),
                "stock_quantity": 80,
                "is_active": True,
            },
        )

        # 6. Community Map & Passport Checkpoints
        MapLocation.objects.get_or_create(
            title="น้ำตกสำโรงเกียรติ (Samrong Kiat Waterfall)",
            defaults={
                "category": MapLocationCategory.PHOTO_SPOT,
                "latitude": Decimal("14.5824500"),
                "longitude": Decimal("104.4756200"),
                "address": "เขตรักษาพันธุ์สัตว์ป่าพนมดงรัก ต.บักดอง อ.ขุนหาญ จ.ศรีสะเกษ",
                "qr_secret": "PASSPORT-SISAKET-WATERFALL-SAMRONG-01",
                "is_active": True,
            },
        )
        MapLocation.objects.get_or_create(
            title="ปราสาทสระกำแพงใหญ่ (Prasat Sa Kamphaeng Yai)",
            defaults={
                "category": MapLocationCategory.PHOTO_SPOT,
                "latitude": Decimal("15.1012300"),
                "longitude": Decimal("104.1489200"),
                "address": "วัดสระกำแพงใหญ่ ต.สระกำแพงใหญ่ อ.อุทุมพรพิสัย จ.ศรีสะเกษ",
                "qr_secret": "PASSPORT-SISAKET-TEMPLE-KAMPHAENG-02",
                "is_active": True,
            },
        )
        MapLocation.objects.get_or_create(
            title="สวนทุเรียนภูเขาไฟ ไร่ตระกูลลี ขุนหาญ",
            defaults={
                "category": MapLocationCategory.HOMESTAY,
                "latitude": Decimal("14.6190000"),
                "longitude": Decimal("104.4260000"),
                "address": "ต.บักดอง อ.ขุนหาญ จ.ศรีสะเกษ",
                "qr_secret": "PASSPORT-SISAKET-DURIAN-VOLCANO-03",
                "is_active": True,
            },
        )
        MapLocation.objects.get_or_create(
            title="ศูนย์หัตถกรรมทอผ้าไหมบ้านโนนกอง",
            defaults={
                "category": MapLocationCategory.OTOP,
                "latitude": Decimal("15.1245000"),
                "longitude": Decimal("104.3289000"),
                "address": "ต.กระแชง อ.กันทรลักษ์ จ.ศรีสะเกษ",
                "qr_secret": "PASSPORT-SISAKET-SILK-CRAFT-04",
                "is_active": True,
            },
        )

        # 7. Coupons & Promo Codes
        Coupon.objects.get_or_create(
            code="WELLTRIP100",
            defaults={
                "discount_amount": Decimal("100.00"),
                "min_purchase": Decimal("500.00"),
                "expires_at": timezone.now() + timedelta(days=365),
                "is_active": True,
            },
        )
        Coupon.objects.get_or_create(
            code="SISAKET50",
            defaults={
                "discount_amount": Decimal("50.00"),
                "min_purchase": Decimal("300.00"),
                "expires_at": timezone.now() + timedelta(days=365),
                "is_active": True,
            },
        )

        # 8. Editorial Stories & Community Wisdom
        EditorialEntry.objects.get_or_create(
            title="การฟื้นฟูวิถีย้อมผ้าไหมสีมะเกลือโบราณ ชุมชนบ้านโนนกอง ศรีสะเกษ",
            defaults={
                "kind": EditorialEntry.Kind.STORY,
                "title_en": "Reviving the Ancient Ebony-Dyed Silk Heritage of Ban Non Kong",
                "summary": "สืบสานภูมิปัญญาการย้อมผ้าไหมด้วยผลมะเกลือธรรมชาติ ภูมิปัญญาอีสานใต้ที่ให้สีดำสนิท นุ่ม เงางาม และเป็นมิตรต่อสิ่งแวดล้อม",
                "body": (
                    "ชุมชนบ้านโนนกอง อำเภอกันทรลักษ์ จังหวัดศรีสะเกษ เป็นแหล่งทอผ้าไหมมัดหมี่โบราณที่สืบทอดกันมากว่าร้อยปี "
                    "เอกลักษณ์อันเลื่องชื่อคือ 'การย้อมมะเกลือ' โดยใช้ผลมะเกลือสดจากต้นในชุมชน นำมาตำและหมักจนเกิดสีดำสนิทธรรมชาติ "
                    "ต้องผ่านกระบวนการย้อมและตากแดดซ้ำๆ กว่า 30-40 แดด เพื่อให้เม็ดสีแทรกซึมลึกสู่เส้นไหม "
                    "ผ้าไหมย้อมมะเกลือของที่นี่จึงไม่เพียงแต่มีสีดำขลับสง่างาม แต่ยังมีคุณสมบัตินุ่ม ลื่นมือ ยิ่งซักยิ่งเงา "
                    "และที่สำคัญคือกระบวนการทั้งหมดไม่ใช้สารเคมีสังเคราะห์แม้แต่น้อย ช่วยรักษาสิ่งแวดล้อมและสุขภาพของช่างทอ"
                ),
                "location": "อ.กันทรลักษ์ จ.ศรีสะเกษ",
                "image_url": "/static/images/cocoa_craft_sisaket.jpg",
                "is_published": True,
            },
        )
        EditorialEntry.objects.get_or_create(
            title="มหัศจรรย์ดินภูเขาไฟ: ทำไมทุเรียนและหอมแดงขุนหาญถึงมีเอกลักษณ์ GI",
            defaults={
                "kind": EditorialEntry.Kind.COMMUNITY,
                "title_en": "The Volcanic Soil Miracle: Why Sisaket Durian & Shallots Earned GI Status",
                "summary": "ดินแดนแห่งภูเขาไฟโบราณที่อุดมด้วยแร่ธาตุโพแทสเซียม ฟอสฟอรัส และกำมะถันธรรมชาติ รังสรรค์ผลผลิตเกษตรอินทรีย์ระดับโลก",
                "body": (
                    "อำเภอขุนหาญและอำเภอกันทรลักษ์ เป็นพื้นที่ที่เคยเป็นแนวภูเขาไฟโบราณเมื่อหลายล้านปีก่อน "
                    "ทำให้ดินในแถบนี้เป็นดินสีแดงร่วนซุยที่อุดมสมบูรณ์ไปด้วยแร่ธาตุอาหารพืชธรรมชาติอย่างหนาแน่น "
                    "ส่งผลให้ 'ทุเรียนภูเขาไฟศรีสะเกษ' มีเนื้อแห้ง เนียนนุ่ม ละเอียด หวานมัน กลิ่นไม่ฉุนรุนแรง "
                    "ขณะที่ 'หอมแดงศรีสะเกษ' มีเปลือกบาง สีแดงเข้ม กลิ่นหอมฉุนและมีสารเควอร์ซิทีนสูงกว่าปกติ "
                    "การท่องเที่ยวเชิงเกษตรที่นี่จึงเปิดโอกาสให้นักท่องเที่ยวได้เด็ดผลไม้สดจากต้น และเรียนรู้วิถีเกษตรอินทรีย์ปลอดสารพิษอย่างแท้จริง"
                ),
                "location": "อ.ขุนหาญ จ.ศรีสะเกษ",
                "image_url": "/static/images/sisaket-nature-concept.webp",
                "is_published": True,
            },
        )
        EditorialEntry.objects.get_or_create(
            title="ปราสาทสระกำแพงใหญ่: อารยธรรมหินทรายพันปีและสปิริตแห่งอีสานใต้",
            defaults={
                "kind": EditorialEntry.Kind.ATTRACTION,
                "title_en": "Prasat Sa Kamphaeng Yai: Millennium-Old Sandstone Heritage",
                "summary": "โบราณสถานศิลปะขอมโบราณที่สมบูรณ์และงดงามที่สุดแห่งหนึ่งในจังหวัดศรีสะเกษ ศูนย์รวมจิตวิญญาณและประวัติศาสตร์ท้องถิ่น",
                "body": (
                    "ปราสาทสระกำแพงใหญ่ หรือวัดสระกำแพงใหญ่ ตั้งอยู่ที่อำเภออุทุมพรพิสัย ก่อสร้างขึ้นในราวพุทธศตวรรษที่ 16 "
                    "เพื่อเป็นเทวาลัยตามคติศาสนาฮินดู ตัวปราสาทประกอบด้วยปรางค์ก่อด้วยอิฐและหินทราย 3 องค์บนฐานศิลาแลงเดียวกัน "
                    "ลวดลายทับหลังและหน้าบันสลักเสลาด้วยความประณีต เช่น ภาพพระศิวะร่ายรำ และพระนารายณ์บรรทมสินธุ์ "
                    "สะท้อนถึงการผสมผสานทางวัฒนธรรมและภูมิปัญญาเชิงช่างโบราณที่สืบเนื่องมาจนถึงวิถีชุมชนรอบข้างในปัจจุบัน"
                ),
                "location": "อ.อุทุมพรพิสัย จ.ศรีสะเกษ",
                "image_url": "/static/images/attractions/prasat-sa-kamphaeng-yai.jpg",
                "is_published": True,
            },
        )

        self.stdout.write(self.style.SUCCESS("WellTrip demo data seeded successfully!"))

