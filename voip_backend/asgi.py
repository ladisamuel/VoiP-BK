
import os
import django
from django.core.asgi import get_asgi_application


os.environ.setdefault("DJANGO_SETTINGS_MODULE", "voip_backend.settings")

django.setup()

django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter
from calls.routing import websocket_urlpatterns

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": URLRouter(websocket_urlpatterns),
})
