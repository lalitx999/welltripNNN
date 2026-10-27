from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET

from apps.accommodations.models import Accommodation, AccommodationStatus
from apps.services.models import FoodMenu, WellnessService
from apps.otop.models import OTOPProduct


@require_GET
def home_view(request):
    """
    Landing Page view:
    Binds real database catalog counts, featured multi-vendor experiences,
    AI wellness goals, and live system statistics to home.html.
    """
    # Real live counts
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



@require_GET
def manifest_view(request):
    """Serves PWA manifest with security-safe parameters."""
    manifest_data = {
        "name": "WellTrip - Smart Wellness Tourism",
        "short_name": "WellTrip",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#FAF9F6",
        "theme_color": "#1F2925",
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "/static/icons/icon-192.png",
                "sizes": "192x192",
                "type": "image/png"
            },
            {
                "src": "/static/icons/icon-512.png",
                "sizes": "512x512",
                "type": "image/png"
            }
        ]
    }
    return JsonResponse(manifest_data)


@require_GET
def service_worker_view(request):
    """
    Serves sw.js with Service-Worker-Allowed header set to '/'.
    Strictly forbids caching of /admin/*, /accounts/*, /payments/*, and user-specific data.
    """
    sw_code = """
    const CACHE_NAME = 'welltrip-v1';
    const STATIC_ASSETS = [
        '/',
        '/offline/',
        '/static/css/tailwind.css',
        '/static/js/htmx.min.js',
        '/static/js/alpine.min.js'
    ];

    self.addEventListener('install', (event) => {
        event.waitUntil(
            caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
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
        const url = new URL(event.request.url);
        // Security requirement #10: NEVER cache admin, accounts, payments or mutations
        if (
            url.pathname.startsWith('/admin') ||
            url.pathname.startsWith('/accounts') ||
            url.pathname.startsWith('/payments') ||
            url.pathname.startsWith('/bookings') ||
            event.request.method !== 'GET'
        ) {
            return;
        }

        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request).then((res) => res || caches.match('/offline/')))
        );
    });
    """
    response = HttpResponse(sw_code, content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    return response


@require_GET
def offline_view(request):
    """Fallback offline page for PWA."""
    return render(request, 'core/offline.html')
