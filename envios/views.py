from django.shortcuts import render, redirect, get_object_or_404, get_list_or_404
from django.contrib.auth.decorators import login_required, permission_required, user_passes_test
from django.views.decorators.http import require_http_methods, require_GET, require_POST
from django.contrib import messages # <--- Importación esencial
from django.utils import timezone
from django.http import HttpResponse, JsonResponse, Http404, HttpResponseForbidden
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.core.paginator import Paginator
import redis
from django.conf import settings


# Importaciones de modelos y recursos locales
from .models import Encomienda, Empleado, HistorialEstado
from .forms import EncomiendaForm
from clientes.models import Cliente
from rutas.models import Ruta
from config.choices import EstadoEnvio

# ── FUNCIONES DE APOYO (PERMISOS) ──────────────────────────────

def es_empleado_activo(user):
    """Verifica si el usuario tiene un perfil de Empleado activo"""
    return (
        user.is_authenticated and 
        Empleado.objects.filter(email=user.email, estado=1).exists()
    )

# ── VISTAS DEL DASHBOARD Y LISTADOS ────────────────────────────

@login_required
def dashboard(request):
    """
    Vista principal con estadísticas de encomiendas adaptada para el WebSocket.
    El template renderiza con los datos iniciales de la BD.
    El WebSocket actualiza los contadores en tiempo real a partir de ese punto.
    """
    hoy = timezone.now().date()
    context = {
        'stats': {
            'activas': Encomienda.objects.activas().count(),
            'en_transito': Encomienda.objects.en_transito().count(),
            'con_retraso': Encomienda.objects.con_retraso().count(),
            'entregadas_hoy': Encomienda.objects.filter(
                estado='EN', 
                fecha_entrega_real=hoy
            ).count(),
        },
        'ultimas': Encomienda.objects.con_relaciones()[:5], # Mantenemos las últimas por si tu dashboard las lista abajo
    }
    return render(request, 'envios/dashboard.html', context)

@require_GET
@login_required
def encomienda_lista(request):
    """Listado con filtros por estado, búsqueda general y paginación"""
    estado = request.GET.get('estado', '')
    q = request.GET.get('q', '')
    
    qs = Encomienda.objects.con_relaciones()
    
    if estado:
        qs = qs.filter(estado=estado)
        
    if q:
        qs = qs.filter(
            Q(codigo__icontains=q) |
            Q(remitente__apellidos__icontains=q) |
            Q(destinatario__apellidos__icontains=q)
        )

    paginator = Paginator(qs, 15)
    page_number = request.GET.get('page', 1)
    encomiendas = paginator.get_page(page_number)

    return render(request, 'envios/lista.html', {
        'encomiendas': encomiendas,
        'estados': EstadoEnvio.choices,
        'estado_activo': estado,
        'q': q,
    })

# ── VISTAS DE DETALLE Y ACCIONES ───────────────────────────────

@login_required
def encomienda_detalle(request, pk):
    """Busca encomienda optimizada o devuelve 404"""
    enc = get_object_or_404(Encomienda.objects.con_relaciones(), pk=pk)
    return render(request, 'envios/detalle.html', {'encomienda': enc})

@login_required
def buscar_por_codigo(request, codigo):
    """Busca una encomienda por su código único de texto"""
    try:
        enc = Encomienda.objects.get(codigo=codigo.upper())
    except Encomienda.DoesNotExist:
        raise Http404(f'No existe la encomienda {codigo}')
    return render(request, 'envios/detalle.html', {'encomienda': enc})

@require_POST
@login_required
def encomienda_cambiar_estado(request, pk):
    """Procesa el cambio de estado mediante POST"""
    enc = get_object_or_404(Encomienda, pk=pk)
    nuevo_estado = request.POST.get('estado')
    observacion = request.POST.get('observacion', '')
    
    try:
        empleado = Empleado.objects.get(email=request.user.email)
        enc.cambiar_estado(nuevo_estado, empleado, observacion)
        # MENSAJE DE ÉXITO
        messages.success(request, f'Estado actualizado a: {enc.get_estado_display()}')
    except (ValueError, Empleado.DoesNotExist) as e:
        # MENSAJE DE ERROR
        messages.error(request, str(e))
        
    return redirect('encomienda_detalle', pk=pk)

# ── FORMULARIOS Y CREACIÓN / EDICIÓN ───────────────────────────

@require_http_methods(['GET', 'POST'])
@permission_required('envios.add_encomienda', raise_exception=True)
@login_required
def encomienda_crear(request):
    """Gestión de creación de encomiendas"""
    if request.method == 'POST':
        form = EncomiendaForm(request.POST)
        if form.is_valid():
            enc = form.save(commit=False)
            enc.empleado_registro = Empleado.objects.get(email=request.user.email)
            enc.save()
            # MENSAJE DE ÉXITO
            messages.success(request, f'Encomienda {enc.codigo} registrada correctamente.')
            return redirect('encomienda_detalle', pk=enc.pk)
        else:
            # MENSAJE DE ERROR EN FORMULARIO
            messages.error(request, 'Por favor, corrige los errores en el formulario.')
    else:
        form = EncomiendaForm()
        
    return render(request, 'envios/form.html', {'form': form, 'titulo': 'Nueva Encomienda'})

@require_http_methods(['GET', 'POST'])
@login_required
def encomienda_editar(request, pk):
    """Edición de encomienda existente"""
    enc = get_object_or_404(Encomienda, pk=pk)
    if request.method == 'POST':
        form = EncomiendaForm(request.POST, instance=enc)
        if form.is_valid():
            form.save()
            # MENSAJE DE ÉXITO
            messages.success(request, 'Datos actualizados correctamente.')
            return redirect('encomienda_detalle', pk=enc.pk)
        else:
            messages.error(request, 'Error al actualizar los datos.')
    else:
        form = EncomiendaForm(instance=enc)
    return render(request, 'envios/form.html', {'form': form, 'titulo': 'Editar Encomienda'})

@login_required
def eliminar_encomienda(request, pk):
    """Eliminación con validación de estado (solo Pendientes)"""
    enc = get_object_or_404(Encomienda, pk=pk)
    
    if enc.estado != 'PE': 
        raise PermissionDenied
        
    if request.method == 'POST':
        enc.delete()
        # MENSAJE DE ÉXITO
        messages.success(request, 'Encomienda eliminada con éxito.')
        return redirect('encomienda_lista')
    
    return render(request, 'envios/confirmar_eliminar.html', {'enc': enc})

# ── ENDPOINTS DE API / UTILITARIOS ──────────────────────────────

def encomienda_api(request, id_api):
    enc = get_object_or_404(Encomienda, id=id_api)
    return JsonResponse({'codigo': enc.codigo, 'estado': enc.estado})

def encomienda_estado_json(request, pk):
    enc = get_object_or_404(Encomienda, pk=pk)
    return JsonResponse({
        'codigo': enc.codigo,
        'estado': enc.estado,
        'display': enc.get_estado_display(),
        'retraso': enc.tiene_retraso,
        'dias': enc.dias_en_transito,
    })

def ping(request):
    return HttpResponse('pong', status=200, content_type='text/plain')

def health_check(request):
    """
    GET /health/
    Verifica que todos los servicios del sistema estén funcionando.
    Incluye el estado de Redis y del channel layer.
    """
    estado = {
        "postgres": False,
        "redis": False,
        "channels": False,
    }

    # 1. Verificar PostgreSQL
    try:
        from django.db import connection
        connection.ensure_connection()
        estado["postgres"] = True
    except Exception as e:
        estado["postgres_error"] = str(e)
        logger.error(f"Healthcheck: Error en PostgreSQL: {e}")

    # 2. Verificar Redis directamente
    try:
        r = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        r.ping()
        info = r.info()
        estado["redis"] = True
        estado["redis_memoria"] = info.get("used_memory_human")
        estado["redis_clientes"] = info.get("connected_clients")
        estado["redis_version"] = info.get("redis_version")
    except Exception as e:
        estado["redis_error"] = str(e)
        logger.error(f"Healthcheck: Error en Redis: {e}")

    # 3. Verificar Channel Layer (publicar un mensaje de prueba)
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer
        
        cl = get_channel_layer()
        async_to_sync(cl.group_send)(
            "health_check",
            {"type": "health.ping"}
        )
        estado["channels"] = True
    except Exception as e:
        estado["channels_error"] = str(e)
        logger.error(f"Healthcheck: Error en Channel Layer: {e}")

    # 4. Contar empleados conectados
    try:
        r = redis.from_url(settings.REDIS_URL)
        # Nota: Ajusta el prefijo según tu configuración ('encomiendas' en este caso)
        estado["empleados_conectados"] = r.scard(
            "encomiendas:group:encomiendas_global"
        )
    except Exception:
        estado["empleados_conectados"] = None

    # Evaluación final de salud del sistema
    todo_ok = all([estado["postgres"], estado["redis"], estado["channels"]])
    http_status = 200 if todo_ok else 503

    return JsonResponse(estado, status=http_status)