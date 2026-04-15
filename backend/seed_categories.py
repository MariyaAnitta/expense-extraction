from firebase_config import db
import time

def seed_categories():
    categories = [
        # Expense categories
        {"name": "Food", "type": "Expense", "is_builtin": True},
        {"name": "Travel", "type": "Expense", "is_builtin": True},
        {"name": "Visa/LMRA", "type": "Expense", "is_builtin": True},
        {"name": "SIO", "type": "Expense", "is_builtin": True},
        {"name": "Municipality/EWA", "type": "Expense", "is_builtin": True},
        {"name": "Internet/Mobile", "type": "Expense", "is_builtin": True},
        {"name": "Amex Payment", "type": "Expense", "is_builtin": True},
        {"name": "Government Fees", "type": "Expense", "is_builtin": True},
        {"name": "Parking", "type": "Expense", "is_builtin": True},
        {"name": "Fuel", "type": "Expense", "is_builtin": True},
        {"name": "Stationery", "type": "Expense", "is_builtin": True},
        {"name": "Other", "type": "Expense", "is_builtin": True},
        
        # Deposit categories
        {"name": "Bank", "type": "Deposit", "is_builtin": True},
        {"name": "Cash", "type": "Deposit", "is_builtin": True},
    ]

    print("Seeding categories...")
    for cat in categories:
        # Use name as document ID to prevent duplicates (fix: remove slashes)
        doc_id = f"{cat['type'].lower()}_{cat['name'].replace(' ', '_').replace('/', '_').lower()}"
        db.collection("categories").document(doc_id).set({
            **cat,
            "created_at": time.time()
        })
        print(f"  - Added {cat['type']}: {cat['name']}")

    print("Success: Initial categories seeded.")

if __name__ == "__main__":
    seed_categories()
