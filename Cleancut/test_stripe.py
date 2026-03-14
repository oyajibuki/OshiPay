import os
import stripe
from dotenv import load_dotenv

load_dotenv('.env')

stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()

print("Using Stripe Key:", stripe.api_key[:10] if stripe.api_key else "None")

try:
    print("Testing Stripe Search...")
    sessions = stripe.checkout.Session.search(
        query="client_reference_id:'CC-H55N-WNQ5-BNOO-0J7M'",
        limit=1
    )
    print("Search Result:", sessions)
    for s in sessions.data:
        print("Session ID:", s.id, "Payment Status:", s.payment_status)
except Exception as e:
    print("Stripe Search Error:", type(e), e)
