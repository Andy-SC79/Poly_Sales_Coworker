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


async def chat_loop(phone: str, is_admin: bool):
    channel = "telegram" if is_admin else "whatsapp"
    role_label = "ADMIN (Telegram)" if is_admin else f"Cliente WhatsApp [{phone}]"

    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  🤖 Poly AI Coworker — Terminal Chat{RESET}")
    print(f"{GRAY}  Modo: {role_label}{RESET}")
    print(f"{GRAY}  Escribe 'salir' para terminar{RESET}")
    print(f"{BOLD}{'='*55}{RESET}\n")

    config = {"configurable": {"thread_id": phone}}

    while True:
        try:
            user_input = input(f"{GREEN}Tú:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GRAY}Sesión terminada.{RESET}")
            break

        if not user_input or user_input.lower() in ("salir", "exit", "quit"):
            print(f"\n{GRAY}Hasta luego!{RESET}\n")
            break

        state = {
            "messages": [HumanMessage(content=user_input)],
            "channel": channel,
            "customer_id": phone,
            "stage": "greeting",
            "customer_name": None,
            "pain_points": [],
            "recommended_products": [],
            "order_data": None,
            "is_admin": is_admin,
            "escalation_pending": False,
            "long_term_profile": None,
        }

        print(f"{GRAY}  [pensando...]{RESET}", end="\r")
        try:
            result = await poly_graph.ainvoke(state, config=config)
            reply = result["messages"][-1].content
            stage = result.get("stage", "?")
            print(f"{CYAN}Poly:{RESET} {reply}")
            print(f"{GRAY}  [etapa detectada: {stage}]{RESET}\n")
        except Exception as e:
            print(f"\n{YELLOW}  ⚠ Error: {e}{RESET}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Chat interactivo con Poly")
    parser.add_argument("--admin", action="store_true", help="Modo administrador (Telegram)")
    parser.add_argument("--phone", default="+573001234567", help="Número de teléfono simulado")
    args = parser.parse_args()
    asyncio.run(chat_loop(args.phone, args.admin))
