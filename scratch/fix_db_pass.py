import asyncio
import asyncpg
import sys

async def main():
    # Try to connect as postgres user to change 'poly' password
    # Common dev setup: no password for local postgres user
    try:
        conn = await asyncpg.connect(user='postgres', host='localhost')
        await conn.execute("ALTER USER poly WITH PASSWORD 'poly_pass';")
        await conn.close()
        print("SUCCESS: Password for user 'poly' changed to 'poly_pass'")
    except Exception as e:
        print(f"FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
