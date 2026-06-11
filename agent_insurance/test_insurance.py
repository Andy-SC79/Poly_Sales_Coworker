"""
agent_insurance/test_insurance.py
Interactive CLI to test the Sura Health prequalification agent locally.
"""
import asyncio
import argparse
from dotenv import load_dotenv

load_dotenv()

from langchain_core.messages import HumanMessage
from agent_insurance.agents import run_insurance_agent

RESET  = "\033[0m"
BOLD   = "\033[1m"
CYAN   = "\033[96m"
GREEN  = "\033[92m"
YELLOW = "\033[93m"
GRAY   = "\033[90m"
MAGENTA = "\033[95m"

def print_state(state: dict):
    print(f"\n{BOLD}{MAGENTA}=== ESTADO ACTUAL DEL CRM ==={RESET}")
    print(f"  {BOLD}Etapa actual:{RESET} {state.get('stage')}")
    print(f"  {BOLD}Persona que llama:{RESET} {state.get('caller_name')}")
    print(f"  {BOLD}¿Es para sí mismo?:{RESET} {state.get('is_for_self')}")
    print(f"  {BOLD}Relación candidato:{RESET} {state.get('candidate_relation')}")
    print(f"  {BOLD}Nombre candidato:{RESET} {state.get('candidate_name')}")
    print(f"  {BOLD}Edad candidato:{RESET} {state.get('candidate_age')}")
    print(f"  {BOLD}¿Tiene EPS?:{RESET} {state.get('candidate_has_eps')}")
    print(f"  {BOLD}Nombre EPS:{RESET} {state.get('candidate_eps')}")
    print(f"  {BOLD}¿Está precalificado?:{RESET} {state.get('is_qualified')}")
    print(f"  {BOLD}Razón precalificación:{RESET} {state.get('qualification_reason')}")
    print(f"  {BOLD}Producto seleccionado:{RESET} {state.get('matched_product')}")
    print(f"  {BOLD}Correo:{RESET} {state.get('email')}")
    print(f"  {BOLD}Teléfono:{RESET} {state.get('phone')}")
    print(f"  {BOLD}Estado cita Calendly:{RESET} {state.get('appointment_status')}")
    print(f"  {BOLD}Fecha cita Calendly:{RESET} {state.get('appointment_date')}")
    print(f"{BOLD}{MAGENTA}=============================={RESET}\n")

async def chat_loop(phone: str):
    print(f"\n{BOLD}{'='*55}{RESET}")
    print(f"{BOLD}  [AGENT] Sura Health Agent — Terminal Chat{RESET}")
    print(f"{GRAY}  Cliente WhatsApp: {phone}{RESET}")
    print(f"{GRAY}  Comandos: /state, /mock-schedule [fecha], /reset, salir{RESET}")
    print(f"{BOLD}{'='*55}{RESET}\n")

    state = {
        "messages": [],
        "channel": "whatsapp",
        "customer_id": phone,
        "stage": "greeting",
        
        # Prequalification attributes
        "is_for_self": None,
        "caller_name": None,
        "candidate_relation": None,
        "candidate_name": None,
        "candidate_age": None,
        "candidate_has_eps": None,
        "candidate_eps": None,
        "is_qualified": None,
        "qualification_reason": None,
        "matched_product": None,
        
        # Contact and appointment attributes
        "email": None,
        "phone": None,
        "appointment_status": "none",
        "appointment_date": None,
        "other_product_interest": None
    }

    # Boot greeting turn automatically
    print(f"{GRAY}[iniciando conversación...]{RESET}")
    state = await run_insurance_agent(state)
    reply = state["messages"][-1].content
    print(f"{CYAN}Mateo:{RESET} {reply}\n")

    while True:
        try:
            user_input = input(f"{GREEN}Tú:{RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{GRAY}Sesión terminada.{RESET}")
            break

        if not user_input:
            continue

        if user_input.lower() in ("salir", "exit", "quit"):
            print(f"\n{GRAY}¡Hasta luego!{RESET}\n")
            break

        # -- Command handler --
        if user_input.startswith("/"):
            parts = user_input.split(" ", 1)
            cmd = parts[0].lower()
            
            if cmd == "/state":
                print_state(state)
                continue
                
            elif cmd == "/reset":
                state.update({
                    "messages": [],
                    "stage": "greeting",
                    "is_for_self": None,
                    "caller_name": None,
                    "candidate_relation": None,
                    "candidate_name": None,
                    "candidate_age": None,
                    "candidate_has_eps": None,
                    "candidate_eps": None,
                    "is_qualified": None,
                    "qualification_reason": None,
                    "matched_product": None,
                    "email": None,
                    "phone": None,
                    "appointment_status": "none",
                    "appointment_date": None,
                    "other_product_interest": None
                })
                print(f"{GRAY}[Estado reiniciado. Iniciando saludo...]{RESET}")
                state = await run_insurance_agent(state)
                reply = state["messages"][-1].content
                print(f"{CYAN}Mateo:{RESET} {reply}\n")
                continue
                
            elif cmd == "/mock-schedule":
                # Simulate webhook confirmation
                date_str = parts[1] if len(parts) > 1 else "2026-06-15 10:00 AM"
                state["appointment_status"] = "scheduled"
                state["appointment_date"] = date_str
                state["stage"] = "completed"
                
                print(f"\n{BOLD}{YELLOW}*** [MOCK WEBHOOK CALENDLY]: Cita confirmada para {date_str} ***{RESET}")
                confirmation_msg = (
                    f"¡Excelente noticia! Hemos confirmado tu cita con tu asesor de Sura "
                    f"para el día {date_str}. Se ha enviado una notificación por correo a {state.get('email', 'tu email')} "
                    f"y por SMS a {state.get('phone', 'tu teléfono')}. ¡Que tengas un excelente día!"
                )
                print(f"{CYAN}Mateo (SMS/Notificación):{RESET} {confirmation_msg}\n")
                continue
            
            else:
                print(f"{YELLOW}Comando desconocido.{RESET}")
                continue

        # Regular message
        state["messages"].append(HumanMessage(content=user_input))
        print(f"{GRAY}  [Mateo está pensando...]{RESET}", end="\r")
        
        try:
            state = await run_insurance_agent(state)
            reply = state["messages"][-1].content
            print(f"{CYAN}Mateo:{RESET} {reply}")
            print(f"{GRAY}  [etapa: {state.get('stage')}]{RESET}\n")
            
        except Exception as e:
            print(f"\n{YELLOW}  [ERROR]: {e}{RESET}\n")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test runner para agente de seguros")
    parser.add_argument("--phone", default="+573115551234", help="Número de teléfono simulado")
    args = parser.parse_args()
    asyncio.run(chat_loop(args.phone))
