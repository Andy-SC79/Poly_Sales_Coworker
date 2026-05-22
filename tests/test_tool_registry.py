from core.brain.model_selector import get_admin_tools, get_customer_tools


def _tool_schema_props(tool):
    return set(tool.tool_call_schema.model_json_schema().get("properties", {}))


def test_customer_tools_do_not_expose_injected_identity_or_state():
    critical = {
        "submit_order_to_supabase",
        "cancelar_pedido",
        "add_order_note",
        "escalar_consulta_humana",
        "check_order_status",
    }

    for tool in get_customer_tools():
        if tool.name in critical:
            props = _tool_schema_props(tool)
            assert "state" not in props
            assert "caller_whatsapp" not in props
            assert "caller_whatsapp" not in tool.description


def test_admin_registry_includes_customer_tools_and_admin_tools():
    customer_names = {tool.name for tool in get_customer_tools()}
    admin_names = {tool.name for tool in get_admin_tools()}

    assert customer_names.issubset(admin_names)
    assert "query_business_intelligence" in admin_names
    assert "update_system_config" in admin_names
