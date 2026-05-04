"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
# Importamos tus vistas personalizadas de autenticación
from envios import views_auth

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # 1. TUS RUTAS PERSONALIZADAS (Prioridad Alta)
    # Al ponerlas antes, Django usará TU login_view y no el de auth.urls
    path('login/', views_auth.login_view, name='login'),
    path('logout/', views_auth.logout_view, name='logout'),
    path('perfil/', views_auth.perfil_view, name='perfil'),

    # 2. RUTAS DE TUS APPS
    path('', include('envios.urls')),

    # 3. URLS DE DJANGO (Opcional/Respaldo)
    # Útil para recuperar contraseña u otras funciones que no hayas programado manualmente
    path('accounts/', include('django.contrib.auth.urls')),
]

if settings.DEBUG:
    # Archivos estáticos (CSS, JS)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    # Archivos de medios (Imágenes/Uploads) corregido MEDIA_URL
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)