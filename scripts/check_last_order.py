import asyncio
from dotenv import load_dotenv
from integrations.supabase_client import get_supabase
import structlog

log = structlog.get_logger()

async def check_orders():
    load_dotenv()
    try:
        supabase = get_supabase()
        
        print("--- Consultando ultimos pedidos en Supabase ---")
        
        try:
            response = supabase.table("ORDERS").select("*").order("Timestamp", desc=True).limit(5).execute()
        except Exception:
            response = supabase.table("ORDERS").select("*").limit(5).execute()
            
        if response.data:
            print(f"OK: Se encontraron {len(response.data)} pedido(s) reciente(s):")
            for i, order in enumerate(response.data, 1):
                print(f"\n[Pedido #{i}]")
                print(f"   Cliente: {order.get('Nombres')} {order.get('Apellidos')}")
                print(f"   Producto: {order.get('Producto')}")
                print(f"   WhatsApp: {order.get('Whatsapp')}")
                print(f"   Ciudad: {order.get('Ciudad')}")
                print(f"   Valor: {order.get('Valor a Pagar')}")
                print(f"   Fecha: {order.get('Timestamp')}")
                print("-" * 30)
        else:
            print("INFO: No se encontraron pedidos en la tabla ORDERS.")
            
    except Exception as e:
        print(f"ERROR: Al consultar Supabase: {e}")

if __name__ == "__main__":
    asyncio.run(check_orders())
