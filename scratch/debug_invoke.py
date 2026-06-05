import asyncio
from langchain_core.messages import HumanMessage
from core.brain.agents import _invoke_agent

state = {
    "messages": [HumanMessage(content="Dame un resumen de las ventas de hoy")],
    "channel": "telegram",
    "customer_id": "telegram_admin_123",
    "stage": "admin",
    "customer_name": None,
    "conversation_summary": None,
    "discovery_notes": None,
    "recommended_products": [],
    "order_data": None,
    "is_admin": True,
    "escalation_pending": False,
    "long_term_profile": None,
}

async def main():
    res = await _invoke_agent(state, 'admin')
    print('INVOKE RESULT KEYS:', list(res.keys()))
    msgs = res.get('messages')
    print('MESSAGES LEN', len(msgs) if msgs else 0)
    for i,m in enumerate(msgs or []):
        print(i, type(m), getattr(m,'content', None))

if __name__ == '__main__':
    asyncio.run(main())
