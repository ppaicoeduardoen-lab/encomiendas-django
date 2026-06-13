from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async

from envios.models import Encomienda

class EncomiendaConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
            
        self.group_name = 'encomiendas_global'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        
        stats = await self.get_estadisticas()
        await self.send_json({
            'tipo': 'conectado',
            'usuario': user.username,
            'mensaje': f'Bienvenido, {user.username}',
            'stats': stats,
        })

    async def receive_json(self, content, **kwargs):
        tipo = content.get('tipo')
        if tipo == 'ping':
            await self.send_json({'tipo': 'pong'})
        elif tipo == 'solicitar_stats':
            stats = await self.get_estadisticas()
            await self.send_json({
                'tipo': 'stats', 
                'stats': stats
            })
        elif tipo == 'suscribir_encomienda':
            enc_id = content.get('encomienda_id')
            if enc_id:
                await self.channel_layer.group_add(
                    f'encomienda_{enc_id}',
                    self.channel_name
                )
                await self.send_json({
                    'tipo': 'suscrito', 
                    'encomienda_id': enc_id
                })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def encomienda_estado_cambio(self, event):
        await self.send_json({
            'tipo': 'estado_cambio',
            'encomienda_id': event['encomienda_id'],
            'codigo': event['codigo'],
            'estado_anterior': event['estado_anterior'],
            'estado_nuevo': event['estado_nuevo'],
            'empleado': event['empleado'],
            'timestamp': event['timestamp'],
        })

    @database_sync_to_async
    def get_estadisticas(self):
        from .models import Encomienda
        return {
            'activas': Encomienda.objects.activas().count(),
            'en_transito': Encomienda.objects.en_transito().count(),
            'con_retraso': Encomienda.objects.con_retraso().count(),
        }
    @database_sync_to_async
    def get_encomiendas_activas(self):
   
    # Nota: Es mejor importar Encomienda al inicio del archivo, 
    # pero si necesitas evitar importaciones circulares, puedes dejarlo aquí.
        return list(Encomienda.objects.activas().con_relaciones())


    async def receive(self, text_data):
    # Uso en el consumer:
        encs = await self.get_encomiendas_activas()
    
    async def receive(self, text_data):
    # 1. Conteo asíncrono (.acount)
        count = await Encomienda.objects.activas().acount()
    
    # 2. Obtener un registro de forma asíncrona (.aget)
        enc = await Encomienda.objects.aget(pk=1)
    
    # 3. Guardar cambios de forma asíncrona (.asave)
        await enc.asave()

class DashboardConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close(code=4001)
            return
            
        self.group_name = 'dashboard'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()
        
        stats = await self.get_stats()
        await self.send_json({
            'tipo': 'stats_iniciales',
            'stats': stats,
        })

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def dashboard_actualizar(self, event):
        await self.send_json({
            'tipo': 'stats_actualizado',
            'stats': event['stats'],
        })

    async def estado_cambio(self, event):
        await self.send_json({
            'tipo': 'estado_cambio',
            'codigo': event['codigo'],
            'estado_anterior': event['estado_anterior'],
            'estado_nuevo': event['estado_nuevo'],
            'empleado': event['empleado'],
            'timestamp': event['timestamp'],
        })

    @database_sync_to_async
    def get_stats(self):
        from .models import Encomienda
        from django.utils import timezone
        hoy = timezone.now().date()
        return {
            'activas': Encomienda.objects.activas().count(),
            'en_transito': Encomienda.objects.en_transito().count(),
            'con_retraso': Encomienda.objects.con_retraso().count(),
            'entregadas_hoy': Encomienda.objects.filter(
                estado='EN', 
                fecha_entrega_real=hoy
            ).count(),
        }
class EncomiendaConsumer(AsyncWebsocketConsumer):

    async def receive(self, text_data):
        # Siempre envolver en try/except para evitar que la conexión
        # se cierre por un error no controlado
        try:
            data = json.loads(text_data)
            await self.procesar_mensaje(data)
        except json.JSONDecodeError:
            await self.send(
                text_data=json.dumps({
                    "tipo": "error",
                    "codigo": "JSON_INVALIDO",
                    "mensaje": "El mensaje no es JSON válido",
                })
            )
        except Exception as e:
            logger.error(f"Error en consumer: {e}", exc_info=True)
            await self.send(
                text_data=json.dumps({
                    "tipo": "error",
                    "codigo": "ERROR_INTERNO",
                    "mensaje": "Error interno del servidor",
                })
            )

    async def procesar_mensaje(self, data):
        tipo = data.get("tipo")
        
        if tipo == "ping":
            await self.send(text_data=json.dumps({"tipo": "pong"}))
            
        elif tipo == "solicitar_stats":
            stats = await self.get_estadisticas()
            await self.send(
                text_data=json.dumps({
                    "tipo": "stats", 
                    "stats": stats
                })
            )
            
        else:
            await self.send(
                text_data=json.dumps({
                    "tipo": "error", 
                    "mensaje": f"Tipo desconocido: {tipo}"
                })
            )