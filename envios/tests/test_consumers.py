import json
import pytest
from channels.layers import get_channel_layer
from channels.testing import WebsocketCommunicator
from config.asgi import application

from .factories import EmpleadoFactory, EncomiendaFactory, UserFactory


@pytest.mark.asyncio
@pytest.mark.django_db(transaction=True)
class TestEncomiendaConsumer:

    async def test_conexion_sin_autenticacion(self):
        """Sin autenticar: el servidor debe rechazar con codigo 4001"""
        communicator = WebsocketCommunicator(application, "/ws/encomiendas/")
        connected, code = await communicator.connect()
        assert not connected
        assert code == 4001
        await communicator.disconnect()

    async def test_conexion_autenticated(self):
        """Con usuario autenticado: el servidor acepta y envia stats"""
        from django.contrib.auth.models import AnonymousUser
        from django.test import RequestFactory
        from channels.db import database_sync_to_async  # Import añadido para que funcione database_sync_to_async

        user = await database_sync_to_async(UserFactory)()
        communicator = WebsocketCommunicator(application, "/ws/encomiendas/")
        
        # Inyectar el usuario en el scope para simular autenticacion
        communicator.scope["user"] = user
        connected, _ = await communicator.connect()
        assert connected

        # Recibir el mensaje de bienvenida
        response = await communicator.receive_json_from(timeout=3)
        assert response["tipo"] == "conectado"
        assert "stats" in response
        assert "activas" in response["stats"]
        await communicator.disconnect()

    async def test_ping_pong(self):
        """El consumer responde pong al recibir ping"""
        from channels.db import database_sync_to_async

        user = await database_sync_to_async(UserFactory)()
        communicator = WebsocketCommunicator(application, "/ws/encomiendas/")
        communicator.scope["user"] = user
        await communicator.connect()
        await communicator.receive_json_from(timeout=2)  # mensaje bienvenida

        # Enviar ping
        await communicator.send_json_to({"tipo": "ping"})

        # Recibir pong
        response = await communicator.receive_json_from(timeout=2)
        assert response["tipo"] == "pong"
        await communicator.disconnect()

    async def test_notificacion_via_channel_layer(self):
        """El consumer recibe y reenvía mensajes del channel layer"""
        from channels.db import database_sync_to_async

        user = await database_sync_to_async(UserFactory)()
        communicator = WebsocketCommunicator(application, "/ws/encomiendas/")
        communicator.scope["user"] = user
        await communicator.connect()
        await communicator.receive_json_from(timeout=2)  # bienvenida

        # Simular que el modelo envia una notificacion al channel layer
        channel_layer = get_channel_layer()
        await channel_layer.group_send(
            "encomiendas_global",
            {
                "type": "encomienda_estado_cambio",
                "encomienda_id": 1,
                "codigo": "ENC-2026-001",
                "estado_anterior": "PE",
                "estado_nuevo": "TR",
                "empleado": "Mendoza Cruz, Luis",
                "timestamp": "2026-05-14T10:00:00Z",
            },
        )

        # El consumer debe recibir y reenviar al cliente
        response = await communicator.receive_json_from(timeout=3)
        assert response["tipo"] == "estado_cambio"
        assert response["codigo"] == "ENC-2026-001"
        assert response["estado_nuevo"] == "TR"
        await communicator.disconnect()