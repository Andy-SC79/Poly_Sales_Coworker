import asyncio
from sqlalchemy import text
from core.memory.database import engine

async def migrate():
    print("🚀 Iniciando migración de base de datos...")
    async with engine.begin() as conn:
        try:
            # Añadir columna 'role'
            await conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'customer'"))
            # Añadir columna 'role_metadata'
            await conn.execute(text("ALTER TABLE customers ADD COLUMN IF NOT EXISTS role_metadata JSON DEFAULT '{}'"))
            print("✅ Columnas 'role' y 'role_metadata' añadidas correctamente.")
        except Exception as e:
            print(f"❌ Error durante la migración: {e}")

if __name__ == "__main__":
    asyncio.run(migrate())
