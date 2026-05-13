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
    catalog_path = Path("config/products.yaml")
    if not catalog_path.exists():
        log.error("catalog.not_found", path=str(catalog_path))
        return

    log.info("catalog.loading", path=str(catalog_path))
    
    with open(catalog_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    
    products = data.get("products", [])
    documents = []
    
    for p in products:
        # Create a rich text representation for the vector search
        content = f"""
Producto: {p['name']}
ID: {p['id']}
Precio: ${p['price']}
Descripción: {p['description']}
Beneficios: {', '.join(p['benefits'])}
Dosis: {p['dosage']}
Disponibilidad: {p.get('city_availability', 'Nacional')}
"""
        doc = Document(
            page_content=content.strip(),
            metadata={
                "id": p["id"],
                "name": p["name"],
                "price": p["price"],
                "type": "product"
            }
        )
        documents.append(doc)

    log.info("catalog.indexing", count=len(documents))
    
    # 1. Clear existing collection to avoid duplicates and handle updates/deletions
    # This ensures the vector store is a 1:1 reflection of your YAML file.
    from qdrant_client import QdrantClient
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    client.delete_collection(settings.qdrant_collection_name)
    log.info("catalog.cleared", name=settings.qdrant_collection_name)

    # 2. Re-index all documents
    await index_documents(documents)
    log.info("catalog.success")

if __name__ == "__main__":
    asyncio.run(main())
