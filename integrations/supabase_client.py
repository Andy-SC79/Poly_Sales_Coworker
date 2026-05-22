"""
integrations/supabase_client.py
--------------------------------
Client factory for Supabase integration.
"""
import structlog
from supabase import create_client, Client
from config.settings import get_settings

settings = get_settings()
log = structlog.get_logger()

def get_supabase() -> Client:
    """
    Returns an authenticated Supabase client using service role for admin access.
    """
    if not settings.supabase_orders_url or not settings.supabase_service_role_key:
        log.error("supabase.config_missing")
        raise ValueError("SUPABASE_ORDERS_URL or SUPABASE_SERVICE_ROLE_KEY not configured in .env")

    # The client handles connection pooling/reuse internally if used as a singleton, 
    # but for simple tool calls, we can instantiate it.
    return create_client(settings.supabase_orders_url, settings.supabase_service_role_key)
