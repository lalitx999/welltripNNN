# Deploy WellTrip ขึ้น VPS

ระบบมี 5 container: `db` (PostgreSQL 16), `redis`, `backend` (Django + Gunicorn), `nginx` และ `cloudflared`
คนเข้าเว็บผ่าน **Cloudflare Tunnel** จึงไม่ต้องเปิดพอร์ตหรือทำ SSL เอง และไม่ชนกับโปรเจคอื่นบน VPS

```
ผู้ใช้ → https://welltripthailand.com → Cloudflare → cloudflared → nginx → backend
```

ตอน start `backend` จะรัน `migrate` และ `collectstatic` ให้อัตโนมัติ (ดูใน `docker-entrypoint.sh`)

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
| `CLOUDFLARE_TUNNEL_TOKEN` | ได้จากขั้นที่ 2 |
| `SLIP_PROVIDER_API_KEY` | key **ใหม่** ของ EasySlip |
| `EMAIL_HOST_PASSWORD` | รหัสอีเมล **ใหม่** |
| `PAYEE_*`, `GOOGLE_OAUTH_CLIENT_IDS`, `ADMIN_EMAIL` | ค่าจริงของคุณ |

ไม่ต้องใส่ `DATABASE_URL` และ `REDIS_URL` เพราะ docker-compose สร้างให้เอง

## 2. สร้าง Cloudflare Tunnel

ใช้ Tunnel ใหม่ของ VPS ไม่ใช้ `tanchonserver` ตัวเดิมที่อยู่บน homeserver

1. Cloudflare → **Zero Trust** → **Networks** → **Tunnels** → **Create a tunnel** → เลือก **Cloudflared**
2. ตั้งชื่อ เช่น `welltrip-vps` แล้วกด Save
3. ในหน้าที่ให้ติดตั้ง เลือก **Docker** แล้วก๊อปเฉพาะ token ซึ่งเป็นข้อความยาว ๆ ต่อจาก `--token`
   ใส่ใน `.env` เป็น `CLOUDFLARE_TUNNEL_TOKEN=...` (**ไม่ต้อง**รันคำสั่ง docker ที่ Cloudflare ให้มา)
4. กด Next ไปที่ **Public Hostname** แล้วเพิ่มดังนี้:
   - Subdomain: ว่าง, Domain: `welltripthailand.com`, Service: **HTTP** → `nginx:80`
5. เพิ่มอีกอันสำหรับ `www`:
   - Subdomain: `www`, Domain: `welltripthailand.com`, Service: **HTTP** → `nginx:80`

ถ้ามี A record เดิมของ `welltripthailand.com` หรือ `www` อยู่ใน DNS ให้ลบก่อน ไม่อย่างนั้น Cloudflare จะสร้าง record ของ Tunnel ไม่ได้

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
docker compose logs -f backend cloudflared
```

ใน log ของ `cloudflared` ต้องเห็นบรรทัด `Registered tunnel connection` และในหน้า Tunnels ของ Cloudflare ต้องขึ้นสถานะ **HEALTHY**

ถ้าย้ายไฟล์ media มาจากขั้นที่ 3 ให้แตกไฟล์เข้า volume:

```bash
docker compose exec -T backend tar xzf - -C /app/media < welltrip-media.tgz
```

ถ้าเริ่มฐานข้อมูลใหม่ ให้สร้าง admin:

```bash
docker compose exec backend python manage.py createsuperuser
```

เปิด https://welltripthailand.com แล้วทดสอบหน้าแรก, ล็อกอิน, หน้า `/admin/`, การอัปโหลดรูป และหน้าชำระเงิน

## อัปเดตเวอร์ชันครั้งต่อไป

```bash
git pull && docker compose up -d --build
```

## สำรองฐานข้อมูล

```bash
docker compose exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -Fc "$POSTGRES_DB"' > backup-$(date +%F).dump
```
