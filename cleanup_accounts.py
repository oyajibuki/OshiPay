import stripe
import toml
import os

def get_stripe_key():
    try:
        with open(".streamlit/secrets.toml", "r") as f:
            config = toml.load(f)
            return config.get("STRIPE_SECRET")
    except Exception:
        return os.environ.get("STRIPE_SECRET")

def list_accounts():
    key = get_stripe_key()
    if not key:
        print("Error: Stripe API Key not found.")
        return
    
    stripe.api_key = key
    print(f"Stripe API Key (last 4): ...{key[-4:]}")
    
    try:
        accounts = stripe.Account.list(limit=100)
        print("\n--- Connected Accounts ---")
        for a in accounts.data:
            name = a.settings.dashboard.display_name if a.settings.dashboard else "N/A"
            status = "Enabled" if a.charges_enabled else "Restricted"
            print(f"ID: {a.id} | Name: {name} | Status: {status}")
        print("--------------------------\n")
        return accounts.data
    except Exception as e:
        print(f"Error listing accounts: {e}")
        return []

def delete_account(account_id):
    key = get_stripe_key()
    stripe.api_key = key
    try:
        stripe.Account.delete(account_id)
        print(f"✅ Deleted: {account_id}")
    except Exception as e:
        print(f"❌ Failed to delete {account_id}: {e}")

if __name__ == "__main__":
    list_accounts()
    print("To delete an account, run this script with the account ID as an argument, or use the delete_account function.")
