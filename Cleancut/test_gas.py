import urllib.request
import json
import os
import sys

# URL you provided
GAS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbzmBWscXUWg2OgvDKwe8jZE84mYh93ufXMJp368MRcex8I7-R3qRiAbbeii_ARUQg5e2A/exec"

def test_gas_webhook():
    test_email = "test-customer@example.com"
    test_key = "CC-TEST-1234-ABCD-5678"
    
    print(f"Sending test data to GAS Webhook...")
    print(f"URL: {GAS_WEBHOOK_URL}")
    print(f"Email: {test_email}")
    print(f"License Key: {test_key}")
    print("-" * 40)
    
    try:
        data = json.dumps({
            "email": test_email,
            "license_key": test_key
        }).encode("utf-8")
        
        req = urllib.request.Request(
            GAS_WEBHOOK_URL, 
            data=data, 
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        
        with urllib.request.urlopen(req) as response:
            result = response.read().decode("utf-8")
            print(f"Success! Response from GAS:")
            print(result)
            
    except urllib.error.URLError as e:
        print(f"Failed to connect to GAS: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    test_gas_webhook()
