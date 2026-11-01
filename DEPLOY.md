# Deploy WellTrip ขึ้น VPS

ระบบประกอบด้วย 4 container ใน `docker-compose.yml`: `db` (PostgreSQL 16), `redis`, `backend` (Django + Gunicorn) และ `nginx` (HTTPS ผ่าน Let's Encrypt)
ตอน start `backend` จะรัน `migrate` และ `collectstatic` ให้อัตโนมัติ (ดูใน `docker-entrypoint.sh`)

## 0. เตรียมก่อนเริ่ม

- ตั้ง DNS: สร้าง A record ของ `welltripthailand.com` และ `www.welltripthailand.com` ให้ชี้ไปที่ IP ของ VPS
  ถ้าใช้ Cloudflare ให้ตั้งเป็น **DNS only (เมฆสีเทา)** ไว้ก่อนจนกว่าจะออก cert เสร็จ
- ติดตั้ง Docker บน VPS แล้ว และเปิดพอร์ต 22, 80, 443

```bash
curl -fsSL https://get.docker.com | sh
```

```bash
sudo ufw allow OpenSSH && sudo ufw allow 80 && sudo ufw allow 443 && sudo ufw enable
```

- ทดสอบว่า DNS ชี้มาที่ VPS แล้ว ผลที่ได้ต้องเป็น IP ของ VPS

```bash
dig +short welltripthailand.com
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

## 2. ออก SSL certificate ครั้งแรก

ทำตอนที่ nginx ยังไม่ได้รัน เพราะ certbot ต้องใช้พอร์ต 80 (เปลี่ยนอีเมลเป็นของคุณ)

```bash
docker compose run --rm -p 80:80 certbot certonly --standalone -d welltripthailand.com -d www.welltripthailand.com --email you@example.com --agree-tos --no-eff-email
```

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
docker compose logs -f backend
```

ถ้าย้ายไฟล์ media มาจากขั้นที่ 3 ให้แตกไฟล์เข้า volume:

```bash
docker compose exec -T backend tar xzf - -C /app/media < welltrip-media.tgz
```

ถ้าเริ่มฐานข้อมูลใหม่ ให้สร้าง admin:

```bash
docker compose exec backend python manage.py createsuperuser
```

เปิด https://welltripthailand.com ทดสอบ: หน้าแรก, ล็อกอิน, หน้า `/admin/`, อัปโหลดรูป และหน้าชำระเงิน

## 5. ต่ออายุ SSL อัตโนมัติ

ตั้ง cron ด้วย `crontab -e` แล้วเพิ่มบรรทัดนี้ (แก้ path ให้ตรงกับที่ clone ไว้):

```
0 3 * * * cd /root/welltrip && docker compose run --rm certbot renew --webroot -w /var/www/certbot --quiet && docker compose exec nginx nginx -s reload
```

## อัปเดตเวอร์ชันครั้งต่อไป

```bash
git pull && docker compose up -d --build
```

## สำรองฐานข้อมูล

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup-$(date +%F).dump
```
