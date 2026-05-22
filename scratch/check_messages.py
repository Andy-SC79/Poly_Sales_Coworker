import asyncio
import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from core.memory.database import get_session
from sqlalchemy import text

async def main():
    try:
        async with get_session() as session:
            query = text("SELECT role, content FROM messages ORDER BY id DESC LIMIT 20")
            result = await session.execute(query)
            print("\n--- HISTORIAL DE MENSAJES ---")
            messages = list(result)
            for role, content in reversed(messages):
                print(f"{role.upper()}: {content}")
            print("-----------------------------\n")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(main())
