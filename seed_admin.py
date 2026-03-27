import os
import sys
import time

# Add the current directory to sys.path to resolve imports within the backend folder
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

def seed_admin():
    from backend.firebase_config import auth, db
    
    email = "admin@expense.com"
    password = "AdminPassword123!"
    
    try:
        user = auth.get_user_by_email(email)
        print(f"Admin already exists: {email}")
    except Exception:
        print(f"Creating first admin account...")
        user = auth.create_user(email=email, password=password)
        db.collection("users").document(user.uid).set({
            "uid": user.uid,
            "email": email,
            "role": "admin",
            "team_id": "Global",
            "status": "active",
            "created_at": time.time()
        })
        print("--- SUCCESS ---")
        print(f"Admin Email: {email}")
        print(f"Admin Password: {password}")
        print("Please use these credentials to log into the new Expense Portal.")

if __name__ == "__main__":
    seed_admin()
