#!/bin/bash
# OshiPay2 → OshiPay 移行スクリプト
# 使用方法: bash migrate_from_oshipay2.sh
# ロールバック: bash migrate_from_oshipay2.sh --rollback

OSHIPAY_DIR="C:/Users/User/Desktop/my-sideprojects/42.OshiPay"
OSHIPAY2_DIR="C:/Users/User/Desktop/my-sideprojects/42.1.OshiPay2"

if [ "$1" == "--rollback" ]; then
    echo "⏪ ロールバック: OshiPay を直前のコミットに戻します..."
    cd "$OSHIPAY_DIR"
    git revert HEAD --no-edit
    git push origin main
    echo "✅ ロールバック完了"
    exit 0
fi

echo "🚀 OshiPay2 → OshiPay 移行開始..."

# 1. app.py をコピー
echo "📋 app.py をコピー中..."
cp "$OSHIPAY2_DIR/app.py" "$OSHIPAY_DIR/app.py"

# 2. requirements.txt 確認（supabase 追加済み）
echo "📦 requirements.txt 確認..."
cat "$OSHIPAY_DIR/requirements.txt"

# 3. APP_URL を oshipay.streamlit.app に変更（secrets.toml はローカルのみ、本番はStreamlit Cloudで設定）
echo ""
echo "⚠️  Streamlit Cloud の OshiPay の Secrets に以下を追加してください:"
echo "   APP_URL = \"https://oshipay.streamlit.app\""
echo "   SUPABASE_URL = \"<OshiPay2と同じ値>\""
echo "   SUPABASE_KEY = \"<OshiPay2と同じ値>\""
echo ""

# 4. git push
echo "📤 OshiPay にプッシュ中..."
cd "$OSHIPAY_DIR"
git add app.py requirements.txt
git commit -m "feat: OshiPay2コードベースに移行（Supabase連携・コインバッジ・ランキング）

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>"
git push origin main

echo ""
echo "✅ 移行完了！"
echo "📌 ロールバックするには: bash migrate_from_oshipay2.sh --rollback"
