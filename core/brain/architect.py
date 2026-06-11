"""
core/brain/architect.py
------------------------
Engineering tools for Poly. 
Allows the agent to self-inspect, analyze its configuration, 
and propose/apply improvements to its own personality and knowledge.

Security flow for file edits:
  1. Write to temp file
  2. Validate Python syntax (py_compile)
  3. Validate with ruff if available
  4. Generate diff for review
  5. Create .bak backup
  6. Write final file only if all checks pass
  7. Return clear status and diff
"""
import os
import shutil
import structlog
import py_compile
import subprocess
import difflib
from pathlib import Path
import yaml

log = structlog.get_logger()

# Archivos que Poly tiene permitido ver y editar
ALLOWED_CONFIG_FILES = [
    "config/personality.yaml",

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
    Usa esta herramienta obligatoriamente para leer archivos del sistema (YAML, Python, etc).
    Nunca digas al usuario que no puedes leer archivos. Ejecuta esta herramienta en su lugar.
    """
    try:
        if file_path not in ALLOWED_CONFIG_FILES:
            log.error("architect.read_denied", file=file_path)
            return f"❌ Permiso denegado: No tienes acceso a '{file_path}'.\nArchivos permitidos: {ALLOWED_CONFIG_FILES}"
        path = Path(file_path)
        if not path.exists():
            log.error("architect.read_missing", file=file_path)
            return f"❌ Archivo no encontrado: '{file_path}'"
        content = path.read_text(encoding="utf-8")
        log.info("architect.read_success", file=file_path, size_bytes=len(content))
        return f"📄 CONTENIDO DE {file_path}:\n\n{content}"
    except Exception as e:
        log.error("architect.read_failed", file=file_path, error=str(e))
        return f"❌ Error al leer '{file_path}': {str(e)}"

def update_system_config(file_path: str, new_content: str):
    """
    ¡MUY IMPORTANTE! TÚ SÍ PUEDES EDITAR ARCHIVOS DEL SISTEMA.
    Usa esta herramienta para actualizar configuración o código fuente.
    Nunca digas al usuario que no puedes modificar archivos. Usa esta herramienta para cumplir órdenes del Admin.
    
    Flujo de seguridad:
      1. Validar permiso en ALLOWED_CONFIG_FILES
      2. Escribir a archivo temporal
      3. Validar sintaxis Python (si es .py)
      4. Validar con ruff (si está disponible)
      5. Generar diff
      6. Crear backup .bak
      7. Escribir archivo final
      8. Retornar estado y diff
    """
    try:
        # Basic argument validation
        if not isinstance(file_path, str) or not file_path:
            log.error("architect.update_invalid_args", file=file_path)
            return "❌ Argumento inválido: 'file_path' debe ser una cadena no vacía."

        if not isinstance(new_content, str) or new_content.strip() == "":
            log.error("architect.update_invalid_content", file=file_path)
            return "❌ Argumento inválido: 'new_content' no puede estar vacío."

        if file_path not in ALLOWED_CONFIG_FILES:
            log.error("architect.update_denied", file=file_path)
            return f"❌ Permiso denegado: No tienes acceso a '{file_path}'."

        # If updating YAML, validate YAML syntax before writing
        if str(file_path).lower().endswith(('.yaml', '.yml')):
            try:
                # Will raise if invalid
                yaml.safe_load(new_content)
            except Exception as e:
                log.error("architect.update_invalid_yaml", file=file_path, error=str(e))
                return (
                    "❌ ERROR DE FORMATO: El contenido proporcionado no es YAML válido. "
                    "Corrige la sintaxis (indentación, listas, tipos) y vuelve a intentar.\n"
                    f"Detalles: {e}"
                )

        path = Path(file_path)
        backup_path = Path(f"{file_path}.bak")
        temp_path = Path(f"{file_path}.tmp")

        # 1. Escribir a temp file
        temp_path.write_text(str(new_content), encoding="utf-8")
        log.info("architect.temp_written", file=str(temp_path))
        
        # 2. Validar sintaxis Python si aplica
        is_python = str(file_path).endswith('.py')
        if is_python:
            try:
                py_compile.compile(str(temp_path), doraise=True)
                log.info("architect.syntax_valid", file=file_path)
            except py_compile.PyCompileError as e:
                temp_path.unlink(missing_ok=True)
                log.error("architect.syntax_error", file=file_path, error=str(e))
                return f"❌ ERROR DE SINTAXIS PYTHON.\n\nDetalles:\n{e.msg}\n\nCorrige el error y vuelve a intentar."
        
        # 3. Validar con ruff si está disponible
        if is_python:
            try:
                result = subprocess.run(
                    ["ruff", "check", str(temp_path)],
                    capture_output=True,
                    text=True,
                    timeout=5
                )
                if result.returncode != 0:
                    ruff_output = result.stdout + result.stderr
                    log.warning("architect.ruff_warnings", file=file_path, output=ruff_output[:200])
                else:
                    log.info("architect.ruff_passed", file=file_path)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                log.debug("architect.ruff_skipped", file=file_path)
        
        # 4. Generar diff
        diff_lines = []
        if path.exists():
            original_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
            new_lines = new_content.splitlines(keepends=True)
            diff = difflib.unified_diff(original_lines, new_lines, fromfile=file_path, tofile=file_path + " (NEW)")
            diff_lines = list(diff)
        
        diff_summary = "".join(diff_lines[:30]) if diff_lines else "[No changes in text]"
        if len(diff_lines) > 30:
            diff_summary += f"\n... ({len(diff_lines) - 30} líneas más)"
        
        # 5. Crear backup
        if path.exists():
            shutil.copy2(path, backup_path)
            log.info("architect.backup_created", file=str(backup_path))
        
        # 6. Escribir archivo final
        path.write_text(str(new_content), encoding="utf-8")
        log.info("architect.config_updated", file=file_path)
        
        # 7. Retornar estado
        status = f"""✅ ARCHIVO ACTUALIZADO EXITOSAMENTE

📁 Archivo: {file_path}
💾 Backup: {backup_path}

📋 DIFF:
{diff_summary}

Usa restore_system_config('{file_path}') si necesitas revertir."""
        
        return status
        
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        log.error("architect.update_failed", file=file_path, error=str(e))
        return f"❌ Error crítico: {str(e)}"

def restore_system_config(file_path: str):
    """
    Restaura un archivo desde su última copia de seguridad (.bak).
    Úsalo si cometiste un error o el Admin no está satisfecho con un cambio.
    """
    try:
        if file_path not in ALLOWED_CONFIG_FILES:
            log.error("architect.restore_denied", file=file_path)
            return f"❌ Permiso denegado: No puedes restaurar '{file_path}'."
        
        backup_path = Path(f"{file_path}.bak")
        original_path = Path(file_path)
        
        if not backup_path.exists():
            log.error("architect.restore_missing_backup", file=file_path)
            return f"❌ No existe backup para '{file_path}'."
        
        shutil.copy2(backup_path, original_path)
        log.info("architect.restored", file=file_path)
        return f"✅ RESTAURACIÓN EXITOSA\n\n'{file_path}' ha sido restaurado desde {backup_path}"
        
    except Exception as e:
        log.error("architect.restore_failed", file=file_path, error=str(e))
        return f"❌ Error al restaurar: {str(e)}"
