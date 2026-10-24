from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("api.urls")),
]

# Uploaded and rendered meme images. In production serve MEDIA_ROOT from the web server or object storage;
# DJANGO_SERVE_MEDIA=True lets Django serve them itself (single-instance free hosting).
if settings.SERVE_MEDIA and not settings.DEBUG:
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT})]
else:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
