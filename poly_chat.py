"""
poly_chat.py
-------------
Interactive CLI to chat with Poly in the terminal.
Useful for manual testing before WhatsApp/Telegram are connected.

Usage:
  python poly_chat.py                    # as customer
  python poly_chat.py --admin            # as admin (Telegram mode)
  python poly_chat.py --phone +573001234 # custom phone number

Requires OPENAI_API_KEY in .env
"""
import asyncio
import argparse
import sys
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage
from core.brain.graph import poly_graph

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"


async def chat_loop(phone: str, is_admin: bool, use_ollama: bool):
    channel = "telegram" if is_admin else "whatsapp"
    role_label = "ADMIN (Telegram)" if is_admin else f"Cliente WhatsApp [{phone}]"
    model_label = "Ollama (local)" if use_ollama else "OpenAI/Gemini (cloud)"

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  🤖 Poly AI Coworker — Terminal Chat{RESET}")
    print(f"{GRAY}  Modo: {role_label} | Modelo: {model_label}{RESET}")
    print(f"{GRAY}  Escribe 'salir' para terminar{RESET}")
    print(f"{BOLD}{'='*55}{RESET}\n")

    # Clean thread_id for fresh session if needed, but here we'll use phone
    config = {"configurable": {"thread_id": f"{phone}_{'ollama' if use_ollama else 'cloud'}"}}

    state = {
        "messages": [],
        "channel": channel,
        "customer_id": phone,
        "stage": "greeting",
        "customer_name": None,
        "conversation_summary": None,
        "discovery_notes": None,
        "recommended_products": [],
        "order_data": None,
        "current_order_id": None,
        "is_admin": is_admin,
        "escalation_pending": False,
        "long_term_profile": None,
        "role": "owner" if is_admin else "customer",
        "last_interaction_at": None,
        "permissions": ["web_search"] if (is_admin or use_ollama) else [], # Ollama users get search for testing
        "model_provider": "ollama" if use_ollama else "default"
    }

    # IMPORTANT: If use_ollama is true, we should tell the graph or model_selector.
    # For now, we'll assume the user has OLLAMA_DEFAULT_MODEL set.
    # We can pass a flag in the config or just rely on model_selector logic if we force 'ollama' task.

    # Load long-term profile from DB
    from core.memory.database import get_session
    from core.memory.customer_repo import CustomerRepo
    try:
        async with get_session() as session:
            repo = CustomerRepo(session)
            profile = await repo.get_profile(phone)
            state["long_term_profile"] = profile
            if profile and profile.get("name"):
                state["customer_name"] = profile["name"]
            if profile and profile.get("conversation_summary"):
                state["conversation_summary"] = profile["conversation_summary"]
    except Exception as db_err:
        print(f"{GRAY}  (DB no disponible: {db_err}){RESET}")

    while True:
        try:
            user_input = input(f"{GREEN}Tú:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GRAY}Sesión terminada.{RESET}")
            break

        if not user_input or user_input.lower() in ("salir", "exit", "quit"):
            print(f"\n{GRAY}Hasta luego!{RESET}\n")
            break

        state["messages"].append(HumanMessage(content=user_input))

        print(f"{GRAY}  [pensando...]{RESET}", end="\r")
        try:
            from core.brain.graph import get_poly_graph
            graph = await get_poly_graph()
            
            result = await graph.ainvoke(state, config=config)
            
            # Update local state for next turn
            state.update({k: v for k, v in result.items() if k != "messages"})
            state["messages"] = result["messages"]
            
            # --- CRM SYNC: Guardar lo aprendido en la base de datos ---
            if not is_admin:
                try:
                    async with get_session() as session:
                        repo = CustomerRepo(session)
                        await repo.update_profile(
                            phone=phone,
                            name=result.get("customer_name"),
                            city=result.get("city"),
                            conversation_summary=result.get("conversation_summary"),
                            email=result.get("email"),
                            address=result.get("address"),
                            alternative_phone=result.get("alternative_phone")
                        )
                        await session.commit()
                except Exception as db_err:
                    print(f"{YELLOW}  ⚠ Error CRM: {db_err}{RESET}")

            # Check for tool calls
            last_ai_msg = state["messages"][-1]
            if hasattr(last_ai_msg, "tool_calls") and last_ai_msg.tool_calls:
                for tc in last_ai_msg.tool_calls:
                    print(f"{YELLOW}  [ACCION: {tc['name']}]{RESET}")
            
            reply = last_ai_msg.content
            stage = state.get("stage", "?")
            if reply:
                print(f"{CYAN}Poly:{RESET} {reply}")
            else:
                print(f"{GRAY}Poly está procesando una acción...{RESET}")
            
            print(f"{GRAY}  [etapa: {stage} | país: {phone[:3]}]{RESET}\n")
            
        except Exception as e:
            print(f"\n{YELLOW}  ⚠ Error: {e}{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat interactivo con Poly")
    parser.add_argument("--admin", action="store_true", help="Modo administrador (Telegram)")
    parser.add_argument("--ollama", action="store_true", help="Usar Ollama en lugar de Cloud")
    parser.add_argument("--phone", default="+573001234567", help="Número de teléfono simulado")
    args = parser.parse_args()
    asyncio.run(chat_loop(args.phone, args.admin, args.ollama))
