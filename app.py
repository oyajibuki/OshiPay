import os
import io
import base64
import uuid

from flask import Flask, render_template, request, jsonify, redirect, url_for
import stripe
import qrcode

app = Flask(__name__)

# Stripe設定（環境変数から取得）
stripe.api_key = os.environ.get("STRIPE_SECRET_KEY", "sk_test_xxxxx")

# プリセット金額
PRESET_AMOUNTS = [100, 500, 1000, 10000, 30000]


def generate_qr_base64(data: str) -> str:
    """QRコードを生成しBase64文字列で返す"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2,
    )
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#6c2bd9", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


# ──────────────────────────────────────────────
# ページ ルート
# ──────────────────────────────────────────────

@app.route("/")
def index():
    """ランディング → ダッシュボードへ"""
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    """QRコード発行画面"""
    return render_template("dashboard.html")


@app.route("/support/<user_id>")
def support(user_id):
    """応援画面（QR読み取り後に表示）"""
    display_name = request.args.get("name", user_id)
    return render_template(
        "support.html",
        user_id=user_id,
        display_name=display_name,
        preset_amounts=PRESET_AMOUNTS,
    )


@app.route("/success")
def success():
    """決済成功画面"""
    return render_template("success.html")


@app.route("/cancel")
def cancel():
    """決済キャンセル画面"""
    return render_template("cancel.html")


# ──────────────────────────────────────────────
# API エンドポイント
# ──────────────────────────────────────────────

@app.route("/api/generate-qr", methods=["POST"])
def api_generate_qr():
    """QRコード生成API"""
    data = request.get_json()
    display_name = data.get("name", "サポーター")
    user_id = data.get("user_id") or str(uuid.uuid4())[:8]

    # 応援ページのURLを生成
    base_url = request.host_url.rstrip("/")
    support_url = f"{base_url}/support/{user_id}?name={display_name}"

    qr_base64 = generate_qr_base64(support_url)

    return jsonify({
        "qr_image": qr_base64,
        "support_url": support_url,
        "user_id": user_id,
    })


@app.route("/api/create-checkout", methods=["POST"])
def api_create_checkout():
    """Stripe Checkout Session 作成"""
    data = request.get_json()
    amount = int(data.get("amount", 100))
    user_id = data.get("user_id", "unknown")
    display_name = data.get("display_name", "応援")

    if amount < 100:
        return jsonify({"error": "最低金額は100円です"}), 400

    base_url = request.host_url.rstrip("/")

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "jpy",
                    "product_data": {
                        "name": f"🔥 {display_name} への応援",
                        "description": f"OshiPay - {amount:,}円の応援",
                    },
                    "unit_amount": amount,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=f"{base_url}/success?amount={amount}",
            cancel_url=f"{base_url}/cancel",
            metadata={
                "user_id": user_id,
                "display_name": display_name,
            },
        )
        return jsonify({"checkout_url": session.url})
    except stripe.error.StripeError as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(debug=True, port=5000)