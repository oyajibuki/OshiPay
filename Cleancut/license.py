import secrets
import string
from datetime import datetime, date

from database import get_db

FREE_DAILY_LIMIT = 3


def generate_license() -> str:
    """Generate a license key in CC-XXXX-XXXX-XXXX-XXXX format."""
    chars = string.ascii_uppercase + string.digits
    segments = [
        "".join(secrets.choice(chars) for _ in range(4))
        for _ in range(4)
    ]
    return f"CC-{'-'.join(segments)}"


def create_license(email: str) -> str:
    """Create a new license key and store it in DB."""
    key = generate_license()
    conn = get_db()
    conn.execute(
        "INSERT INTO licenses (license_key, email) VALUES (?, ?)",
        (key, email)
    )
    conn.commit()
    conn.close()
    return key


def verify_license(license_key: str) -> bool:
    """Check if a license key is valid and active."""
    # 1. Quick check against local DB (exists during active container run)
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM licenses WHERE license_key = ? AND is_active = 1",
        (license_key,)
    ).fetchone()
    conn.close()

    if row is not None:
        # Check expiry if set
        if row["expires_at"]:
            expires = datetime.fromisoformat(row["expires_at"])
            if datetime.utcnow() > expires:
                return False
        return True

    # 2. If not in local DB (e.g. Hugging Face container restarted and lost DB)
    # Ping Stripe to verify if this client_reference_id exists and was paid.
    import os
    import stripe
    import urllib.request
    import json
    
    stripe.api_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    
    if stripe.api_key:
        try:
            # Checkout sessions don't support the .search() API. We must page through recent sessions.
            # Using auto_paging_iter() checks sessions until it finds the matching client_reference_id
            for session in stripe.checkout.Session.list(limit=100).auto_paging_iter():
                if session.client_reference_id == license_key:
                    if session.payment_status == "paid":
                        # Restore the license to local DB for faster future lookups
                        email = session.customer_details.email if session.customer_details else "recovered@example.com"
                        try:
                            conn = get_db()
                            conn.execute("INSERT OR IGNORE INTO licenses (license_key, email) VALUES (?, ?)", (license_key, email))
                            conn.commit()
                            conn.close()
                        except Exception as db_err:
                            print(f"[ClearCut] Failed to restore recovered license to DB: {db_err}")
                        return True
                    else:
                        break # Found it, but not paid
        except Exception as e:
            print(f"[ClearCut] Error recovering license from Stripe: {e}")

    # 3. If still not found, check Google Sheets via GAS Webhook
    gas_url = os.getenv("GAS_WEBHOOK_URL", "").strip()
    if gas_url:
        try:
            # Perform GET request to GAS URL with license_key parameter
            req_url = f"{gas_url}?license_key={urllib.parse.quote(license_key)}"
            with urllib.request.urlopen(req_url) as response:
                result = json.loads(response.read().decode("utf-8"))
                if result.get("status") == "success" and result.get("valid") is True:
                    # Valid key found in Spreadsheet, restore to local DB
                    email = result.get("email", "spreadsheet_recovered@example.com")
                    try:
                        conn = get_db()
                        conn.execute("INSERT OR IGNORE INTO licenses (license_key, email) VALUES (?, ?)", (license_key, email))
                        conn.commit()
                        conn.close()
                    except Exception as db_err:
                        print(f"[ClearCut] Failed to restore spreadsheet license to DB: {db_err}")
                    print(f"[ClearCut] Recovered license from Spreadsheet: {license_key}")
                    return True
        except Exception as e:
            print(f"[ClearCut] Error checking license against GAS Webhook: {e}")

    return False


def get_today_usage(ip_address: str) -> int:
    """Get how many times this IP has used the service today."""
    conn = get_db()
    today_str = date.today().isoformat()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM usage_log WHERE ip_address = ? AND DATE(used_at) = ?",
        (ip_address, today_str)
    ).fetchone()
    conn.close()
    return row["cnt"] if row else 0


def record_usage(ip_address: str):
    """Record a usage event for this IP."""
    conn = get_db()
    conn.execute(
        "INSERT INTO usage_log (ip_address) VALUES (?)",
        (ip_address,)
    )
    conn.commit()
    conn.close()


def can_use(ip_address: str, license_key: str = None) -> dict:
    """
    Check if user can use the service.
    Returns: {"allowed": bool, "is_pro": bool, "used": int, "limit": int}
    """
    # Pro user
    if license_key and verify_license(license_key):
        return {"allowed": True, "is_pro": True, "used": 0, "limit": -1}

    # Free user
    used = get_today_usage(ip_address)
    return {
        "allowed": used < FREE_DAILY_LIMIT,
        "is_pro": False,
        "used": used,
        "limit": FREE_DAILY_LIMIT,
    }
