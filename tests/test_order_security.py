from types import SimpleNamespace

import pytest

from integrations.supabase_orders import submit_order_to_supabase
from integrations.supabase_queries import check_order_status


class FakeSupabase:
    def __init__(self, select_data=None):
        self.select_data = select_data or []
        self.insert_called = False
        self.update_called = False

    def table(self, name):
        return FakeQuery(self)


class FakeQuery:
    def __init__(self, client):
        self.client = client
        self.operation = None

    def select(self, *args, **kwargs):
        if self.operation is None:
            self.operation = "select"
        return self

    def eq(self, *args, **kwargs):
        return self

    def order(self, *args, **kwargs):
        return self

    def limit(self, *args, **kwargs):
        return self

    def insert(self, payload):
        self.client.insert_called = True
        self.operation = "insert"
        return self

    def update(self, payload):
        self.client.update_called = True
        self.operation = "update"
        return self

    def execute(self):
        if self.operation == "insert":
            return SimpleNamespace(data=[{"Order ID": 99}])
        if self.operation == "update":
            return SimpleNamespace(data=[{"Order ID": 42}])
        return SimpleNamespace(data=self.client.select_data)


def _order_payload(**overrides):
    payload = {
        "nombres": "Carlos",
        "apellidos": "Perez",
        "whatsapp": "+573001234567",
        "departamento": "Antioquia",
        "ciudad": "Medellin",
        "main_address": "CL 10 # 20-30",
        "neighborhood": "Centro",
        "producto": "Colageno",
        "valor_a_pagar": "85000",
        "caller_whatsapp": "+573001234567",
    }
    payload.update(overrides)
    return payload


@pytest.mark.asyncio
async def test_update_with_invalid_order_id_does_not_insert(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr("integrations.supabase_orders.get_supabase", lambda: fake)

    result = await submit_order_to_supabase(**_order_payload(order_id="P-ABC"))

    assert fake.insert_called is False
    assert result["id"] is None


@pytest.mark.asyncio
async def test_update_with_missing_order_does_not_insert(monkeypatch):
    fake = FakeSupabase(select_data=[])
    monkeypatch.setattr("integrations.supabase_orders.get_supabase", lambda: fake)

    result = await submit_order_to_supabase(**_order_payload(order_id="P-000042"))

    assert fake.insert_called is False
    assert result["id"] is None


@pytest.mark.asyncio
async def test_update_with_non_owner_phone_does_not_insert(monkeypatch):
    fake = FakeSupabase(select_data=[{"Whatsapp": "3009999999", "Status": "Creado", "Tracking Number": ""}])
    monkeypatch.setattr("integrations.supabase_orders.get_supabase", lambda: fake)

    result = await submit_order_to_supabase(**_order_payload(order_id="P-000042"))

    assert fake.insert_called is False
    assert result["id"] is None


@pytest.mark.asyncio
async def test_update_with_tracking_number_does_not_insert(monkeypatch):
    fake = FakeSupabase(select_data=[{"Whatsapp": "3001234567", "Status": "Creado", "Tracking Number": "GUIA123"}])
    monkeypatch.setattr("integrations.supabase_orders.get_supabase", lambda: fake)

    result = await submit_order_to_supabase(**_order_payload(order_id="P-000042"))

    assert fake.insert_called is False
    assert result["id"] is None


@pytest.mark.asyncio
async def test_create_without_order_id_inserts(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr("integrations.supabase_orders.get_supabase", lambda: fake)

    result = await submit_order_to_supabase(**_order_payload())

    assert fake.insert_called is True
    assert result["id"] == "P-000099"


def _sample_order(**overrides):
    order = {
        "Order ID": 42,
        "Nombres": "Carlos",
        "Apellidos": "Perez",
        "Indicativo Pais": "+57",
        "Whatsapp": "3001234567",
        "NÃºmero Alternativo": "",
        "Producto": "Colageno",
        "Oferta": "1 unidad",
        "Valor a Pagar": 85000,
        "Status": "Despachado",
        "Tracking Number": "GUIA123",
        "Delivery_Notes": "En ruta",
        "Direccion": "CL 10 # 20-30",
        "Indicaciones_Adicionales": "Barrio Centro",
        "Notas": "Nota privada",
        "Ciudad": "Medellin",
        "Timestamp": "2026-05-20T12:00:00Z",
    }
    order.update(overrides)
    return order


@pytest.mark.asyncio
async def test_customer_query_matching_origin_returns_sanitized_response(monkeypatch):
    fake = FakeSupabase(select_data=[_sample_order()])
    monkeypatch.setattr("integrations.supabase_queries.get_supabase", lambda: fake)

    result = await check_order_status(order_id="P-000042", caller_whatsapp="+573001234567")

    assert "Pedido encontrado" in result
    assert "Colageno" in result
    assert "Telefono" not in result
    assert "Direccion" not in result
    assert "Nota privada" not in result


@pytest.mark.asyncio
async def test_customer_query_non_matching_origin_requires_two_challenge_facts(monkeypatch):
    fake = FakeSupabase(select_data=[_sample_order()])
    monkeypatch.setattr("integrations.supabase_queries.get_supabase", lambda: fake)

    result = await check_order_status(order_id="P-000042", caller_whatsapp="+573009999999")

    assert "Por seguridad" in result


@pytest.mark.asyncio
async def test_customer_query_non_matching_origin_allows_two_valid_challenge_facts(monkeypatch):
    fake = FakeSupabase(select_data=[_sample_order()])
    monkeypatch.setattr("integrations.supabase_queries.get_supabase", lambda: fake)

    result = await check_order_status(
        order_id="P-000042",
        caller_whatsapp="+573009999999",
        verification_name="Carlos Perez",
        verification_city="Medellin",
    )

    assert "Pedido encontrado" in result
    assert "Telefono" not in result


@pytest.mark.asyncio
async def test_admin_query_returns_operational_detail(monkeypatch):
    fake = FakeSupabase(select_data=[_sample_order()])
    monkeypatch.setattr("integrations.supabase_queries.get_supabase", lambda: fake)

    result = await check_order_status(order_id="P-000042", caller_whatsapp="admin", is_admin=True)

    assert "DATOS CRUDOS" in result
    assert "Nota privada" in result
