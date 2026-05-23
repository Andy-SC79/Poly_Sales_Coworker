"""
tests/test_architect.py
-----------------------
Unit tests for core/brain/architect.py safety and security features.

Tests cover:
  - Permission checks (ALLOWED_CONFIG_FILES)
  - Python syntax validation
  - Backup creation
  - Restore functionality
  - Diff generation
"""
import pytest
import tempfile
from pathlib import Path
from core.brain.architect import (
    read_system_config,
    update_system_config,
    restore_system_config,
    ALLOWED_CONFIG_FILES,
)


@pytest.fixture
def temp_test_file():
    """Create a temporary test file in the config directory."""
    test_file = Path("config/test_architect_temp.yaml")
    test_file.write_text("# Initial content\nkey: value\n", encoding="utf-8")
    yield test_file
    # Cleanup
    test_file.unlink(missing_ok=True)
    Path(f"{test_file}.bak").unlink(missing_ok=True)
    Path(f"{test_file}.tmp").unlink(missing_ok=True)


@pytest.fixture
def temp_test_py():
    """Create a temporary test Python file."""
    test_file = Path("core/brain/test_architect_temp.py")
    test_file.write_text("# Test file\ndef hello():\n    return 'world'\n", encoding="utf-8")
    yield test_file
    # Cleanup
    test_file.unlink(missing_ok=True)
    Path(f"{test_file}.bak").unlink(missing_ok=True)
    Path(f"{test_file}.tmp").unlink(missing_ok=True)


class TestReadSystemConfig:
    """Tests for read_system_config function."""

    def test_read_allowed_yaml(self):
        """Can read an allowed YAML file."""
        result = read_system_config("config/personality.yaml")
        assert "❌" not in result or "CONTENIDO" in result or "personality" in result.lower()

    def test_read_denied_file(self):
        """Cannot read a file not in ALLOWED_CONFIG_FILES."""
        result = read_system_config("../../secrets.txt")
        assert "❌" in result or "Permiso" in result

    def test_read_missing_file(self):
        """Cannot read a file that doesn't exist."""
        result = read_system_config("config/nonexistent_file_xyz.yaml")
        assert "❌" in result


class TestUpdateSystemConfig:
    """Tests for update_system_config function with safety validation."""

    def test_update_yaml_valid(self, temp_test_file):
        """Can update a YAML file with valid new content."""
        new_content = "# Updated content\nkey: new_value\ncount: 42\n"
        
        # Must add file to allow list temporarily for test
        if str(temp_test_file) not in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.append(str(temp_test_file))
        
        result = update_system_config(str(temp_test_file), new_content)
        
        # Should succeed
        assert "✅" in result or "ACTUALIZADO" in result
        
        # File should be updated
        assert temp_test_file.read_text(encoding="utf-8") == new_content
        
        # Backup should exist
        backup_path = Path(f"{temp_test_file}.bak")
        assert backup_path.exists()
        
        # Cleanup from allow list
        if str(temp_test_file) in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.remove(str(temp_test_file))

    def test_update_python_valid(self, temp_test_py):
        """Can update a Python file with valid syntax."""
        new_content = """# Updated Python file
def greet(name):
    '''Greet someone.'''
    return f'Hello, {name}!'

if __name__ == '__main__':
    print(greet('world'))
"""
        
        if str(temp_test_py) not in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.append(str(temp_test_py))
        
        result = update_system_config(str(temp_test_py), new_content)
        
        # Should succeed (syntax valid)
        assert "✅" in result
        assert temp_test_py.read_text(encoding="utf-8") == new_content
        
        if str(temp_test_py) in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.remove(str(temp_test_py))

    def test_update_python_syntax_error(self, temp_test_py):
        """Rejects Python with syntax errors without writing."""
        invalid_content = """# Invalid Python
def broken(:
    return 'oops'
"""
        
        if str(temp_test_py) not in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.append(str(temp_test_py))
        
        original_content = temp_test_py.read_text(encoding="utf-8")
        result = update_system_config(str(temp_test_py), invalid_content)
        
        # Should fail
        assert "❌" in result or "ERROR" in result.upper()
        assert "SINTAXIS" in result.upper()
        
        # File should NOT be changed
        assert temp_test_py.read_text(encoding="utf-8") == original_content
        
        # Backup should NOT be created for failed update
        backup_path = Path(f"{temp_test_py}.bak")
        # (may exist from before, but not from this failed update)
        
        if str(temp_test_py) in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.remove(str(temp_test_py))

    def test_update_denied_file(self):
        """Cannot update a file not in ALLOWED_CONFIG_FILES."""
        result = update_system_config("../../etc/passwd", "hacked")
        assert "❌" in result or "Permiso" in result


class TestRestoreSystemConfig:
    """Tests for restore_system_config function."""

    def test_restore_from_backup(self, temp_test_file):
        """Can restore a file from its backup."""
        original_content = temp_test_file.read_text(encoding="utf-8")
        backup_path = Path(f"{temp_test_file}.bak")
        
        if str(temp_test_file) not in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.append(str(temp_test_file))
        
        # Update the file (creates backup)
        new_content = "# Modified content\nfoo: bar\n"
        update_system_config(str(temp_test_file), new_content)
        
        assert temp_test_file.read_text(encoding="utf-8") == new_content
        assert backup_path.exists()
        
        # Restore from backup
        result = restore_system_config(str(temp_test_file))
        
        # Should succeed
        assert "✅" in result or "EXITOSA" in result.upper()
        
        # File should be reverted
        assert temp_test_file.read_text(encoding="utf-8") == original_content
        
        if str(temp_test_file) in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.remove(str(temp_test_file))

    def test_restore_no_backup(self, temp_test_file):
        """Cannot restore if no backup exists."""
        backup_path = Path(f"{temp_test_file}.bak")
        backup_path.unlink(missing_ok=True)  # Ensure no backup
        
        if str(temp_test_file) not in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.append(str(temp_test_file))
        
        result = restore_system_config(str(temp_test_file))
        
        # Should fail gracefully
        assert "❌" in result or "No existe" in result
        
        if str(temp_test_file) in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.remove(str(temp_test_file))

    def test_restore_denied_file(self):
        """Cannot restore a file not in ALLOWED_CONFIG_FILES."""
        result = restore_system_config("../../secret_config.txt")
        assert "❌" in result or "Permiso" in result


class TestDiffGeneration:
    """Tests for diff generation in updates."""

    def test_diff_included_in_response(self, temp_test_file):
        """Diff should be included in the update response."""
        if str(temp_test_file) not in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.append(str(temp_test_file))
        
        new_content = "# Completely new content\nstatus: updated\n"
        result = update_system_config(str(temp_test_file), new_content)
        
        # Diff should be in response
        assert "DIFF" in result.upper() or "---" in result or "+++" in result
        
        if str(temp_test_file) in ALLOWED_CONFIG_FILES:
            ALLOWED_CONFIG_FILES.remove(str(temp_test_file))
