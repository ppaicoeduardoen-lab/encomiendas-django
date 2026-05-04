from django.urls import path
from django.contrib import admin
from . import views       # Para las funciones (dashboard, estado, api)
from . import views_cbv   # Para las clases (ListView, DetailView, etc.)

urlpatterns = [
    # ── Dashboard (se mantiene como función) ────────────────────────
    path('', views.dashboard, name='dashboard'),

    # ── Rutas usando Class-Based Views (views_cbv) ──────────────────
    # Listado general
    path('encomiendas/', views_cbv.EncomiendaListView.as_view(), name='encomienda_lista'),
    
    # Creación
    path('encomiendas/nueva/', views_cbv.EncomiendaCreateView.as_view(), name='encomienda_crear'),
    
    # Detalle (con parámetro pk)
    path('encomiendas/<int:pk>/', views_cbv.EncomiendaDetailView.as_view(), name='encomienda_detalle'),
    
    # Edición (con parámetro pk)
    path('encomiendas/<int:pk>/editar/', views_cbv.EncomiendaUpdateView.as_view(), name='encomienda_editar'),

    # ── Rutas especiales (se mantienen como funciones en views) ─────
    # Cambio de estado (Acción rápida)
    path('encomiendas/<int:pk>/estado/', views.encomienda_cambiar_estado, name='encomienda_cambiar_estado'),

    # Búsqueda por código de texto
    path('encomiendas/buscar/<str:codigo>/', views.buscar_por_codigo, name='buscar_por_codigo'),

    # API con UUID
    path('api/encomiendas/<uuid:id_api>/', views.encomienda_api, name='encomienda_api'),
]

# Personalización del Panel de Administración
admin.site.site_header = 'Sistema de Gestión de Encomiendas'
admin.site.site_title = 'Encomiendas Admin'
admin.site.index_title = 'Panel de Administración'