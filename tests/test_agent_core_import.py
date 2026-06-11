def test_agent_core_package_import():
    from agent_core.core.engine import AgentCoreEngine, EngineConfig

    engine = AgentCoreEngine(config=EngineConfig(
        prompt_provider=None,
        tool_provider=None,
        memory_provider=None,
        rbac_provider=None,
    ))
    assert engine is not None
    assert engine.config is not None
