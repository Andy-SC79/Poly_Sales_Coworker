"""
scripts/index_catalog.py
-------------------------
Loads products from config/products.yaml and indexes them into Qdrant.
Run this script whenever you update the product catalog.
"""
import asyncio
import yaml
import structlog
from pathlib import Path
from langchain_core.documents import Document

from core.knowledge.catalog import index_documents

log = structlog.get_logger()

async def main():
    catalog_path = Path("config/catalog.yaml")
    if not catalog_path.exists():
        log.error("catalog.not_found", path=str(catalog_path))
        return

    log.info("catalog.loading", path=str(catalog_path))
    
    with open(catalog_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    # Soporta tanto 'products' como 'items' para servicios
    items = data.get("products") or data.get("items") or []
    documents = []
    
    for p in items:
        # Extraer ofertas o precios
        price_info = p.get("base_price", "N/A")
        
        # Create a rich text representation for the vector search
        content = f"""
Item: {p.get('name', 'Sin nombre')}
ID: {p.get('id', 'N/A')}
Precio/Costo: {price_info}
Descripción: {p.get('description', 'Sin descripción')}
Beneficios: {', '.join(p.get('benefits', [])) if isinstance(p.get('benefits'), list) else p.get('benefits', 'N/A')}
Detalles adicionales: {p.get('dosage', p.get('coverage', 'N/A'))}
Disponibilidad: {p.get('city_availability', 'Nacional')}
"""
        doc = Document(
            page_content=content.strip(),
            metadata={
                "id": p.get("id", "N/A"),
                "name": p.get("name", "Sin nombre"),
                "type": "item"
            }
        )
        documents.append(doc)

    log.info("catalog.indexing", count=len(documents))
    
    # 1. Clear existing collection to avoid duplicates
    from integrations.supabase_client import get_supabase
    client = get_supabase()
    try:
        # Supabase API does not support truncate via REST easily without a filter,
        # so we delete where id is not null (which deletes all rows)
        client.table("catalog").delete().neq("id", "00000000-0000-0000-0000-000000000000").execute()
        log.info("catalog.cleared", name="catalog")
    except Exception as e:
        log.info("catalog.clear_failed", error=str(e))

    # 2. Re-index all documents
    await index_documents(documents)
    log.info("catalog.success")

if __name__ == "__main__":
    asyncio.run(main())
