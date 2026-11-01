# Deploy WellTrip ขึ้น VPS

ระบบมี 4 container: `db` (PostgreSQL 16), `redis`, `backend` (Django + Gunicorn) และ `nginx`
ตอน start `backend` จะรัน `migrate` และ `collectstatic` ให้อัตโนมัติ (ดูใน `docker-entrypoint.sh`)

พอร์ต 80/443 บน VPS นี้เป็นของโปรเจคอื่น nginx ของ WellTrip จึงรับที่พอร์ต **8443** แล้วให้ Cloudflare ส่งต่อมา:

```
ผู้ใช้ → https://welltripthailand.com (Cloudflare :443) → VPS:8443 (welltrip_nginx) → backend
```

## 0. เตรียมก่อนเริ่ม

- โดเมนต้องใช้ DNS ของ Cloudflare
- ติดตั้ง Docker บน VPS แล้ว และเปิดพอร์ต 8443 ใน firewall

```bash
sudo ufw allow 8443/tcp
```

## 1. ดึงโค้ดและสร้าง `.env`

```bash
git clone https://github.com/lalitx999/welltripNNN.git welltrip && cd welltrip
```

```bash
cp .env.example .env && chmod 600 .env
```

แก้ `.env` (`nano .env`) ให้ครบอย่างน้อยค่าต่อไปนี้:

| ตัวแปร | ค่าที่ใส่ |
|---|---|
| `DJANGO_SECRET_KEY` | ใช้ค่าจาก `openssl rand -hex 32` |
| `DJANGO_ALLOWED_HOSTS` | `welltripthailand.com,www.welltripthailand.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://welltripthailand.com,https://www.welltripthailand.com` |
| `POSTGRES_PASSWORD` | ใช้ค่าจาก `openssl rand -hex 24` (ใช้แค่ตัวอักษรและตัวเลข) |
| `SLIP_PROVIDER_API_KEY` | key **ใหม่** ของ EasySlip |
| `EMAIL_HOST_PASSWORD` | รหัสอีเมล **ใหม่** |
| `PAYEE_*`, `GOOGLE_OAUTH_CLIENT_IDS`, `ADMIN_EMAIL` | ค่าจริงของคุณ |

ไม่ต้องใส่ `DATABASE_URL` และ `REDIS_URL` เพราะ docker-compose สร้างให้เอง

## 2. ตั้งค่า Cloudflare

1. **DNS:** ตั้ง A record ของ `@` และ `www` ให้ชี้ไปที่ IP ของ VPS และเปิด Proxy เป็น **เมฆสีส้ม**
2. **Origin Certificate:** ไปที่ SSL/TLS → Origin Server → Create Certificate
   ใช้ค่า default (RSA, `*.welltripthailand.com` และ `welltripthailand.com`, อายุ 15 ปี) แล้ววางไฟล์บน VPS:

```bash
mkdir -p nginx/certs && nano nginx/certs/fullchain.pem
```

วางส่วน **Origin Certificate** ลงไปแล้ว save จากนั้นเปิดไฟล์ key:

```bash
nano nginx/certs/privkey.pem
```

วางส่วน **Private Key** ลงไปแล้ว save จากนั้นจำกัดสิทธิ์ไฟล์:

```bash
chmod 600 nginx/certs/privkey.pem
```

3. **SSL mode:** SSL/TLS → Overview → ตั้งเป็น **Full (strict)**
4. **Origin Rule (ส่งต่อไปพอร์ต 8443):** Rules → Origin Rules → Create rule
   - ตั้งเงื่อนไข: Hostname **is in** `welltripthailand.com`, `www.welltripthailand.com`
   - ตั้ง Destination Port → Rewrite to **8443**

## 3. ย้ายข้อมูลเดิมจาก homeserver (ข้ามขั้นนี้ได้ถ้าจะเริ่มฐานข้อมูลใหม่)

บน **homeserver**: dump ฐานข้อมูลและแพ็กไฟล์ media

```bash
docker exec shared-postgres pg_dump -U postgres -Fc welltrip_db > welltrip.dump
```

```bash
tar czf welltrip-media.tgz -C /mnt/hdd_backup/welltrip/media .
```

คัดลอกทั้งสองไฟล์ไปไว้ในโฟลเดอร์ `welltrip` บน VPS (เช่นใช้ `scp`) จากนั้นบน **VPS** ให้รัน:

```bash
docker compose up -d db
```

```bash
docker compose exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --no-acl' < welltrip.dump
```

## 4. เปิดระบบ

```bash
docker compose up -d --build
```

```bash
docker compose logs -f backend nginx
```

ถ้าย้ายไฟล์ media มาจากขั้นที่ 3 ให้แตกไฟล์เข้า volume:

```bash
docker compose exec -T backend tar xzf - -C /app/media < welltrip-media.tgz
```

ถ้าเริ่มฐานข้อมูลใหม่ ให้สร้าง admin:

```bash
docker compose exec backend python manage.py createsuperuser
```

ทดสอบบน VPS ก่อน ถ้าได้ `200` หรือ `302` แปลว่า nginx และ backend ทำงานแล้ว:

```bash
curl -sk -o /dev/null -w '%{http_code}\n' --resolve welltripthailand.com:8443:127.0.0.1 https://welltripthailand.com:8443/
```

จากนั้นเปิด https://welltripthailand.com แล้วทดสอบหน้าแรก, ล็อกอิน, หน้า `/admin/`, การอัปโหลดรูป และหน้าชำระเงิน

## อัปเดตเวอร์ชันครั้งต่อไป

```bash
git pull && docker compose up -d --build
```

## สำรองฐานข้อมูล

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup-$(date +%F).dump
```
