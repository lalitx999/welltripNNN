"""
Build the site's logo files from static/logo_new.png (the master logo).

    python3 scripts/make_logo_assets.py

Writes:
  static/images/brand/logo-full.png   full logo, transparent, trimmed (pages, documents, JSON-LD)
  static/images/brand/logo-mark.png   the "W" emblem only, square, transparent (header, sidebar, footer)
  static/images/brand/logo-og.jpg     1200x630 share image on white (Open Graph / Twitter)
  static/images/brand/favicon.ico     16/32/48 px emblem
  static/icons/wt-icon-192.png        PWA / apple-touch icons: emblem on white, padded for maskable
  static/icons/wt-icon-512.png

The master has dark lettering on a transparent background, so the full logo is
only placed on light backgrounds; dark areas use the emblem.
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "static" / "logo_new.png"
BRAND = ROOT / "static" / "images" / "brand"
ICONS = ROOT / "static" / "icons"

# Emblem area in the 1536x1024 master: the "W", swoosh and plane, without the map pin below it
EMBLEM_BOX = (300, 40, 1290, 575)
PIN_BOX = (1065, 500, 1300, 600)


def trim(im):
    return im.crop(im.split()[3].getbbox())


def square(im, pad=0.0, bg=(0, 0, 0, 0)):
    w, h = im.size
    side = int(max(w, h) * (1 + 2 * pad))
    out = Image.new("RGBA", (side, side), bg)
    out.alpha_composite(im, ((side - w) // 2, (side - h) // 2))
    return out


def fit(im, w, h):
    im = im.copy()
    im.thumbnail((w, h), Image.LANCZOS)
    return im


def main():
    BRAND.mkdir(parents=True, exist_ok=True)
    master = Image.open(SRC).convert("RGBA")

    full = trim(master)
    fit(full, 900, 900).save(BRAND / "logo-full.png", optimize=True)

    em = master.copy()
    ImageDraw.Draw(em).rectangle(PIN_BOX, fill=(0, 0, 0, 0))
    emblem = square(trim(em.crop(EMBLEM_BOX)))
    emblem.resize((256, 256), Image.LANCZOS).save(BRAND / "logo-mark.png", optimize=True)

    og = Image.new("RGBA", (1200, 630), (255, 255, 255, 255))
    logo = fit(full, 1000, 560)
    og.alpha_composite(logo, ((1200 - logo.width) // 2, (630 - logo.height) // 2))
    og.convert("RGB").save(BRAND / "logo-og.jpg", quality=88, optimize=True)

    emblem.resize((48, 48), Image.LANCZOS).save(BRAND / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])

    icon = square(emblem, pad=0.12, bg=(255, 255, 255, 255))
    for size in (192, 512):
        icon.resize((size, size), Image.LANCZOS).convert("RGB").save(ICONS / f"wt-icon-{size}.png", optimize=True)

    print("logo assets written to", BRAND, "and", ICONS)


if __name__ == "__main__":
    main()
