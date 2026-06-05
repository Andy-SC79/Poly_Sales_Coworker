import pytest
import yaml
from pathlib import Path
from core.brain.admin_tools import edit_file, list_workspace_files


@pytest.mark.asyncio
async def test_edit_file_dry_run(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('POLY_WORKSPACE_ROOT', str(tmp_path))
    result = await edit_file.arun({"path": "demo.txt", "content": "hola mundo", "mode": "replace", "dry_run": True})
    assert "edit_file (dry_run)" in result
    assert not (tmp_path / "demo.txt").exists()


@pytest.mark.asyncio
async def test_edit_file_replace_creates_backup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('POLY_WORKSPACE_ROOT', str(tmp_path))
    target = tmp_path / "demo.txt"
    target.write_text("original", encoding="utf-8")

    result = await edit_file.arun({"path": "demo.txt", "content": "nuevo contenido", "mode": "replace"})
    assert "actualizado" in result
    assert target.read_text(encoding="utf-8") == "nuevo contenido"
    assert ".bak." in result
    bak_files = list(tmp_path.glob("demo.txt.bak.*"))
    assert len(bak_files) == 1


@pytest.mark.asyncio
async def test_edit_file_append(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('POLY_WORKSPACE_ROOT', str(tmp_path))
    target = tmp_path / "demo.txt"
    target.write_text("primero\n", encoding="utf-8")

    result = await edit_file.arun({"path": "demo.txt", "content": "segundo\n", "mode": "append"})
    assert "Contenido añadido" in result
    assert target.read_text(encoding="utf-8") == "primero\nsegundo\n"


@pytest.mark.asyncio
async def test_edit_file_path_traversal_denied(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('POLY_WORKSPACE_ROOT', str(tmp_path))
    result = await edit_file.arun({"path": "../outside.txt", "content": "hola"})
    assert "Ruta fuera del workspace" in result
    assert not (tmp_path.parent / "outside.txt").exists()


@pytest.mark.asyncio
async def test_list_workspace_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('POLY_WORKSPACE_ROOT', str(tmp_path))
    (tmp_path / "a.txt").write_text("x", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.txt").write_text("y", encoding="utf-8")

    result = await list_workspace_files.arun({"path": ".", "depth": 1})
    assert "a.txt" in result
    assert "sub" in result


@pytest.mark.asyncio
async def test_execute_sql_query_permissions():
    """Test execute_sql_query respects role-based permissions."""
    from core.brain.admin_tools import execute_sql_query
    from core.brain.permissions import UserRole, get_user_role
    
    # Test admin access
    admin_result = await execute_sql_query.arun({
        "user_id": "admin_123",
        "sql_query": "SELECT * FROM catalog",
        "table": "catalog",
        "action": "SELECT"
    })
    assert "Ejecutada consulta" in str(admin_result) or "rows" in str(admin_result).lower()
    
    # Test customer access to non-ORDERS table (should be denied)
    customer_result = await execute_sql_query.arun({
        "user_id": "+573001234567",  # customer phone
        "sql_query": "SELECT * FROM catalog",
        "table": "catalog",
        "action": "SELECT"
    })
    assert "Permiso denegado" in str(customer_result)
    
    # Test user role detection
    admin_role = get_user_role("admin_001")
    assert admin_role == UserRole.ADMIN
    
    customer_role = get_user_role("+573001234567")
    assert customer_role == UserRole.CUSTOMER
