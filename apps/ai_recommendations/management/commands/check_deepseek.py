"""
Check the DeepSeek key and model from the server:
    python manage.py check_deepseek
    docker compose exec backend python manage.py check_deepseek
"""
import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Send one short Thai prompt to DeepSeek with the configured key and model"

    def handle(self, *args, **options):
        key = (settings.DEEPSEEK_API_KEY or "").strip()
        if not key:
            raise CommandError("DEEPSEEK_API_KEY is empty in .env")
        base = settings.DEEPSEEK_BASE_URL.rstrip("/")
        self.stdout.write(f"Model: {settings.DEEPSEEK_MODEL}  Endpoint: {base}/chat/completions")
        try:
            resp = requests.post(
                f"{base}/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={
                    "model": settings.DEEPSEEK_MODEL,
                    "messages": [{"role": "user", "content": "แนะนำสถานที่ท่องเที่ยวในจังหวัดศรีสะเกษ 1 แห่ง ตอบสั้นๆ 1 ประโยค"}],
                    "max_tokens": 80,
                },
                timeout=30,
            )
        except requests.RequestException as exc:
            raise CommandError(f"Could not reach DeepSeek: {exc}")
        if resp.status_code != 200:
            raise CommandError(f"DeepSeek answered HTTP {resp.status_code}: {resp.text[:300]}")
        data = resp.json()
        self.stdout.write(self.style.SUCCESS("OK: " + data["choices"][0]["message"]["content"].strip()))
        usage = data.get("usage") or {}
        self.stdout.write(f"Tokens used: {usage.get('total_tokens', '?')}")
