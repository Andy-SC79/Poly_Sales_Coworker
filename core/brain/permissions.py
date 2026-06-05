"""
core/brain/permissions.py
--------------------------
Role-based access control (RBAC) for database operations.
Validates user permissions before allowing queries and mutations.
"""

import structlog
from enum import Enum
from typing import Optional

log = structlog.get_logger()


class UserRole(Enum):
    """Available user roles."""
    ADMIN = "admin"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


def get_user_role(user_id: Optional[str]) -> UserRole:
    """
    Determine the role of a user.
    Admin: starts with 'admin_' prefix.
    Customer: regular phone number format (digits, +, hyphens) or chat ID.
    """
    if not user_id:
        return UserRole.UNKNOWN
    
    user_str = str(user_id).lower().strip()
    
    if user_str.startswith("admin_"):
        return UserRole.ADMIN
    
    # Check if it looks like a phone number or regular identifier
    # Phone numbers can have +, digits, hyphens, spaces
    if user_str and any(c.isdigit() for c in user_str):
        # Check if it's primarily numeric (phone-like) or chat ID-like
        digit_version = user_str.replace("+", "").replace("-", "").replace(" ", "")
        if digit_version.isdigit():
            return UserRole.CUSTOMER
    
    if "@" in user_str:  # Email-like
        return UserRole.CUSTOMER
    
    return UserRole.UNKNOWN


def can_execute_sql(user_role: UserRole, table_name: str, action: str) -> bool:
    """
    Check if a user can execute a SQL action on a table.
    
    Admin: Can read/insert/update/delete on any table.
    Customer: Can only read/update ORDERS table for their own phone number.
    """
    if user_role == UserRole.ADMIN:
        return action.upper() in {"SELECT", "INSERT", "UPDATE", "DELETE"}
    
    if user_role == UserRole.CUSTOMER:
        if table_name.upper() != "ORDERS":
            return False
        return action.upper() in {"SELECT", "UPDATE"}
    
    return False


def validate_customer_order_access(
    customer_phone: str, order_id: Optional[str], tracking_number: Optional[str]
) -> dict:
    """
    Validate a customer's access to an order.
    
    Rules:
    1. If no order_id and no tracking_number: attempt to use last order for the phone.
    2. If order_id or tracking_number provided: validate with exact match.
    3. If phone differs: reject unless order_id/tracking_number is provided AND validated.
    
    Returns:
        {
            "allowed": bool,
            "reason": str,
            "order_id": Optional[str],  # The allowed order ID if granted
        }
    """
    if not customer_phone or not str(customer_phone).strip():
        return {"allowed": False, "reason": "No phone number provided"}
    
    # If both identifiers missing, will attempt last order lookup (handler's job)
    if not order_id and not tracking_number:
        return {
            "allowed": True,
            "reason": "Will use customer's last order",
            "order_id": None,
        }
    
    # If identifiers provided, validation must match exactly
    # (actual DB comparison will be done in query builder)
    if order_id or tracking_number:
        return {
            "allowed": True,
            "reason": "Order identifiers provided; will validate against DB",
            "order_id": order_id,
        }
    
    return {"allowed": False, "reason": "Invalid access attempt"}


def build_customer_order_filter(customer_phone: str, order_id: Optional[str] = None) -> str:
    """
    Build a SQL WHERE clause for customer order access.
    
    Returns a SQL fragment that filters ORDERS to only those belonging to the customer.
    """
    customer_phone_sql = customer_phone.replace("'", "''")  # Escape quotes
    
    if order_id:
        order_id_sql = str(order_id).replace("'", "''")
        # Exact match on Order ID
        return f"\"Whatsapp\" = '{customer_phone_sql}' AND \"Order ID\" = '{order_id_sql}'"
    
    # Default: return orders for this phone
    return f"\"Whatsapp\" = '{customer_phone_sql}'"


# Permissions matrix (for documentation/reference)
PERMISSIONS_MATRIX = {
    "admin": {
        "ORDERS": ["SELECT", "INSERT", "UPDATE", "DELETE"],
        "catalog": ["SELECT", "INSERT", "UPDATE", "DELETE"],
        "customers": ["SELECT", "INSERT", "UPDATE", "DELETE"],
        "episodic_memories": ["SELECT", "INSERT", "UPDATE", "DELETE"],
        "*": ["SELECT", "INSERT", "UPDATE", "DELETE"],  # Access to any table
    },
    "customer": {
        "ORDERS": ["SELECT", "UPDATE"],  # Only own orders
        "catalog": ["SELECT"],  # View products only
        "customers": [],  # No access
        "episodic_memories": [],  # No access
    },
}
