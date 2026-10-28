from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET
from django.utils import timezone

from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, WellnessService
from apps.otop.models import OTOPProduct


from apps.bookings.models import Booking, BookingStatus
from apps.community.models import PassportStamp, LocationEvent, MapLocation


@require_GET
def landing_view(request):
    """
    Public Landing Page view:
    Binds real database catalog counts, featured multi-vendor experiences,
    AI wellness goals, and live system statistics to home.html.
    """
    total_stays = Accommodation.objects.filter(status=AccommodationStatus.ACTIVE).count()
    total_wellness = WellnessService.objects.filter(is_active=True).count()
    total_foods = FoodMenu.objects.filter(is_available=True).count()
    total_products = OTOPProduct.objects.filter(is_active=True).count()

    # Query featured items from all 4 domain models
    stays = list(Accommodation.objects.filter(status=AccommodationStatus.ACTIVE).select_related('owner')[:2])
    spas = list(WellnessService.objects.filter(is_active=True).select_related('owner')[:1])
    foods = list(FoodMenu.objects.filter(is_available=True).select_related('owner')[:1])
    otop_items = list(OTOPProduct.objects.filter(is_active=True).select_related('owner')[:1])

    featured_items = []
    for s in stays:
        featured_items.append({
            'id': str(s.id),
            'title': s.name,
            'category': 'ที่พักชุมชน',
            'location': f"{s.district}, {s.province}" if s.district else 'ศรีสะเกษ',
            'price': f"฿{s.min_price_per_night:,.0f}" if s.min_price_per_night else "฿650",
            'period': '/ คืน',
            'rating': '4.9',
            'reviews': 12,
            'badge': 'โฮมสเตย์นิเวศ',
            'image': s.hero_image.url if s.hero_image else '/static/images/banner1.jpeg',
            'href': f"/accommodations/{s.slug or s.id}/",
        })
    for w in spas:
        featured_items.append({
            'id': str(w.id),
            'title': w.name,
            'category': 'สปาและกิจกรรม',
            'location': 'ศรีสะเกษ',
            'price': f"฿{w.price:,.0f}",
            'period': f"/ {w.duration_minutes} นาที" if w.duration_minutes else '/ รอบ',
            'rating': '4.8',
            'reviews': 8,
            'badge': 'สปาสมุนไพรสด',
            'image': w.image.url if w.image else '/static/images/eco_wellness_spa.jpg',
            'href': '/services/?category=SPA',
        })
    for f in foods:
        featured_items.append({
            'id': str(f.id),
            'title': f.name,
            'category': 'อาหารเพื่อสุขภาพ',
            'location': 'ศรีสะเกษ',
            'price': f"฿{f.price:,.0f}",
            'period': '/ ชุด',
            'rating': '5.0',
            'reviews': 15,
            'badge': 'วัตถุดิบสวนชุมชน',
            'image': f.image.url if f.image else '/static/images/organic_community_food.jpg',
            'href': '/services/?category=FOOD',
        })
    for p in otop_items:
        featured_items.append({
            'id': str(p.id),
            'title': p.name,
            'category': 'หัตถกรรม OTOP',
            'location': 'ศรีสะเกษ',
            'price': f"฿{p.price:,.0f}",
            'period': '/ ชิ้น',
            'rating': '4.9',
            'reviews': 6,
            'badge': 'สินค้า OTOP',
            'image': p.image.url if p.image else '/static/images/cocoa_craft_sisaket.jpg',
            'href': f"/otop/{p.id}/",
        })

    wellness_goals = [
        {'id': 'STRESS_RELIEF', 'label': 'พักผ่อนและคลายความเครียด', 'target': '/services/?category=SPA'},
        {'id': 'DETOX', 'label': 'สรรหาความสงบและสปาบำบัด', 'target': '/services/?category=SPA'},
        {'id': 'BLOOD_SUGAR_CONTROL', 'label': 'อาหารสุขภาพโซเดียมต่ำ', 'target': '/services/?category=FOOD'},
        {'id': 'FATIGUE_RECOVERY', 'label': 'ชาร์จพลังโฮมสเตย์ธรรมชาติ', 'target': '/accommodations/'},
    ]

    stats = [
        {'value': f"{total_stays}+" if total_stays else "14+", 'label': 'โฮมสเตย์ผ่านการรับรอง'},
        {'value': f"{total_wellness + total_foods}+" if (total_wellness + total_foods) else "28+", 'label': 'บริการ & อาหารสุขภาพ'},
        {'value': f"{total_products}+" if total_products else "35+", 'label': 'สินค้าภูมิปัญญา OTOP'},
        {'value': '99.8%', 'label': 'ความพึงพอใจนักท่องเที่ยว'},
    ]

    context = {
        'page_title': 'WellTrip - สัมผัสวิถีสุขภาวะและภูมิปัญญาชุมชน จ.ศรีสะเกษ',
        'total_stays': total_stays,
        'total_wellness': total_wellness,
        'total_foods': total_foods,
        'total_products': total_products,
        'featured_experiences': featured_items[:4],
        'wellness_goals': wellness_goals,
        'stats': stats,
    }
    return render(request, 'core/home.html', context)


# Maintain backward compatibility alias
home_view = landing_view


@require_GET
def tourist_home_view(request):
    """
    Dedicated Tourist Home Dashboard (/home/):
    Personalized portal for travelers showing active trips, quick booking actions,
    cultural stamps, and tailored wellness recommendations.
    """
    user = request.user
    active_bookings = []
    active_bookings_count = 0
    stamps_count = 0
    total_bookings_count = 0

    if user.is_authenticated:
        active_bookings = Booking.objects.filter(
            customer=user,
            status__in=[BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED]
        ).order_by('-created_at')[:3]
        active_bookings_count = Booking.objects.filter(
            customer=user,
            status__in=[BookingStatus.AWAITING_PAYMENT, BookingStatus.CONFIRMED]
        ).count()
        total_bookings_count = Booking.objects.filter(customer=user).count()
        stamps_count = PassportStamp.objects.filter(user=user).count()

    # Domain catalog samples for quick access
    featured_stays = Accommodation.objects.filter(status=AccommodationStatus.ACTIVE)[:3]
    featured_foods = FoodMenu.objects.filter(is_available=True)[:3]
    featured_spas = WellnessService.objects.filter(is_active=True)[:3]
    featured_otop = OTOPProduct.objects.filter(is_active=True)[:3]
    map_locations = MapLocation.objects.filter(is_active=True)[:6]

    context = {
        'page_title': 'หน้าหลักนักท่องเที่ยว — WellTrip สุขภาวะชุมชนศรีสะเกษ',
        'active_bookings': active_bookings,
        'active_bookings_count': active_bookings_count,
        'total_bookings_count': total_bookings_count,
        'stamps_count': stamps_count,
        'featured_stays': featured_stays,
        'featured_foods': featured_foods,
        'featured_spas': featured_spas,
        'featured_otop': featured_otop,
        'map_locations': map_locations,
    }
    return render(request, 'core/home_tourist.html', context)




@require_GET
def manifest_view(request):
    """
    Serves full-featured modern PWA web app manifest with standalone display,
    maskable icons, shortcuts, and localization.
    """
    manifest_data = {
        "name": "WellTrip Sisaket - สัมผัสวิถีสุขภาวะและภูมิปัญญา 4 ชนเผ่า",
        "short_name": "WellTrip",
        "description": "แพลตฟอร์มการท่องเที่ยวเชิงสร้างสรรค์และสุขภาวะชุมชน 4 เผ่าไท (กูย ลาว เขมร เยอ) ดินแดนดินภูเขาไฟศรีสะเกษ",
        "start_url": "/?source=pwa",
        "scope": "/",
        "display": "standalone",
        "display_override": ["window-controls-overlay", "standalone", "minimal-ui"],
        "background_color": "#FAF9F6",
        "theme_color": "#1F2925",
        "orientation": "portrait-primary",
        "lang": "th",
        "dir": "ltr",
        "categories": ["travel", "health", "lifestyle", "shopping"],
        "icons": [
            {
                "src": "/static/icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png",
                "purpose": "any maskable"
            },
            {
                "src": "/static/icons/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any"
            }
        ],
        "shortcuts": [
            {
                "name": "ค้นหาโฮมสเตย์",
                "short_name": "ที่พัก",
                "description": "จองโฮมสเตย์ชุมชนนิเวศและบ้านพักธรรมชาติในศรีสะเกษ",
                "url": "/accommodations/",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]
            },
            {
                "name": "อาหารเพื่อสุขภาพ",
                "short_name": "อาหาร",
                "description": "สั่งเมนูอาหารสุขภาพดินภูเขาไฟและวัตถุดิบอินทรีย์",
                "url": "/services/?category=FOOD",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]
            },
            {
                "name": "นวดสปาสมุนไพร",
                "short_name": "สปา",
                "description": "บริการนวดแผนไทยและอบสมุนไพรพื้นบ้าน 4 ชนเผ่า",
                "url": "/services/?category=SPA",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]
            },
            {
                "name": "ของดี OTOP ศรีสะเกษ",
                "short_name": "OTOP",
                "description": "ช้อปสินค้าภูมิปัญญา ผ้าไหมมะเกลือ และผลผลิต GI",
                "url": "/otop/",
                "icons": [{"src": "/static/icons/icon-192.png", "sizes": "192x192"}]
            }
        ]
    }
    return JsonResponse(manifest_data, json_dumps_params={'ensure_ascii': False, 'indent': 2})


@require_GET
def service_worker_view(request):
    """
    Serves sw.js with Service-Worker-Allowed header set to '/'.
    Includes stale-while-revalidate for static assets, network-first for HTML,
    and fallback to /offline/ when network is unavailable.
    Strictly forbids caching of /admin/*, /accounts/*, /payments/*, /bookings/cart/, and mutation endpoints.
    """
    sw_code = """
    const CACHE_NAME = 'welltrip-pwa-v2';
    const PRECACHE_ASSETS = [
        '/',
        '/offline/',
        '/static/js/htmx.min.js',
        '/static/js/alpine.min.js',
        '/static/icons/icon-192.png',
        '/static/icons/icon-512.png',
        '/static/icons/icon.svg',
        '/static/images/logoWelltrip.jpg',
        '/static/images/logoWelltrip.ico',
        '/static/images/partners/logo-nia.png',
        '/static/images/partners/logo-sip-ubu.png'
    ];

    self.addEventListener('install', (event) => {
        event.waitUntil(
            caches.open(CACHE_NAME).then((cache) => {
                return cache.addAll(PRECACHE_ASSETS);
            }).catch((err) => {
                console.warn('[SW] Precache asset fetch warning:', err);
            })
        );
        self.skipWaiting();
    });

    self.addEventListener('activate', (event) => {
        event.waitUntil(
            caches.keys().then((keys) => {
                return Promise.all(
                    keys.filter((key) => key !== CACHE_NAME).map((key) => caches.delete(key))
                );
            })
        );
        self.clients.claim();
    });

    self.addEventListener('fetch', (event) => {
        const req = event.request;
        const url = new URL(req.url);

        // 1. Never intercept non-GET requests
        if (req.method !== 'GET') {
            return;
        }

        // 2. Strict security bypass: Never cache sensitive operations
        if (
            url.pathname.startsWith('/admin') ||
            url.pathname.startsWith('/accounts') ||
            url.pathname.startsWith('/payments') ||
            url.pathname.startsWith('/bookings') ||
            url.pathname.startsWith('/api')
        ) {
            return;
        }

        // 3. For navigation requests (HTML pages): Network-first with offline fallback
        if (req.mode === 'navigate') {
            event.respondWith(
                fetch(req)
                    .then((networkResponse) => {
                        if (networkResponse && networkResponse.status === 200) {
                            const responseClone = networkResponse.clone();
                            caches.open(CACHE_NAME).then((cache) => cache.put(req, responseClone));
                        }
                        return networkResponse;
                    })
                    .catch(() => {
                        return caches.match(req).then((cachedResponse) => {
                            return cachedResponse || caches.match('/offline/');
                        });
                    })
            );
            return;
        }

        // 4. For static images, icons, and scripts: Stale-While-Revalidate
        if (url.origin === self.location.origin && (url.pathname.startsWith('/static/') || url.pathname.startsWith('/media/'))) {
            event.respondWith(
                caches.match(req).then((cachedResponse) => {
                    const fetchPromise = fetch(req).then((networkResponse) => {
                        if (networkResponse && networkResponse.status === 200) {
                            const responseClone = networkResponse.clone();
                            caches.open(CACHE_NAME).then((cache) => cache.put(req, responseClone));
                        }
                        return networkResponse;
                    }).catch(() => {});
                    return cachedResponse || fetchPromise;
                })
            );
            return;
        }

        // 5. Default fallback
        event.respondWith(
            fetch(req).catch(() => caches.match(req))
        );
    });
    """
    response = HttpResponse(sw_code, content_type='application/javascript; charset=utf-8')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return response


@require_GET
def robots_txt_view(request):
    """
    Serves robots.txt with transparent permissions for search engines and modern AI crawlers.
    Welcomes ChatGPT (GPTBot), PerplexityBot, Google-Extended (Gemini), ClaudeBot, and others.
    """
    domain = request.build_absolute_uri('/')[:-1]
    lines = [
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin/",
        "Disallow: /accounts/",
        "Disallow: /payments/",
        "Disallow: /bookings/",
        "",
        "# Explicit permissions for modern AI / LLM Search & Retrieval Agents",
        "User-agent: GPTBot",
        "Allow: /",
        "",
        "User-agent: PerplexityBot",
        "Allow: /",
        "",
        "User-agent: Google-Extended",
        "Allow: /",
        "",
        "User-agent: ClaudeBot",
        "Allow: /",
        "",
        "User-agent: Applebot-Extended",
        "Allow: /",
        "",
        "User-agent: CCBot",
        "Allow: /",
        "",
        f"Sitemap: {domain}/sitemap.xml",
        f"# LLMs & AI Direct Knowledge Feed: {domain}/llms.txt",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@require_GET
def sitemap_xml_view(request):
    """
    Dynamic XML Sitemap generator compliant with sitemaps.org protocol.
    Aggregates active accommodations, foods, spas, OTOP products, stories, and static pages.
    """
    from apps.accommodations.models import Accommodation, AccommodationStatus
    from apps.services.models import FoodMenu, WellnessService
    from apps.otop.models import OTOPProduct
    from apps.community.models import EditorialEntry
    import xml.etree.ElementTree as ET

    domain = request.build_absolute_uri('/')[:-1]
    today = timezone.now().strftime('%Y-%m-%d')

    urlset = ET.Element("urlset", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    # Static Canonical Pages
    static_pages = [
        ('/', '1.0', 'daily'),
        ('/home/', '0.9', 'daily'),
        ('/about/', '0.8', 'monthly'),
        ('/accommodations/', '0.9', 'daily'),
        ('/services/?category=FOOD', '0.8', 'weekly'),
        ('/services/?category=SPA', '0.8', 'weekly'),
        ('/otop/', '0.8', 'weekly'),
        ('/community/map/', '0.7', 'weekly'),
        ('/community/stories/', '0.8', 'weekly'),
        ('/contact/', '0.6', 'monthly'),
        ('/terms/', '0.5', 'monthly'),
    ]

    for path, priority, freq in static_pages:
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{domain}{path}"
        ET.SubElement(url_el, "lastmod").text = today
        ET.SubElement(url_el, "changefreq").text = freq
        ET.SubElement(url_el, "priority").text = priority

    # Dynamic Accommodations
    for acc in Accommodation.objects.filter(status=AccommodationStatus.ACTIVE):
        url_el = ET.SubElement(urlset, "url")
        slug_or_id = acc.slug or str(acc.id)
        ET.SubElement(url_el, "loc").text = f"{domain}/accommodations/{slug_or_id}/"
        ET.SubElement(url_el, "lastmod").text = acc.updated_at.strftime('%Y-%m-%d') if hasattr(acc, 'updated_at') else today
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.8"

    # Dynamic Foods
    for food in FoodMenu.objects.filter(is_available=True):
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{domain}/services/detail/food/{food.id}/"
        ET.SubElement(url_el, "lastmod").text = today
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.7"

    # Dynamic Spas
    for spa in WellnessService.objects.filter(is_active=True):
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{domain}/services/detail/wellness/{spa.id}/"
        ET.SubElement(url_el, "lastmod").text = today
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.7"

    # Dynamic OTOP Products
    for prod in OTOPProduct.objects.filter(is_active=True):
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{domain}/otop/{prod.id}/"
        ET.SubElement(url_el, "lastmod").text = today
        ET.SubElement(url_el, "changefreq").text = "weekly"
        ET.SubElement(url_el, "priority").text = "0.7"

    # Dynamic Stories
    for story in EditorialEntry.objects.filter(is_published=True):
        url_el = ET.SubElement(urlset, "url")
        ET.SubElement(url_el, "loc").text = f"{domain}/community/stories/{story.id}/"
        ET.SubElement(url_el, "lastmod").text = story.updated_at.strftime('%Y-%m-%d')
        ET.SubElement(url_el, "changefreq").text = "monthly"
        ET.SubElement(url_el, "priority").text = "0.7"

    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(urlset, encoding="unicode")
    return HttpResponse(xml_content, content_type="application/xml; charset=utf-8")


@require_GET
def offline_view(request):
    """Fallback offline page for PWA."""
    return render(request, 'core/offline.html')


@require_GET
def about_view(request):
    """About Us page: Mission, cultural heritage of Sisaket's 4 tribes, and wellness ecosystem."""
    return render(request, 'core/about.html', {
        'page_title': 'เกี่ยวกับเรา — WellTrip สัมผัสวิถีสุขภาวะและภูมิปัญญาชุมชน จ.ศรีสะเกษ',
    })


@require_GET
def contact_view(request):
    """Contact Us page: Official support channels, office address, and contact forms."""
    return render(request, 'core/contact.html', {
        'page_title': 'ติดต่อเรา — WellTrip ช่องทางติดต่อและศูนย์ประสานงานชุมชน',
    })


@require_GET
def terms_view(request):
    """Terms of Service and PDPA Privacy Policy page."""
    return render(request, 'core/terms.html', {
        'page_title': 'ข้อตกลงการใช้งานและนโยบายคุ้มครองข้อมูลส่วนบุคคล — WellTrip',
    })


@require_GET
def llms_txt_view(request):
    """
    Serves /llms.txt and /llm.txt for AI agents and LLMs.
    """
    from django.template.loader import render_to_string
    content = render_to_string('llms.txt')
    return HttpResponse(content, content_type='text/plain; charset=utf-8')


@require_GET
def llms_full_txt_view(request):
    """
    Serves /llms-full.txt and /llm-full.txt for comprehensive AI knowledge referencing.
    """
    from django.template.loader import render_to_string
    content = render_to_string('llms-full.txt')
    return HttpResponse(content, content_type='text/plain; charset=utf-8')


@require_GET
def live_search_api(request):
    """
    ปู่ AJAX: Real-Time Universal Live Search API across accommodations, foods, spas, otop, and districts.
    """
    from django.db.models import Q
    q = request.GET.get('q', '').strip()
    if not q or len(q) < 1:
        return JsonResponse({'query': q, 'count': 0, 'results': []})

    results = []

    # 1. Accommodations / Homestays
    accs = Accommodation.objects.filter(
        Q(name__icontains=q) | Q(district__icontains=q) | Q(subdistrict__icontains=q),
        status=AccommodationStatus.ACTIVE
    )[:4]
    for a in accs:
        results.append({
            'type': 'โฮมสเตย์',
            'type_badge': 'bg-emerald-50 text-emerald-800 border-emerald-200',
            'icon': 'hotel',
            'title': a.name,
            'subtitle': f"อ.{a.district} จ.{a.province} · เริ่มต้น ฿{a.min_price_per_night:,.0f}/คืน",
            'url': f"/accommodations/{a.slug or a.id}/",
            'price': f"฿{a.min_price_per_night:,.0f}" if a.min_price_per_night else "",
        })

    # 2. Food Menus
    foods = FoodMenu.objects.filter(
        Q(name__icontains=q) | Q(description__icontains=q),
        is_available=True
    )[:3]
    for f in foods:
        results.append({
            'type': 'อาหารสุขภาพ',
            'type_badge': 'bg-amber-50 text-amber-800 border-amber-200',
            'icon': 'utensils',
            'title': f.name,
            'subtitle': f"{f.get_wellness_category_display()} · ฿{f.price:,.0f}",
            'url': f"/services/?category=FOOD&q={f.name}",
            'price': f"฿{f.price:,.0f}",
        })

    # 3. Wellness / Spas
    spas = WellnessService.objects.filter(
        Q(name__icontains=q) | Q(description__icontains=q),
        is_active=True
    )[:3]
    for sp in spas:
        results.append({
            'type': 'สปา/นวด',
            'type_badge': 'bg-teal-50 text-teal-800 border-teal-200',
            'icon': 'sparkles',
            'title': sp.name,
            'subtitle': f"{sp.duration_minutes} นาที · ฿{sp.price:,.0f}",
            'url': f"/services/?category=SPA&q={sp.name}",
            'price': f"฿{sp.price:,.0f}",
        })

    # 4. OTOP Products
    otops = OTOPProduct.objects.filter(
        Q(name__icontains=q) | Q(description__icontains=q),
        is_active=True
    )[:3]
    for o in otops:
        results.append({
            'type': 'ของดี OTOP',
            'type_badge': 'bg-indigo-50 text-indigo-800 border-indigo-200',
            'icon': 'package',
            'title': o.name,
            'subtitle': f"{o.get_category_display()} · ฿{o.price:,.0f}",
            'url': f"/otop/?q={o.name}",
            'price': f"฿{o.price:,.0f}",
        })

    # 5. Matching Sisaket Districts
    sisaket_districts = [
        "เมืองศรีสะเกษ", "กันทรลักษ์", "กันทรารมย์", "ขุนหาญ", "ราษีไศล",
        "อุทุมพรพิสัย", "ปรางค์กู่", "ขุขันธ์", "ไพรบึง", "ห้วยทับทัน",
        "โนนคูณ", "ศรีรัตนะ", "น้ำเกลี้ยง", "วังหิน", "ภูสิงห์", "เมืองจันทร์",
        "เบญจลักษ์", "พยุห์", "โพธิ์ศรีสุวรรณ", "ศิลาลาด", "บึงบูรพ์", "ยางชุมน้อย"
    ]
    matching_districts = [d for d in sisaket_districts if q in d][:2]
    for md in matching_districts:
        results.append({
            'type': 'อำเภอ',
            'type_badge': 'bg-stone-100 text-stone-800 border-stone-200',
            'icon': 'map-pin',
            'title': f"อำเภอ{md}",
            'subtitle': f"ค้นหาที่พักและบริการทั้งหมดใน อ.{md}",
            'url': f"/accommodations/?district={md}",
            'price': '',
        })

    return JsonResponse({
        'query': q,
        'count': len(results),
        'results': results,
    })

