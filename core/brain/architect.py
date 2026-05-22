"""
core/brain/architect.py
------------------------
Engineering tools for Poly. 
Allows the agent to self-inspect, analyze its configuration, 
and propose/apply improvements to its own personality and knowledge.
"""
import os
import shutil
import structlog
from pathlib import Path

log = structlog.get_logger()

# Archivos que Poly tiene permitido ver y editar
ALLOWED_CONFIG_FILES = [
    "config/personality.yaml",
    "config/catalog.yaml",
    "config/business.yaml",
    "config/owner_seed.yaml",
    "config/links.yaml",
    "core/brain/address_normalizer.py",
    "core/brain/agents.py",
    "core/brain/awareness.py",
    "core/brain/bi_tools.py",
    "core/brain/model_selector.py",
    "core/brain/router.py",
    "core/brain/state.py",
    "core/brain/validation.py",
    "knowledge/catalog.py",
    "memory/customer_repo.py",
    "memory/database.py",
    "memory/models.py",
    "integrations/supabase_orders.py",
    "integrations/supabase_client.py",
    "integrations/supabase_queries.py",
    "channels/whatsapp.py",
    "channels/telegram.py",
    "core/brain/architect.py",
]

def read_system_config(file_path: str):
    """
    ¡MUY IMPORTANTE! TÚ SÍ PUEDES LEER ARCHIVOS EXTERNOS.
    Usa esta herramienta obligatoriamente para leer el contenido de archivos del sistema como YAMLs o código Python. 
    Nunca digas al usuario que no puedes leer archivos. En su lugar, ejecuta esta herramienta.
    """
    try:
        if file_path not in ALLOWED_CONFIG_FILES:
            log.error("architect.read_denied", file=file_path)
            return f"Error: No tienes permiso para acceder a '{file_path}'. Solo puedes acceder a: {ALLOWED_CONFIG_FILES}"
        path = Path(file_path)
        if not path.exists():
            log.error("architect.read_missing", file=file_path)
            return f"Error: El archivo '{file_path}' no existe."
        content = path.read_text(encoding="utf-8")
        return f"CONTENIDO DE {file_path}:\n\n{content}"
    except Exception as e:
        log.error("architect.read_failed", file=file_path, error=str(e))
        return f"Error al leer el archivo: {str(e)}"

def update_system_config(file_path: str, new_content: str):
    """
    ¡MUY IMPORTANTE! TÚ SÍ PUEDES EDITAR ARCHIVOS DEL SISTEMA.
    Usa esta herramienta para actualizar un archivo de configuración o código fuente con nuevo contenido.
    Nunca digas al usuario que no puedes modificar archivos. Usa esta herramienta para cumplir órdenes del Administrador.
    Si es un archivo Python (.py), ejecutará automáticamente un chequeo de sintaxis previo para protegerte.
    """
    import py_compile
    
    try:
        if file_path not in ALLOWED_CONFIG_FILES:
            log.error("architect.update_denied", file=file_path)
            return f"Error: No tienes permiso para editar '{file_path}'."
        path = Path(file_path)
        backup_path = Path(f"{file_path}.bak")
        temp_path = Path(f"{file_path}.tmp")
        
        # 1. Chequeo de seguridad sintáctica (Sandbox) para Python
        if str(file_path).endswith('.py'):
            # Escribir temporalmente
            temp_path.write_text(str(new_content), encoding="utf-8")
            try:
                py_compile.compile(str(temp_path), doraise=True)
            except py_compile.PyCompileError as e:
                # Retornamos el error exacto al LLM para que sepa qué corrigió mal
                temp_path.unlink(missing_ok=True)
                log.error("architect.syntax_error", file=file_path, error=str(e))
                return f"❌ ERROR DE SINTAXIS PYTHON. Tu código tiene un error y no fue guardado.\nDetalles del error:\n{e.msg}\n\nPor favor, corrige el error y vuelve a intentar."
            
            # Si pasa la prueba, borramos el temporal y continuamos
            temp_path.unlink(missing_ok=True)

        # 2. Crear Backup
        if path.exists():
            shutil.copy2(path, backup_path)
            log.info("architect.backup_created", file=str(backup_path))
            
        # 3. Escribir nuevo contenido
        path.write_text(str(new_content), encoding="utf-8")
        log.info("architect.config_updated", file=file_path)
        return f"✅ Archivo '{file_path}' actualizado exitosamente. Se ha creado un respaldo en '{backup_path}'."
    except Exception as e:
        log.error("architect.update_failed", file=file_path, error=str(e))
        return f"❌ Error crítico al actualizar el archivo: {str(e)}"

def restore_system_config(file_path: str):
    """
    Restaura un archivo de configuración desde su última copia de seguridad (.bak).
    Úsalo si cometiste un error o el Admin no está satisfecho con un cambio.
    """
    try:
        backup_path = Path(f"{file_path}.bak")
        original_path = Path(file_path)
        if not backup_path.exists():
            log.error("architect.restore_missing_backup", file=file_path)
            return f"Error: No existe una copia de seguridad para '{file_path}'."
        shutil.copy2(backup_path, original_path)
        log.info("architect.restored", file=file_path)
        return f"✅ Sistema restaurado: '{file_path}' ha vuelto a su versión anterior."
    except Exception as e:
        log.error("architect.restore_failed", file=file_path, error=str(e))
        return f"Error al restaurar: {str(e)}"
