import sqlite3

def check_license(key):
    try:
        conn = sqlite3.connect('clearcut.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM licenses WHERE license_key = ?", (key,))
        row = cursor.fetchone()
        if row:
            print("Found License:")
            for k in row.keys():
                print(f"{k}: {row[k]}")
        else:
            print("License not found in local DB.")
        conn.close()
    except Exception as e:
        print("Error:", e)

check_license('CC-H55N-WNQ5-BNOO-0J7M')
