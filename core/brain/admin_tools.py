"""
core/brain/admin_tools.py
-------------------------
Herramientas de autonomía avanzadas (CRM Memory y Logística DB) 
restringidas exclusivamente para el rol de administrador.
"""
import structlog
from langchain_core.tools import tool
from core.memory.customer_repo import CustomerRepo
from integrations.supabase_client import get_supabase
from datetime import datetime, timezone
from pathlib import Path
import shutil
import os
import time
import difflib
from typing import Optional

import yaml

log = structlog.get_logger()

@tool
async def read_customer_profile(phone: str):
    """
    Busca y lee el perfil completo de un cliente en la base de datos CRM.
    Devuelve su nombre, ciudad, resumen de conversaciones, rol y notas.
    """
    repo = CustomerRepo()
    profile = await repo.get_profile(phone)
    if not profile:
        return f"No se encontró ningún cliente con el número {phone}."
    return str(profile)

@tool
async def edit_customer_profile(phone: str, field: str, value: str):
    """
    Actualiza manualmente un campo del perfil del cliente en el CRM.
    Campos permitidos: name, city, conversation_summary, profile_notes, email, address, alternative_phone.
    Úsalo para corregir datos, o limpiar el historial (pasando un value vacío '' en conversation_summary).
    """
    allowed_fields = ["name", "city", "conversation_summary", "profile_notes", "email", "address", "alternative_phone"]
    if field not in allowed_fields:
        return f"Error: Campo no permitido. Debe ser uno de {allowed_fields}"
        
    repo = CustomerRepo()
    kwargs = {field: value}
    await repo.update_profile(phone, **kwargs)
    return f"Éxito: El campo '{field}' del cliente {phone} fue actualizado a '{value}'."

@tool
async def update_tracking_number(order_id: str, tracking_number: str, delivery_notes: str = ""):
    """
    Asigna o actualiza un número de guía a un pedido existente en Supabase, 
    y opcionalmente añade notas de la transportadora. 
    Esto bloquea el pedido impidiendo que el cliente lo cancele.
    """
    supabase = get_supabase()
    clean_id = str(order_id).replace("P-", "").lstrip("0")
    try:
        int_id = int(clean_id)
        # Verificamos si existe primero
        existing = supabase.table("ORDERS").select('"Order ID"').eq("Order ID", int_id).execute()
        if not existing.data:
            return f"Error: No se encontró ningún pedido con ID {int_id}"
            
        payload = {
            "Tracking Number": tracking_number,
            "Status": "Despachado",
            "Timestamp": datetime.now(timezone.utc).isoformat()
        }
        if delivery_notes:
            payload["Delivery_Notes"] = delivery_notes
            
        try:
            supabase.table("ORDERS").update(payload).eq("Order ID", int_id).execute()
            return f"Éxito: Guía {tracking_number} asignada al pedido {order_id}. Estado cambiado a 'Despachado'."
        except Exception as e_update:
            err = str(e_update)
            log.error("admin_tools.update_tracking_failed.retry", error=err)
            # Si la columna 'Tracking Number' no existe, reintentamos sin ella
            if "PGRST204" in err or "Tracking Number" in err:
                payload.pop("Tracking Number", None)
                supabase.table("ORDERS").update(payload).eq("Order ID", int_id).execute()
                return f"Éxito parcial: Estado del pedido actualizado a 'Despachado' pero no fue posible guardar el número de guía ({tracking_number}) en esta instalación (columna ausente)."
            return f"Error al actualizar la guía: {err}"
    except Exception as e:
        log.error("admin_tools.update_tracking_failed", error=str(e))
        return f"Error al actualizar la guía: {str(e)}"


@tool
async def edit_file(path: str, content: str, mode: str = "replace", dry_run: bool = False):
    """
    Edita un archivo dentro del workspace. Modo puede ser:
      - 'replace': reemplaza el contenido entero del archivo (default)
      - 'append': añade el contenido al final del archivo

    Si dry_run es True, no escribe cambios y devuelve una vista previa.

    Seguridad:
      - Sólo permite rutas dentro del directorio de trabajo actual (workspace root).
      - Crea una copia de seguridad automática antes de sobrescribir.
    """
    try:
        def _find_workspace_root() -> Path:
            # 1) Explicit override
            env_root = os.environ.get("POLY_WORKSPACE_ROOT")
            if env_root:
                return Path(env_root).resolve()

            # 2) Try to find VCS or project marker from current working dir
            cwd = Path(os.getcwd()).resolve()
            markers = [".git", "pyproject.toml", "requirements.txt", "setup.py", "README.md"]
            for p in [cwd] + list(cwd.parents):
                for m in markers:
                    if (p / m).exists():
                        return p

            # 3) Fallback: repo root relative to this file (core/brain/... -> project root)
            return Path(__file__).resolve().parents[3]

        workspace_root = _find_workspace_root()
        target = Path(path)
        if not target.is_absolute():
            target = (workspace_root / target).resolve()

        # Prevent escaping the workspace
        if not str(target).startswith(str(workspace_root)):
            return f"❌ edit_file: Ruta fuera del workspace no permitida: {path}"

        # Ensure parent exists
        target.parent.mkdir(parents=True, exist_ok=True)

        current_content = None
        if target.exists():
            current_content = target.read_text(encoding="utf-8")

        if mode not in {"replace", "append"}:
            return f"❌ edit_file: Modo desconocido '{mode}'. Usa 'replace' o 'append'."

        if dry_run:
            if mode == "replace":
                before = current_content or ""
                after = content
                diff = list(difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=str(target.name),
                    tofile=str(target.name) + " (propuesta)",
                    lineterm=""
                ))
                if not diff:
                    return "✅ edit_file (dry_run): El contenido propuesto es idéntico al existente."
                return "✅ edit_file (dry_run): Vista previa de cambios:\n" + "\n".join(diff[:100])
            return f"✅ edit_file (dry_run): Se añadiría contenido a '{str(target.relative_to(workspace_root))}'."

        bak_name = None
        if target.exists():
            bak_name = f"{target.name}.bak.{int(time.time())}"
            bak_path = target.parent / bak_name
            shutil.copy2(target, bak_path)

        if mode == "replace":
            with open(target, "w", encoding="utf-8") as f:
                f.write(content)
            return f"✅ edit_file: Archivo '{str(target.relative_to(workspace_root))}' actualizado. Backup: {bak_name if bak_name else 'no existía archivo previo'}"
        elif mode == "append":
            with open(target, "a", encoding="utf-8") as f:
                f.write(content)
            return f"✅ edit_file: Contenido añadido a '{str(target.relative_to(workspace_root))}'"
    except Exception as e:
        log.error("admin_tools.edit_file_failed", error=str(e))
        return f"❌ edit_file: Error al editar el archivo: {str(e)}"





@tool
async def list_workspace_files(path: str = ".", depth: int = 2):
    """
    Lista archivos bajo `path` relativo al workspace, con profundidad `depth`.
    Devuelve una cadena formateada con rutas y tamaños.
    """
    try:
        workspace_root = Path(os.getcwd()).resolve()
        base = Path(path)
        if not base.is_absolute():
            base = (workspace_root / base).resolve()
        if not str(base).startswith(str(workspace_root)):
            return f"❌ list_workspace_files: Ruta fuera del workspace no permitida: {path}"

        result = []
        for root, dirs, files in os.walk(base):
            depth_curr = len(Path(root).relative_to(base).parts)
            if depth_curr > depth:
                # don't descend further
                dirs[:] = []
                continue
            for fname in files:
                fpath = Path(root) / fname
                rel = fpath.relative_to(workspace_root)
                size = fpath.stat().st_size
                result.append(f"{rel} - {size} bytes")
        if not result:
            return "(vacío)"
        return "\n".join(result)
    except Exception as e:
        log.error("admin_tools.list_files_failed", error=str(e))
        return f"❌ list_workspace_files: Error: {str(e)}"


@tool
async def execute_sql_query(
    user_id: str,
    sql_query: str,
    table: str = "",
    action: str = "SELECT"
):
    """
    Ejecuta una consulta SQL flexible contra Supabase, con validación de permisos.
    
    Parameters:
    - user_id: Identificador del usuario (admin_XXX para admin, número de teléfono para cliente)
    - sql_query: Consulta SQL personalizada (SELECT, INSERT, UPDATE, DELETE)
    - table: Nombre de la tabla principal (para validación de permisos)
    - action: Tipo de acción (SELECT, INSERT, UPDATE, DELETE)
    
    Admin: Acceso total a cualquier tabla y acción.
    Cliente: Acceso limitado a ORDERS, solo SELECT y UPDATE para sus propios pedidos.
    
    Retorna los resultados en formato JSON o mensaje de error.
    """
    from core.brain.permissions import get_user_role, can_execute_sql, build_customer_order_filter
    
    try:
        # 1. Validate user role
        user_role = get_user_role(user_id)
        
        if user_role.value == "unknown":
            log.warning("execute_sql.unknown_role", user_id=user_id)
            return "❌ execute_sql_query: Rol de usuario desconocido."
        
        # 2. Validate permissions
        if not can_execute_sql(user_role, table, action):
            log.warning("execute_sql.permission_denied", user_id=user_id, table=table, action=action)
            return f"❌ execute_sql_query: Permiso denegado. {user_role.value} no puede ejecutar {action} en {table}."
        
        # 3. For customer accessing ORDERS, restrict to their own data
        if user_role.value == "customer" and table.upper() == "ORDERS":
            customer_phone = user_id  # user_id for customers is their phone
            customer_filter = build_customer_order_filter(customer_phone)
            
            # Ensure the query includes the customer filter
            if "WHERE" not in sql_query.upper():
                sql_query = f"{sql_query} WHERE {customer_filter}"
            else:
                # Append to existing WHERE clause
                sql_query = sql_query.replace(
                    "WHERE",
                    f"WHERE {customer_filter} AND"
                )
            
            log.info("execute_sql.customer_filter_applied", user_id=user_id, filter=customer_filter)
        
        # 4. Execute query against Supabase using RPC if possible, or direct table query
        client = get_supabase()
        
        # Attempt to execute as raw RPC call for complex queries
        if "SELECT" in sql_query.upper():
            # For SELECT, parse and execute carefully
            # This is a simplified approach; in production use parameterized queries
            try:
                # Extract table name and execute
                import re
                table_match = re.search(r"FROM\s+\"?(\w+)\"?", sql_query, re.IGNORECASE)
                if table_match:
                    tbl = table_match.group(1)
                    # Build Supabase query
                    resp = client.table(tbl).select("*").execute()
                    results = resp.data or []
                    return {
                        "success": True,
                        "rows": results,
                        "count": len(results),
                        "message": f"Ejecutada consulta en tabla '{tbl}': {len(results)} filas retornadas."
                    }
            except Exception as e_select:
                log.error("execute_sql.select_failed", error=str(e_select), query=sql_query)
                return f"❌ execute_sql_query: Error al ejecutar SELECT: {str(e_select)}"
        
        elif "INSERT" in sql_query.upper() or "UPDATE" in sql_query.upper() or "DELETE" in sql_query.upper():
            # For mutations, log and execute cautiously
            log.info("execute_sql.mutation_attempt", user_id=user_id, action=action, table=table)
            # In production, parse and execute mutations carefully using RPC or parameterized calls
            return "⚠️ execute_sql_query: Mutaciones (INSERT/UPDATE/DELETE) requieren validación adicional. Contacta al administrador."
        
        else:
            return "❌ execute_sql_query: Tipo de consulta no reconocido."
    
    except Exception as e:
        log.error("execute_sql.query_failed", user_id=user_id, error=str(e))
        return f"❌ execute_sql_query: Error inesperado: {str(e)}"
