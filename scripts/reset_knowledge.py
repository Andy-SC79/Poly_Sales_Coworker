
import asyncio
import structlog
from qdrant_client import QdrantClient
from config.settings import get_settings

log = structlog.get_logger()

async def reset_catalog():
    settings = get_settings()
    client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
    
    collection_name = settings.qdrant_collection_name
    print(f"WARNING: About to delete collection '{collection_name}'")
    
    try:
        # Check if exists
        existing = client.get_collections()
        names = [c.name for c in existing.collections]
        
        if collection_name in names:
            client.delete_collection(collection_name)
            print(f"DONE: Collection '{collection_name}' deleted.")
        else:
            print(f"INFO: Collection '{collection_name}' does not exist.")
            
        # Recreate empty with correct dimensions
        from qdrant_client.models import Distance, VectorParams
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
        )
        print(f"DONE: Collection '{collection_name}' recreated (empty).")
        
    except Exception as e:
        print(f"ERROR: During reset: {e}")

if __name__ == "__main__":
    asyncio.run(reset_catalog())
