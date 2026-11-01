"""
Loads the Nov–Dec 2569 (2026) Sisaket events calendar published by the
Sisaket Chamber of Commerce. Safe to re-run: matches on title + start date.
Events are created as drafts; publish them from Admin Center → ปฏิทินกิจกรรม.
"""
from datetime import date

from django.core.management.base import BaseCommand

from apps.community.models import Event

PARK = ("สวนเฉลิมพระเกียรติฯ (เกาะห้วยน้ำคำ)", "Chaloem Phra Kiat Park (Huai Nam Kham Island)")
AQUARIUM = ("ลานหลังศรีสะเกษอควาเรียม เกาะห้วยน้ำคำ", "Behind Sisaket Aquarium, Huai Nam Kham Island")
C = Event.Category

EVENTS = [
    # (title, title_en, category, start, end, venue, date_note)
    ("การประกวดวงดนตรีพื้นบ้านโปงลาง \"ศรีศิลป์\"", "\"Sri Silp\" Pong Lang Folk Band Contest", C.CONTEST, date(2026, 11, 6), date(2026, 11, 7), PARK, None),
    ("เทศกาลกาแฟและดนตรี ครั้งที่ 4", "4th Sisaket Coffee & Music Festival", C.FOOD, date(2026, 11, 13), date(2026, 11, 15), AQUARIUM, None),
    ("ฟุตบอลคิงส์คัพ ครั้งที่ 52", "52nd King's Cup Football", C.SPORT, date(2026, 11, 14), date(2026, 11, 17),
     ("สนามกีฬาการกีฬาแห่งประเทศไทย จังหวัดศรีสะเกษ", "SAT Stadium, Sisaket"), None),
    ("งานฉลองเมือง 244 ปี ศรีสะเกษ", "Sisaket 244th Anniversary Celebration", C.FESTIVAL, date(2026, 11, 18), date(2026, 11, 22), PARK, None),
    ("การประกวดวงดนตรีลูกทุ่งแห่งประเทศไทย ชิงถ้วยพระราชทานฯ", "National Luk Thung Band Contest (Royal Trophy)", C.CONTEST, date(2026, 11, 21), date(2026, 11, 22), PARK, None),
    ("ลอยกระทง", "Loy Krathong", C.FESTIVAL, date(2026, 11, 23), date(2026, 11, 24), PARK, None),
    ("งานงิ้วประจำปี 2569", "Annual Chinese Opera 2026", C.FESTIVAL, date(2026, 11, 25), date(2026, 12, 2),
     ("ศาลเจ้าปู่ตาศรีสะเกษ", "Chao Pu Ta Shrine, Sisaket"), None),
    ("CAMP กลางเกาะ", "CAMP Klang Ko (Island Camp)", C.OUTDOOR, date(2026, 12, 12), date(2026, 12, 20), AQUARIUM,
     ("12–13 และ 19–20 ธ.ค. 2569", "12–13 & 19–20 Dec 2026")),
    ("การประกวดวงโยธวาทิตโลก ชิงถ้วยพระราชทานฯ แห่งประเทศไทย", "World Marching Band Contest of Thailand (Royal Trophy)", C.CONTEST, date(2026, 12, 16), date(2026, 12, 19), ("", ""), None),
    ("Sound of Sisaket 2026", "Sound of Sisaket 2026", C.MUSIC, date(2026, 12, 16), date(2026, 12, 20), ("", ""), None),
    ("ไทบ้านแลนด์ 7.0", "Thai Ban Land 7.0", C.MUSIC, date(2026, 12, 19), date(2026, 12, 19),
     ("ลานกิจกรรมไทบ้านแลนด์ อบต.น้ำคำ", "Thai Ban Land Grounds, Nam Kham SAO"), None),
]


class Command(BaseCommand):
    help = "Load the Nov–Dec 2569 Sisaket events calendar as drafts"

    def add_arguments(self, parser):
        parser.add_argument("--publish", action="store_true", help="Publish the events immediately")

    def handle(self, *args, publish=False, **options):
        created = 0
        for title, title_en, category, start, end, (venue, venue_en), note in EVENTS:
            note_th, note_en = note or ("", "")
            _, was_created = Event.objects.get_or_create(
                title=title,
                start_date=start,
                defaults={
                    "title_en": title_en,
                    "category": category,
                    "end_date": end,
                    "venue": venue,
                    "venue_en": venue_en,
                    "date_note": note_th,
                    "date_note_en": note_en,
                    "is_published": publish,
                },
            )
            created += was_created
        self.stdout.write(self.style.SUCCESS(f"Created {created} event(s), {len(EVENTS) - created} already existed."))
