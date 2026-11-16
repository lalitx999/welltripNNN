# WellTrip Thailand

เว็บไซต์ท่องเที่ยวเชิงสุขภาพของจังหวัดศรีสะเกษ รวมที่พัก บริการสุขภาพ สินค้า OTOP สถานที่ท่องเที่ยว และกิจกรรมในพื้นที่ไว้ในที่เดียว ผู้ใช้จอง ชำระเงินด้วยสลิปโอนเงิน และรับคำแนะนำจาก AI ได้ ส่วนพาร์ทเนอร์เปิดร้านและจัดการสินค้าของตัวเองได้

เว็บจริง: https://welltripthailand.com

## เทคโนโลยี

- **Backend:** Django 5.1–5.2, Python 3.12
- **ฐานข้อมูล:** PostgreSQL 16 บน production และ SQLite ตอนพัฒนาในเครื่อง
- **งานเบื้องหลัง:** Celery และ Redis ใช้กับการตรวจสลิปและการคืนสต็อกการจองที่ไม่ชำระเงิน
- **หน้าเว็บ:** Django templates, Bootstrap, Leaflet (แผนที่), Lucide (ไอคอน) เก็บไว้ใน `static/vendor` ไม่ต้อง build ด้วย Node
- **ภาษา:** ไทยและอังกฤษ ไฟล์แปลอยู่ใน `locale/`
- **บริการภายนอก:** EasySlip (ตรวจสลิป), Google OAuth (ล็อกอิน), DeepSeek / Gemini (AI), Hostinger SMTP (อีเมล)

## โครงสร้างโปรเจกต์

```
apps/
  accounts/            ผู้ใช้ ล็อกอิน Google ยืนยันอีเมล พาร์ทเนอร์ และหน้าแอดมิน
  accommodations/      ที่พัก
  services/            บริการสุขภาพและสปา
  otop/                สินค้า OTOP และร้านค้าของพาร์ทเนอร์
  bookings/            ตะกร้าและการจอง
  payments/            การชำระเงินและตรวจสลิป
  community/           สถานที่ท่องเที่ยว กิจกรรม และข่าว
  ai_recommendations/  แบบประเมินสุขภาพและคำแนะนำจาก AI
  core/                หน้าแรก หน้ารวม และคำสั่งช่วยเหลือ
config/                settings (base / dev / prod), urls, celery
templates/             HTML templates
static/                CSS, JS, รูป, ฟอนต์ และไลบรารี vendor
locale/                ไฟล์แปลภาษา
nginx/                 ค่า nginx สำหรับ production
scripts/backup.sh      สำรองฐานข้อมูลและ media บนเซิร์ฟเวอร์
```

## เริ่มพัฒนาในเครื่อง (Linux)

ต้องมี Python 3.12 และ venv:

```bash
sudo apt install python3.12-venv
```

สร้าง virtualenv และติดตั้งแพ็กเกจ:

```bash
python3.12 -m venv venv
```

```bash
./venv/bin/pip install -r requirements/dev.txt
```

สร้างไฟล์ `.env` จากตัวอย่าง แล้วแก้ค่าที่ต้องใช้:

```bash
cp .env.example .env
```

สร้างตารางในฐานข้อมูล แล้วเปิดเซิร์ฟเวอร์:

```bash
./venv/bin/python manage.py migrate
```

```bash
./venv/bin/python manage.py runserver 127.0.0.1:8000
```

เปิด http://127.0.0.1:8000

ถ้าไม่ได้ตั้ง `DATABASE_URL` ระบบจะใช้ SQLite (`db.sqlite3`) และถ้าไม่ได้ตั้ง `REDIS_URL` Celery จะรันงานทันทีในโปรเซสเดียวกัน ตอนพัฒนาจึงไม่ต้องลง PostgreSQL หรือ Redis ส่วนอีเมลจะแสดงใน console แทนการส่งจริง

### คำสั่งที่ใช้บ่อย

```bash
./venv/bin/python manage.py test
```

```bash
./venv/bin/python manage.py createsuperuser
```

```bash
./venv/bin/python manage.py compilemessages
```

นำเข้าข้อมูลสถานที่ท่องเที่ยวและกิจกรรมของศรีสะเกษ:

```bash
./venv/bin/python manage.py import_ttd_attractions
```

```bash
./venv/bin/python manage.py load_sisaket_events_2569
```

กิจกรรมจะถูกนำเข้าเป็นฉบับร่าง ถ้าต้องการเผยแพร่ทันทีให้เติม `--publish`

## ไฟล์ที่ไม่อยู่ใน git

`.env`, `db.sqlite3` และ `media/` (รูปที่อัปโหลดและสลิป) ไม่ถูกเก็บใน git เวลาย้ายเครื่องต้องคัดลอกไปเอง ห้าม commit `.env` เพราะมีรหัสผ่านและ API key

## Deploy

ระบบ production รันด้วย docker-compose (PostgreSQL, Redis, Gunicorn, Celery worker และ beat, nginx, Cloudflare Tunnel) ขั้นตอนทั้งหมดอยู่ใน [DEPLOY.md](DEPLOY.md)
