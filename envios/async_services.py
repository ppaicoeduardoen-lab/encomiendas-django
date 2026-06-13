import asyncio
import httpx
from django.utils import timezone
from .models import Encomienda

async def verificar_estado_transportista(codigo: str) -> dict:
    """
    Corrutina que consulta la API del transportista.
    Puede pausarse mientras espera la respuesta HTTP.
    """
    url = f'https://api.transportista.pe/v1/track/{codigo}'
    try:
        async with httpx.AsyncClient() as client:
            # await: se pausa aqui. El event loop atiende otros requests.
            response = await client.get(url, timeout=5.0)
            data = response.json()
            return {
                'codigo': codigo,
                'encontrado': True,
                'estado_ext': data.get('status'),
                'ubicacion': data.get('location'),
                'timestamp': timezone.now().isoformat(),
            }
    except httpx.TimeoutException:
        return {'codigo': codigo, 'encontrado': False, 'error': 'timeout'}
    except httpx.ConnectError:
        return {'codigo': codigo, 'encontrado': False, 'error': 'conexion'}

async def actualizar_estados_en_transito() -> list:
    """
    Actualiza el estado de todas las encomiendas en transito
    consultando la API del transportista en paralelo.
    """
    # 1. Obtener encomiendas en transito (query async)
    encomiendas = await Encomienda.objects.en_transito().alist()
    if not encomiendas:
        return []
        
    # 2. Consultar el transportista para TODAS en paralelo
    # Sin async: 50 enc * 1s = 50 segundos
    # Con async: ~1 segundo (todas en paralelo)
    resultados = await asyncio.gather(
        *[verificar_estado_transportista(enc.codigo) for enc in encomiendas],
        return_exceptions=True
    )
    
    # 3. Procesar los resultados
    actualizadas = []
    for enc, resultado in zip(encomiendas, resultados):
        if isinstance(resultado, Exception):
            continue # ignorar errores individuales
            
        if resultado.get('encontrado') and resultado.get('estado_ext') == 'DELIVERED':
            # La encomienda fue entregada segun el transportista
            enc.estado = 'EN'
            enc.fecha_entrega_real = timezone.now().date()
            await enc.asave() # guardar async
            actualizadas.append(enc.codigo)
            
    return actualizadas
async def verificar_una(session: httpx.AsyncClient, codigo: str) -> dict:
    """Verifica UNA encomienda. Se ejecuta en paralelo con las demas."""
    try:
        r = await session.get(
            f'https://api.transportista.pe/track/{codigo}',
            timeout=5.0
        )
        return {'codigo': codigo, 'ok': True, 'data': r.json()}
    except httpx.TimeoutException:
        return {'codigo': codigo, 'ok': False, 'error': 'timeout'}
    except Exception as e:
        return {'codigo': codigo, 'ok': False, 'error': str(e)}

async def verificar_lote_completo() -> dict:
    """
    Verifica TODAS las encomiendas en transito en paralelo.
    SINCRONO:
    50 encomiendas * 1s por consulta = 50 SEGUNDOS
    ASINCRONO: todas en paralelo
    = ~1 SEGUNDO
    """
    # 1. Obtener encomiendas en transito de la BD
    encomiendas = await Encomienda.objects.en_transito().alist()
    if not encomiendas:
        return {'verificadas': 0, 'resultados': []}
        
    print(f'Verificando {len(encomiendas)} encomiendas en paralelo...')
    
    # 2. Abrir una sesion HTTP compartida para todas las consultas
    async with httpx.AsyncClient() as session:
        # 3. Lanzar TODAS las consultas a la vez
        tareas = [
            verificar_una(session, enc.codigo)
            for enc in encomiendas
        ]
        
        # gather: las ejecuta en paralelo y espera a que todas terminen
        resultados = await asyncio.gather(*tareas, return_exceptions=True)
        
    # 4. Separar exitosas de fallidas
    exitosas = [r for r in resultados if isinstance(r, dict) and r['ok']]
    fallidas = [r for r in resultados if isinstance(r, dict) and not r['ok']]
    errores = [r for r in resultados if isinstance(r, Exception)]
    
    return {
        'verificadas': len(encomiendas),
        'exitosas': len(exitosas),
        'fallidas': len(fallidas),
        'errores': len(errores),
        'resultados': resultados,
    }

# Llamar desde un comando de management o una vista async
# python manage.py shell
# import asyncio
# from envios.async_services import verificar_lote_completo
# asyncio.run(verificar_lote_completo())
async def verificar_con_timeout(enc) -> dict:
    """
    Verifica una encomienda en la API del transportista.
    Si no responde en 3 segundos, devuelve el ultimo estado conocido.
    """
    try:
        # Maximo 3 segundos para la API externa
        resultado = await asyncio.wait_for(
            verificar_api_externa(enc.codigo),
            timeout=3.0
        )
        return resultado
    except asyncio.TimeoutError:
        # La API tardo mas de 3s -> devolver datos de nuestra BD
        return {
            'codigo': enc.codigo,
            'estado': enc.get_estado_display(),
            'fuente': 'cache_local',
            'advertencia': 'API del transportista no disponible',
        }

async def verificar_lote_con_timeout(codigos: list) -> list:
    """
    Verifica multiples encomiendas, cada una con su propio timeout.
    Las que fallen (timeout, error de red) devuelven datos del cache.
    """
    encomiendas = await Encomienda.objects.filter(
        codigo__in=codigos
    ).alist()
    
    resultados = await asyncio.gather(
        *[verificar_con_timeout(enc) for enc in encomiendas],
        return_exceptions=True
    )
    
    return [
        r if not isinstance(r, Exception) else {'error': str(r)}
        for r in resultados
    ]