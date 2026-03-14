import os
import stripe
from dotenv import load_dotenv

load_dotenv('.env')

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

def test_recovery(license_key):
    print(f"Scanning Stripe for {license_key}...")
    try:
        found = False
        sessions = stripe.checkout.Session.list(limit=100)
        for session in sessions.auto_paging_iter():
            if session.client_reference_id == license_key:
                print(f"MATCH FOUND! Session ID: {session.id}, status: {session.payment_status}")
                found = True
                break
        if not found:
            print("Not found in Stripe sessions.")
    except Exception as e:
        print(f"Error: {e}")

test_recovery('CC-H55N-WNQ5-BNOO-0J7M')
