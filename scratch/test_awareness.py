from core.brain.awareness import get_context_awareness
from datetime import datetime, timedelta, timezone

def test_awareness():
    print("--- Test 1: Colombia, sin interacción previa ---")
    print(get_context_awareness("+573001234567"))
    
    print("\n--- Test 2: España, hace 2 horas ---")
    last = datetime.now(timezone.utc) - timedelta(hours=2)
    print(get_context_awareness("+34600000000", last_interaction_at=last))

    print("\n--- Test 3: México, hace 3 días ---")
    last_long = datetime.now(timezone.utc) - timedelta(days=3)
    print(get_context_awareness("+521234567890", last_interaction_at=last_long))

if __name__ == "__main__":
    test_awareness()
