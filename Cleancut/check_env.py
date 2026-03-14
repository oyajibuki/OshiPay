import os
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("dotenv: OK")
except ImportError:
    print("dotenv: NOT INSTALLED")

sk = os.getenv("STRIPE_SECRET_KEY", "")
price = os.getenv("STRIPE_PRICE_ID", "")
print("SK:", sk[:15] + "..." if sk else "EMPTY")
print("PRICE:", price if price else "EMPTY")
