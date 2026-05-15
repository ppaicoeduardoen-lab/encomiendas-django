from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from envios import api_views
from envios.api_auth import EncomiendaTokenView
from envios.viewsets import EncomiendaViewSet

router = DefaultRouter()
router.register('encomiendas', EncomiendaViewSet, basename='encomienda')

urlpatterns = [
    path('auth/token/', EncomiendaTokenView.as_view(), name='token_obtain'),
    path('auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('clientes/', api_views.ClienteListView.as_view(), name='cliente-list'),
    path('rutas/', api_views.RutaListView.as_view(), name='ruta-list'),
    path('', include(router.urls)),
]
