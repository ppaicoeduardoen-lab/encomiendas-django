from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django.utils import timezone
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend
from django.conf import settings
from django.core.cache import cache
from api.throttles import EmpleadoRateThrottle, CambioEstadoThrottle
from api.exceptions import EstadoInvalidoError, EncomiendaYaEntregadaError
from api.permissions import EsEmpleadoActivo, EsPropietarioOAdmin


# Imports de drf-spectacular
from drf_spectacular.utils import (
    extend_schema,
    extend_schema_view,
    OpenApiParameter,
    OpenApiResponse,
    OpenApiExample,
)
from drf_spectacular.types import OpenApiTypes

# Imports locales
from .models import Encomienda, Empleado
from api.filters import EncomiendaFilter
from .serializers import (
    EncomiendaSerializer,
    EncomiendaListSerializer,
    EncomiendaDetailSerializer,
    EncomiendaV2Serializer,
    HistorialEstadoSerializer,
)
from api.pagination import EncomiendaPagination, HistorialPagination

def get_empleado_for_user(user):
    try:
        return user.empleado
    except Exception:
        return Empleado.objects.get(email=user.email)


@extend_schema_view(
    list=extend_schema(
        summary='Listar encomiendas',
        description='Devuelve la lista paginada de encomiendas. Soporta filtros por estado, busqueda y ordenamiento.',
        tags=['Encomiendas'],
    ),
    create=extend_schema(
        summary='Crear encomienda',
        description='Registra una nueva encomienda en el sistema.',
        tags=['Encomiendas'],
    ),
    retrieve=extend_schema(
        summary='Detalle de encomienda',
        description='Devuelve los datos completos de una encomienda con remitente, destinatario, ruta e historial de estados.',
        tags=['Encomiendas'],
    ),
    update=extend_schema(
        summary='Actualizar encomienda',
        tags=['Encomiendas']
    ),
    partial_update=extend_schema(
        summary='Actualizar parcial',
        tags=['Encomiendas']
    ),
    destroy=extend_schema(
        summary='Eliminar encomienda',
        tags=['Encomiendas']
    ),
)
class EncomiendaViewSet(viewsets.ModelViewSet):
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = EncomiendaFilter
    permission_classes = [EsEmpleadoActivo]
    search_fields = [
        'codigo',
        'remitente__apellidos',
        'destinatario__apellidos',
        'descripcion',
    ]
    ordering_fields = ['fecha_registro', 'peso_kg', 'costo_envio']
    ordering = ['-fecha_registro']
    
    queryset = Encomienda.objects.con_relaciones()
    serializer_class = EncomiendaSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = EncomiendaPagination 
    
    throttle_classes = [EmpleadoRateThrottle]

    def get_throttles(self):
        """Throttle diferente para la acción cambiar_estado"""
        if self.action == 'cambiar_estado':
            return [CambioEstadoThrottle()]
        return super().get_throttles()
    
    def get_permissions(self):
        """Permisos distintos según la acción"""
        if self.action in ['update', 'partial_update', 'destroy']:
            return [EsEmpleadoActivo(), EsPropietarioOAdmin()]
        return [EsEmpleadoActivo()]

    def get_serializer_class(self):
        """
        Elegir el serializer segun la version Y la accion.
        v1 list -> EncomiendaListSerializer (ligero)
        v1 retrieve -> EncomiendaDetailSerializer (con anidados)
        v1 write -> EncomiendaSerializer (estandar)
        v2 cualquier accion -> EncomiendaV2Serializer
        """
        version = getattr(self.request, 'version', 'v1')
        # v2: un solo serializer para todo
        if version == 'v2':
            return EncomiendaV2Serializer
        
        # v1: serializer segun la accion
        if self.action == 'list':
            return EncomiendaListSerializer
        if self.action == 'retrieve':
            return EncomiendaDetailSerializer
        return EncomiendaSerializer

    def get_queryset(self):
        """
        v1 y v2 usan el mismo queryset optimizado.
        Si en el futuro v2 necesita datos extra, se agrega aqui.
        """
        qs = Encomienda.objects.con_relaciones().prefetch_related('historial')
        estado = self.request.query_params.get('estado')
        if estado:
            qs = qs.filter(estado=estado)
        q = self.request.query_params.get('search')
        if q:
            from django.db.models import Q
            qs = qs.filter(
            Q(codigo__icontains=q) |
            Q(remitente__apellidos__icontains=q) |
            Q(destinatario__apellidos__icontains=q)
        )
        
        return qs

    def list(self, request, *args, **kwargs):
        """Agregar cabecera X-API-Version en la respuesta"""
        response = super().list(request, *args, **kwargs)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    def retrieve(self, request, *args, **kwargs):
        """Agregar cabecera X-API-Version en el detalle"""
        response = super().retrieve(request, *args, **kwargs)
        response['X-API-Version'] = getattr(request, 'version', 'v1')
        return response

    def perform_create(self, serializer):
        serializer.save(
            empleado_registro=get_empleado_for_user(self.request.user)
        )
        
    @extend_schema(
        summary='Crear multiples encomiendas',
        description='Crea varias encomiendas en una sola peticion. Body: lista de objetos.',
        tags=['Encomiendas'],
    )
    @action(detail=False, methods=['post'], url_path='bulk_create')
    def bulk_create(self, request):
        serializer = self.get_serializer(
            data=request.data, many=True
        )
        if not serializer.is_valid():
            return Response(
                serializer.errors,
                status=status.HTTP_400_BAD_REQUEST
            )
        # Asignar el empleado a todas las encomiendas
        empleado = get_empleado_for_user(request.user)
        encomiendas = serializer.save(empleado_registro=empleado)
        return Response(
            self.get_serializer(encomiendas, many=True).data,
            status=status.HTTP_201_CREATED
        )

    @extend_schema(
        summary='Cambiar estado a multiples encomiendas',
        description='Cambia el estado de varias encomiendas. Reporta cuales tuvieron errores.',
        tags=['Encomiendas'],
    )
    @action(detail=False, methods=['patch'], url_path='bulk_estado')
    def bulk_estado(self, request):
        """
        PATCH /api/v1/encomiendas/bulk_estado/
        Body: {"ids": [1, 2, 3], "estado": "TR", "observacion": "..."}
        Procesa cada encomienda y reporta cuales tuvieron errores.
        """
        ids = request.data.get('ids', [])
        nuevo_estado = request.data.get('estado')
        observacion = request.data.get('observacion', '')

        # Validar que llegaron los campos requeridos
        if not ids:
            return Response(
                {'error': 'El campo ids es requerido y no puede estar vacio.'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not nuevo_estado:
            return Response(
                {'error': 'El campo estado es requerido.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            empleado = Empleado.objects.get(email=request.user.email)
        except Empleado.DoesNotExist:
            return Response(
                {'error': 'El usuario no tiene un empleado asociado.'},
                status=status.HTTP_403_FORBIDDEN
            )

        encomiendas = Encomienda.objects.filter(id__in=ids)
        actualizadas = []
        errores = []

        for enc in encomiendas:
            try:
                enc.cambiar_estado(nuevo_estado, empleado, observacion)
                actualizadas.append(enc.id)
            except ValueError as e:
                errores.append({'id': enc.id, 'error': str(e)})

        # Ids que no existen
        ids_procesados = list(encomiendas.values_list('id', flat=True))
        no_encontrados = [i for i in ids if i not in ids_procesados]

        return Response({
            'actualizadas': actualizadas,
            'errores': errores,
            'no_encontrados': no_encontrados,
            'total': len(actualizadas),
        })

    @extend_schema(
        summary='Cambiar estado de encomienda',
        description='''
        Cambia el estado de una encomienda y registra el cambio
        automaticamente en el historial de estados.
        Estados disponibles:
        - PE: Pendiente
        - TR: En transito
        - DE: En destino
        - EN: Entregado
        - DV: Devuelto
        ''',
        request=OpenApiTypes.OBJECT,
        responses={
            200: EncomiendaSerializer,
            400: OpenApiResponse(description='Estado invalido o ya en ese estado'),
        },
        examples=[
            OpenApiExample(
                'Pasar a En transito',
                value={'estado': 'TR', 'observacion': 'Recogido en agencia Lima'},
                request_only=True,
            ),
            OpenApiExample(
                'Marcar como Entregado',
                value={'estado': 'EN', 'observacion': 'Entregado al destinatario'},
                request_only=True,
            ),
        ],
        tags=['Encomiendas'],
    )
    @action(detail=True, methods=['post'], url_path='cambiar_estado')
    def cambiar_estado(self, request, pk=None):
        enc = self.get_object()
        nuevo_estado = request.data.get('estado')
        observacion = request.data.get('observacion', '')
        if not nuevo_estado:
            return Response({'error': 'El campo estado es requerido.'}, status=status.HTTP_400_BAD_REQUEST)
        
        if enc.esta_entregada:
            raise EncomiendaYaEntregadaError()

        try:
            empleado = get_empleado_for_user(request.user)
            enc.cambiar_estado(nuevo_estado, empleado, observacion)
            cache.delete(f'estadisticas_empleado_{request.user.id}')
            return Response(EncomiendaSerializer(enc).data)
        except ValueError as e:
            raise EstadoInvalidoError(detail=str(e))

    @extend_schema(
        summary='Encomiendas con retraso',
        description='Lista todas las encomiendas activas cuya fecha estimada de entrega ya pasó.',
        tags=['Encomiendas'],
        responses={200: EncomiendaSerializer(many=True)},
    )
    @action(detail=False, methods=['get'], url_path='con_retraso')
    def con_retraso(self, request):
        qs = Encomienda.objects.con_retraso().con_relaciones()
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        summary='Encomiendas pendientes',
        description='Lista todas las encomiendas en estado Pendiente.',
        tags=['Encomiendas'],
    )
    @action(detail=False, methods=['get'])
    def pendientes(self, request):
        qs = Encomienda.objects.pendientes().con_relaciones()
        return Response(self.get_serializer(qs, many=True).data)

    @extend_schema(
        summary='Historial de estados',
        description='Devuelve el historial de cambios de estado de una encomienda, paginado con limit/offset.',
        parameters=[
            OpenApiParameter('limit', type=int, description='Numero de resultados', default=10),
            OpenApiParameter('offset', type=int, description='Posicion de inicio', default=0),
        ],
        tags=['Encomiendas'],
    )
    @action(detail=True, methods=['get'], url_path='historial')
    def historial(self, request, pk=None):
        enc = self.get_object()
        qs = enc.historial.select_related('empleado').order_by('-fecha_cambio')
        paginator = HistorialPagination()
        page = paginator.paginate_queryset(qs, request)
        if page is not None:
            return paginator.get_paginated_response(
                HistorialEstadoSerializer(page, many=True).data
            )
        return Response(HistorialEstadoSerializer(qs, many=True).data)

    @extend_schema(
        summary='Estadísticas globales',
        description='Contadores del sistema: activas, en tránsito, con retraso y entregadas hoy.',
        tags=['Encomiendas'],
        responses={200: OpenApiResponse(description='Objeto con contadores')},
    )
    @action(detail=False, methods=['get'])
    def estadisticas(self, request):
        cache_key = f'estadisticas_empleado_{request.user.id}'
        data = cache.get(cache_key)
        if data is not None:
            return Response(data)

        hoy = timezone.now().date()
        data = {
            'total_activas': Encomienda.objects.activas().count(),
            'en_transito': Encomienda.objects.en_transito().count(),
            'con_retraso': Encomienda.objects.con_retraso().count(),
            'entregadas_hoy': Encomienda.objects.filter(
                estado='EN', fecha_entrega_real=hoy
            ).count(),
        }
        cache.set(cache_key, data, getattr(settings, 'CACHE_TTL', 60 * 15))
        return Response(data)
        
