import sys
import io

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

from license import create_license

def generate_free_key(email="free-user@example.com"):
    # create_license は内部で新しいキーを生成し、データベースに登録します
    new_key = create_license(email)
    print("=========================================")
    print("🆓 無料ライセンスキーを発行しました 🆓")
    print(f"メールアドレス: {email}")
    print(f"ライセンスキー: {new_key}")
    print("=========================================")
    print("※このキーはStripe決済を経由していませんが、即座に「ClearCut」上で制限解除に使えます。")

if __name__ == "__main__":
    email = sys.argv[1] if len(sys.argv) > 1 else "free-user@example.com"
    generate_free_key(email)
