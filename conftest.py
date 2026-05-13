"""
conftest.py — Root pytest configuration.
Adds the project root to sys.path so all modules resolve correctly.
"""
import sys
from pathlib import Path

# Ensure the project root is always importable
sys.path.insert(0, str(Path(__file__).parent))
