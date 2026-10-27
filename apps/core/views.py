from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_GET


@require_GET
def home_view(request):
    """Home view - Landing page with SEO, responsive hero and community highlights."""
    context = {
        'page_title': 'WellTrip - สัมผัสวิถีสุขภาวะและภูมิปัญญาชุมชน',
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
