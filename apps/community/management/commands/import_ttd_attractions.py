"""
Imports Sisaket attractions exported from the Ministry of Tourism and Sports'
Thailand Tourism Directory (thailandtourismdirectory.go.th) as DRAFT editorial
entries (kind ATTRACTION). Publish them one by one from Admin Center → เนื้อหา.

    python manage.py import_ttd_attractions                 # bundled data file
    python manage.py import_ttd_attractions path/to/file.json
    python manage.py import_ttd_attractions --update        # refresh drafts already imported

Safe to re-run: entries are matched on their source URL. Published entries are
never changed, so edits made before publishing are only overwritten with --update.
"""
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.community.models import EditorialEntry

DEFAULT_FILE = Path(__file__).resolve().parents[2] / "data" / "ttd_sisaket_attractions.json"
SISAKET_BOX = ((Decimal("14.0"), Decimal("15.7")), (Decimal("103.8"), Decimal("105.2")))
SOURCE_NAME = "Thailand Tourism Directory กระทรวงการท่องเที่ยวและกีฬา"


def _summary(text, limit=220):
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # end on a space so a Thai/English word is not cut in half
    return (cut.rsplit(" ", 1)[0] if " " in cut else cut).rstrip() + "…"


def _coord(value):
    try:
        number = Decimal(str(value)).quantize(Decimal("0.0000001"))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return number if number != 0 else None


def build_entry_fields(row):
    """Maps one exported attraction to EditorialEntry fields."""
    lat, lng = _coord(row.get("lat")), _coord(row.get("lng"))
    if not (lat and lng and SISAKET_BOX[0][0] <= lat <= SISAKET_BOX[0][1] and SISAKET_BOX[1][0] <= lng <= SISAKET_BOX[1][1]):
        # A few source entries carry coordinates outside the province: better none than a wrong pin
        lat = lng = None
    lines = [row.get("detail_th", "").strip()]
    extra = [
        ("การเดินทาง", row.get("travel_remark")),
        ("เวลาเปิด", row.get("open_hours")),
        ("ที่อยู่", " ".join(filter(None, [row.get("address"), row.get("postcode")]))),
        ("โทร", row.get("tel")),
        ("เว็บไซต์", row.get("website")),
    ]
    info = [f"{label}: {value.strip()}" for label, value in extra if value and str(value).strip()]
    if info:
        lines.append("\n".join(info))
    lines.append(f"ที่มาข้อมูล: {SOURCE_NAME} {row['source_url']}")

    district = row.get("district", "").strip()
    location = " ".join(filter(None, [
        f"ต.{row['subdistrict']}" if row.get("subdistrict") else "",
        f"อ.{district}" if district else "",
        "จ.ศรีสะเกษ",
    ]))
    image = row.get("image") or next(iter(row.get("images") or []), "")
    return {
        "kind": EditorialEntry.Kind.ATTRACTION,
        "title": row["name_th"].strip()[:200],
        "title_en": (row.get("name_en") or "").strip()[:200],
        "summary": _summary(row.get("detail_th")),
        "body": "\n\n".join(lines),
        "image_url": image,
        "image_alt": row["name_th"].strip()[:200],
        "location": location[:200],
        "latitude": lat,
        "longitude": lng,
        "google_maps_url": f"https://www.google.com/maps/@{lat},{lng},16z" if lat and lng else "",
        "source_url": row["source_url"],
    }


class Command(BaseCommand):
    help = "Import Sisaket attractions (Thailand Tourism Directory export) as draft articles."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=str(DEFAULT_FILE))
        parser.add_argument("--update", action="store_true", help="Refresh drafts that were imported before.")

    def handle(self, *args, path, update, **options):
        try:
            rows = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Cannot read {path}: {exc}")

        created = updated = skipped = 0
        with transaction.atomic():
            for row in rows:
                if not row.get("name_th") or not row.get("source_url"):
                    skipped += 1
                    continue
                fields = build_entry_fields(row)
                entry = EditorialEntry.objects.filter(source_url=fields["source_url"]).first()
                if entry is None:
                    EditorialEntry.objects.create(is_published=False, **fields)
                    created += 1
                elif update and not entry.is_published:
                    for key, value in fields.items():
                        setattr(entry, key, value)
                    entry.save()
                    updated += 1
                else:
                    skipped += 1

        self.stdout.write(self.style.SUCCESS(
            f"Attractions: {created} new drafts, {updated} drafts refreshed, {skipped} skipped. "
            "Publish them in Admin Center → เนื้อหา."
        ))
