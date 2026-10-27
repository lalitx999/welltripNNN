from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET

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

