# conftest.py (raiz del proyecto)
import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth.models import User
from django.utils import timezone
from envios.models import Empleado
from config.choices import EstadoGeneral

@pytest.fixture
def api_client():
    """Cliente de API sin autenticacion"""
    return APIClient()

@pytest.fixture
def user(db):
    """Usuario de prueba"""
    user = User.objects.create_user(
        username='test_empleado',
        email='empleado@encomiendas.pe',
        password='test1234',
    )
    Empleado.objects.create(
        codigo='EMP-TEST',
        nombres='Empleado',
        apellidos='Prueba',
        cargo='Operador',
        email=user.email,
        fecha_ingreso=timezone.now().date(),
        estado=EstadoGeneral.ACTIVO,
    )
    return user

@pytest.fixture
def auth_client(api_client, user):
    """Cliente de API con JWT valido"""
    refresh = RefreshToken.for_user(user)
    api_client.credentials(
        HTTP_AUTHORIZATION=f'Bearer {refresh.access_token}'
    )
    return api_client
