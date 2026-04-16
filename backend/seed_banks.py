import time
from firebase_config import db

GLOBAL_BANKS = [
    "JPMorgan Chase",
    "Bank of America",
    "Citibank",
    "HSBC"
]

def seed_banks():
    print("Seeding Global Banks...")
    for name in GLOBAL_BANKS:
        doc_id = f"bank_global_{name.replace(' ', '_').lower()}"
        doc_ref = db.collection("banks").document(doc_id)
        if not doc_ref.get().exists:
            doc_ref.set({
                "name": name,
                "is_builtin": True,
                "team_id": "global",
                "created_at": time.time()
            })
            print(f"Added: {name}")
        else:
            print(f"Skipping (exists): {name}")

if __name__ == "__main__":
    seed_banks()
    print("Seeding complete.")
