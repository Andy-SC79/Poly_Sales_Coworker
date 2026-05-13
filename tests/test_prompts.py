"""
tests/test_prompts.py
----------------------
Tests for the prompt system — no API key needed.
Validates that personality.yaml loads correctly and prompts build without errors.
Run with: python -m pytest tests/test_prompts.py -v
"""
import pytest
from langchain_core.prompts import ChatPromptTemplate
from core.brain.prompts import get_prompt, _load_personality, STAGE_INSTRUCTIONS


class TestPersonalityConfig:
    def test_yaml_loads_without_error(self):
        cfg = _load_personality()
        assert isinstance(cfg, dict)

    def test_required_sections_present(self):
        cfg = _load_personality()
        assert "agent" in cfg
        assert "soul" in cfg
        assert "communication" in cfg
        assert "sales_flow" in cfg

    def test_agent_name_set(self):
        cfg = _load_personality()
        assert cfg["agent"]["name"] == "Poly"

    def test_core_traits_is_list(self):
        cfg = _load_personality()
        assert isinstance(cfg["soul"]["core_traits"], list)
        assert len(cfg["soul"]["core_traits"]) > 0


class TestPromptBuilder:
    @pytest.mark.parametrize("stage", [
        "greeting", "discovery", "presentation",
        "objection", "closing", "post_sale", "complaint", "admin"
    ])
    def test_all_stages_build_prompt(self, stage: str):
        """Every stage must produce a valid ChatPromptTemplate."""
        prompt = get_prompt(stage)
        assert isinstance(prompt, ChatPromptTemplate)

    def test_prompt_contains_agent_name(self):
        prompt = get_prompt("greeting")
        # Serialize to check content
        messages = prompt.messages
        system_text = str(messages[0])
        assert "Poly" in system_text

    def test_all_stages_have_instructions(self):
        """Every defined stage must have a non-empty instruction block."""
        for stage, instructions in STAGE_INSTRUCTIONS.items():
            assert instructions.strip(), f"Stage '{stage}' has empty instructions"
