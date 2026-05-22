import pytest
from langchain_core.prompts import ChatPromptTemplate

from core.brain.prompts import STAGE_INSTRUCTIONS, _load_config, get_prompt


class TestPromptConfig:
    def test_yaml_loads_without_error(self):
        cfg = _load_config()
        assert isinstance(cfg, dict)

    def test_required_sections_present(self):
        cfg = _load_config()
        assert "personality" in cfg
        assert "business" in cfg
        assert "identity" in cfg["personality"]
        assert "moral_principles" in cfg["personality"]
        assert "employment_contract" in cfg["personality"]

    def test_agent_name_set(self):
        cfg = _load_config()
        assert cfg["personality"]["identity"]["name"] == "Poly"


class TestPromptBuilder:
    @pytest.mark.parametrize("stage", [
        "greeting", "discovery", "presentation",
        "objection", "closing", "post_sale", "complaint", "admin",
    ])
    def test_all_stages_build_prompt(self, stage: str):
        prompt = get_prompt(stage)
        assert isinstance(prompt, ChatPromptTemplate)

    def test_prompt_contains_agent_name(self):
        prompt = get_prompt("greeting")
        system_text = str(prompt.messages[0])
        assert "Poly" in system_text

    def test_prompt_does_not_ask_model_to_fill_caller_whatsapp(self):
        prompt = get_prompt("post_sale", whatsapp_origin="+573001234567")
        system_text = str(prompt.messages[0])
        assert "caller_whatsapp" not in system_text

    def test_all_stages_have_instructions(self):
        for stage, instructions in STAGE_INSTRUCTIONS.items():
            assert instructions.strip(), f"Stage '{stage}' has empty instructions"
