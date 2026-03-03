import os
import io
import base64
import uuid
import random

import streamlit as st
import streamlit.components.v1 as components
import stripe
import qrcode
import urllib.parse
import smtplib
from email.mime.text import MIMEText
from email.utils import formatdate
from PIL import Image

# ── ページ設定 ──
st.set_page_config(
    page_title="OshiPay — 応援を、もっとシンプルに。",
    page_icon="🔥",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# Stripe設定
try:
    stripe.api_key = st.secrets["STRIPE_SECRET"]
except Exception:
    stripe.api_key = os.environ.get("STRIPE_SECRET", "")

# 定数
PRESET_AMOUNTS = [100, 500, 1000, 5000, 10000, 30000]
PLATFORM_FEE_PERCENT = 10
ICON_OPTIONS = {
    "🎤": "歌手・MC", "🎸": "ギター・バンド", "🎹": "ピアノ・キーボード",
    "🎨": "アーティスト・絵描き", "📷": "カメラマン・写真家", "☕": "カフェ・バリスタ",
    "✂️": "美容師・理容師", "🎮": "ゲーマー・配信者", "📚": "講師・先生",
    "💻": "エンジニア・クリエイター", "🎭": "役者・パフォーマー", "🔥": "その他",
}
BASE_URL = os.environ.get("APP_URL", "https://oshipay.streamlit.app")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ヘルパー関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_connect_account():
    account = stripe.Account.create(
        type="express", country="JP",
        capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
        business_type="individual",
        business_profile={"mcc": "7922", "product_description": "OshiPay - 投げ銭サービス"},
    )
    return account.id

def create_account_link(account_id, return_params=""):
    return_url = f"{BASE_URL}?page=dashboard&acct={account_id}{return_params}"
    refresh_url = f"{BASE_URL}?page=dashboard&acct={account_id}&refresh=1{return_params}"
    link = stripe.AccountLink.create(
        account=account_id, refresh_url=refresh_url, return_url=return_url, type="account_onboarding",
    )
    return link.url

def send_support_email(to_email, creator_name, amount, message):
    try:
        smtp_server = st.secrets.get("SMTP_SERVER"); smtp_port = st.secrets.get("SMTP_PORT", 587)
        smtp_user = st.secrets.get("SMTP_USER"); smtp_pass = st.secrets.get("SMTP_PASS")
        if not all([smtp_server, smtp_user, smtp_pass]): return False, "SMTP設定不足"
        subject = f"🔥 {creator_name}さんに応援が届きました！ (OshiPay)"
        body = f"{creator_name}さん\n\nOshiPayを通じて応援が届きました！\n\n💰 応援金額: {amount:,}円\n💬 メッセージ:\n{message if message else '（なし）'}\n\n--\nOshiPay\n{BASE_URL}"
        msg = MIMEText(body); msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to_email; msg["Date"] = formatdate(localtime=True)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(); server.login(smtp_user, smtp_pass); server.send_message(msg)
        return True, "送信成功"
    except Exception as e: return False, str(e)

def check_account_status(account_id):
    try:
        account = stripe.Account.retrieve(account_id)
        return {"charges_enabled": account.charges_enabled, "details_submitted": account.details_submitted}
    except Exception: return None

def generate_qr_data(data: str) -> tuple[str, bytes]:
    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_H, box_size=10, border=4)
    qr.add_data(data); qr.make(fit=True); qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    logo_path = "assets/oshi_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            qr_w, qr_h = qr_img.size; logo_size = int(qr_w * 0.22); logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            qr_img.paste(logo, ((qr_w-logo_size)//2, (qr_h-logo_size)//2), logo)
        except Exception: pass
    buf = io.BytesIO(); qr_img.save(buf, format="PNG"); qr_bytes = buf.getvalue(); b64 = base64.b64encode(qr_bytes).decode()
    return b64, qr_bytes

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ページスタイル (Streamlit固有)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Noto+Sans+JP:wght@400;700;900&display=swap');
#MainMenu, header, footer, .stDeployButton {visibility: hidden; display: none !important;}
[data-testid="stToolbar"], [data-testid="stDecoration"] {display: none !important;}
.stApp { background: #08080f !important; font-family: 'Inter', 'Noto Sans JP', sans-serif !important; }
.stMainBlockContainer, .block-container { position: relative; z-index: 1; padding-top: 2rem !important; }
.oshi-logo { text-align: center; margin-bottom: 6px; }
.oshi-logo .icon { font-size: 28px; }
.oshi-logo .text { font-size: 22px; font-weight: 800; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.selected-amount-display { text-align: center; font-size: 36px; font-weight: 900; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 10px 0; }
.stButton > button { width: 100%; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316) !important; color: white !important; border: none !important; border-radius: 9999px !important; padding: 16px !important; font-weight: 700 !important; }
.oshi-footer { text-align: center; margin-top: 24px; font-size: 11px; color: rgba(240,240,245,0.35); }
.oshi-footer a { color: #8b5cf6; text-decoration: none; }
.particles-bg { position: fixed; top: 0; left: 0; width: 100%; height: 100%; pointer-events: none; z-index: 0; overflow: hidden; }
.particle { position: absolute; border-radius: 50%; animation: floatParticle linear infinite; opacity: 0.15; }
@keyframes floatParticle { 0% { transform: translateY(100vh); opacity: 0; } 10% { opacity: 0.15; } 90% { opacity: 0.15; } 100% { transform: translateY(-10vh); opacity: 0; } }
.legal-links a { font-size: 10px; color: rgba(240,240,245,0.3); text-decoration: none; margin: 0 5px; }
</style>
""", unsafe_allow_html=True)

# ── パーティクル ──
particles_html = '<div class="particles-bg">'
for _ in range(20):
    size = random.uniform(2, 4); left = random.uniform(0, 100); dur = random.uniform(15, 25); dly = random.uniform(0, 10)
    particles_html += f'<div class="particle" style="width:{size}px;height:{size}px;left:{left}%;background:#8b5cf6;animation-duration:{dur}s;animation-delay:{dly}s;"></div>'
st.markdown(particles_html + '</div>', unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ルーティング
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
params = st.query_params
page = params.get("page", "lp")

if page == "lp":
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: none !important; padding: 0 !important; margin: 0 !important; } .particles-bg { display: none !important; }</style>", unsafe_allow_html=True)
else:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 460px !important; margin: 0 auto; }</style>", unsafe_allow_html=True)

# ── 法務ページコンテンツ集約 ──
LEGAL_DOCS = {
    "terms": """
<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>利用規約 - OshiPay</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-[#0a0a0f] text-slate-200 p-8 font-sans"><main class="max-w-3xl mx-auto"><h1 class="text-3xl font-bold mb-8 text-white">利用規約</h1><div class="space-y-6 text-slate-300"><section><h2 class="text-xl font-bold text-white border-b border-white/10 pb-2 mb-4">第1条（目的）</h2><p>OshiPayは、活動する方への「純粋な応援」を届けるためのサービスです。</p></section><section><h2 class="text-xl font-bold text-white border-b border-white/10 pb-2 mb-4">第2条（手数料）</h2><p>応援金額の10%をシステム利用料として差し引き、90%を受取人に還元します。</p></section><section><h2 class="text-xl font-bold text-white border-b border-white/10 pb-2 mb-4">第3条（禁止事項）</h2><p>マネーロンダリング、法令違反、公序良俗に反する活動などを禁止します。</p></section></div></main></body></html>
""",
    "privacy": """
<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>プライバシーポリシー - OshiPay</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-[#0a0a0f] text-slate-200 p-8 font-sans"><main class="max-w-3xl mx-auto"><h1 class="text-3xl font-bold mb-8 text-white">プライバシーポリシー</h1><div class="space-y-6"><p>運営側（OshiPay）が応援者の個人情報やメッセージ内容を閲覧・保持することはありません。</p><p>すべての情報はStripe社によって安全に処理されます。</p></div></main></body></html>
""",
    "legal": """
<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>特定商取引法に基づく表記 - OshiPay</title><script src="https://cdn.tailwindcss.com"></script></head><body class="bg-[#0a0a0f] text-slate-200 p-8 font-sans"><main class="max-w-3xl mx-auto"><h1 class="text-3xl font-bold mb-8 text-white">特定商取引法に基づく表記</h1><table class="w-full text-left border border-white/10"><tr><th class="p-4 bg-white/5 border border-white/10">代表責任者</th><td class="p-4 border border-white/10">関　元喜</td></tr><tr><th class="p-4 bg-white/5 border border-white/10">所在地</th><td class="p-4 border border-white/10">〒418-0108 静岡県富士宮市猪之頭字内野941-35</td></tr><tr><th class="p-4 bg-white/5 border border-white/10">連絡先</th><td class="p-4 border border-white/10">oyajibuki@gmail.com</td></tr><tr><th class="p-4 bg-white/5 border border-white/10">販売価格</th><td class="p-4 border border-white/10">任意の応援金額</td></tr><tr><th class="p-4 bg-white/5 border border-white/10">引渡時期</th><td class="p-4 border border-white/10">決済完了後、即時反映</td></tr></table></main></body></html>
"""
}

if page in LEGAL_DOCS:
    components.html(LEGAL_DOCS[page], height=1200, scrolling=True); st.stop()

# ── ランディングページHTML (集約版) ──
LP_HTML = """
<!DOCTYPE html><html lang="ja"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>OshiPay - その感動、今すぐカタチに。</title><script src="https://cdn.tailwindcss.com"></script><script src="https://unpkg.com/lucide@latest"></script><style>body { font-family: sans-serif; } .fade-in { opacity: 0; transform: translateY(20px); transition: 1s ease-out both; } .fade-in.is-visible { opacity: 1; transform: translateY(0); }</style></head><body class="bg-[#0a0a0f] text-slate-200 overflow-x-hidden"><header class="flex items-center justify-between px-6 py-6 max-w-6xl mx-auto"><div class="flex items-center gap-2"><i data-lucide="flame" class="text-orange-500 w-8 h-8"></i><span class="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-orange-400 to-purple-500">OshiPay</span></div> <a href="?page=dashboard" target="_top" class="px-4 py-2 bg-white/10 rounded-full text-white no-underline text-sm">はじめる</a></header><main class="max-w-6xl mx-auto px-6 py-16 text-center"><h1 class="text-5xl md:text-7xl font-bold mb-8">その感動、<br><span class="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-orange-400">今すぐカタチに。</span></h1><p class="text-lg text-slate-400 mb-12">QRコードを読み取るだけ。応援をダイレクトに届けます。</p><a href="?page=dashboard" target="_top" class="inline-block px-12 py-5 bg-gradient-to-r from-purple-600 to-orange-500 rounded-full text-white font-bold text-xl no-underline">🚀 今すぐはじめる</a></main><footer class="border-t border-white/10 py-12 text-center"><div class="flex justify-center gap-6 mb-4"><a href="?page=terms" target="_top" class="text-xs text-slate-500 underline">利用規約</a><a href="?page=privacy" target="_top" class="text-xs text-slate-500 underline">プライバシーポリシー</a><a href="?page=legal" target="_top" class="text-xs text-slate-500 underline">特定商取引法</a></div><p class="text-xs text-slate-600">© 2026 OshiPay.</p></footer><script>lucide.createIcons();</script></body></html>
"""

# ── 各ページのレンダリング ──
if page == "lp":
    st.markdown("<style>iframe { height: 100vh !important; width: 100vw !important; border: none; }</style>", unsafe_allow_html=True)
    components.html(LP_HTML, height=2000, scrolling=True); st.stop()

if page == "success":
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:48px;margin:20px 0;">🎉</div><div class="section-title">応援完了！</div>', unsafe_allow_html=True)
    st.link_button("𝕏 でシェア", f"https://twitter.com/intent/tweet?text={urllib.parse.quote('応援したよ！ #OshiPay')}", use_container_width=True)
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.stop()

elif page == "cancel":
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:48px;margin:20px 0;">🤔</div><div class="section-title">キャンセルしました</div>', unsafe_allow_html=True)
    st.stop()

# 応援ページ
support_user = params.get("user", "")
if page == "support" and support_user:
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="support-avatar">{params.get("icon", "🎤")}</div><div class="support-name">{params.get("name", "Creator")}</div>', unsafe_allow_html=True)
    if st.button("🔥 1000円で応援する"):
        try:
            session = stripe.checkout.Session.create(
                payment_method_types=["card"], mode="payment",
                line_items=[{"price_data": {"currency": "jpy", "product_data": {"name": "応援"}, "unit_amount": 1000}, "quantity": 1}],
                success_url=f"{BASE_URL}?page=success", cancel_url=f"{BASE_URL}?page=cancel"
            )
            st.markdown(f'<script>window.top.location.href = "{session.url}";</script>', unsafe_allow_html=True)
        except Exception as e: st.error(e)
    st.stop()

else: # Dashboard
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">ダッシュボード</div>', unsafe_allow_html=True)
    st.info("ここにQRコード生成機能が表示されます。")
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms">利用規約</a><a href="{BASE_URL}?page=privacy">プライバシーポリシー</a><a href="{BASE_URL}?page=legal">特定商取引法</a></div>', unsafe_allow_html=True)