import os
import io
import base64
import uuid

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

# Stripe設定（st.secrets → 環境変数 のフォールバック）
try:
    stripe.api_key = st.secrets["STRIPE_SECRET"]
except Exception:
    stripe.api_key = os.environ.get("STRIPE_SECRET", "")

# プリセット金額
PRESET_AMOUNTS = [100, 500, 1000, 5000, 10000, 30000]

# プラットフォーム手数料（10%）
PLATFORM_FEE_PERCENT = 10

# アイコン選択肢
ICON_OPTIONS = {
    "🎤": "歌手・MC",
    "🎸": "ギター・バンド",
    "🎹": "ピアノ・キーボード",
    "🎨": "アーティスト・絵描き",
    "📷": "カメラマン・写真家",
    "☕": "カフェ・バリスタ",
    "✂️": "美容師・理容師",
    "🎮": "ゲーマー・配信者",
    "📚": "講師・先生",
    "💻": "エンジニア・クリエイター",
    "🎭": "役者・パフォーマー",
    "🔥": "その他",
}

# ベースURL
BASE_URL = os.environ.get("APP_URL", "https://oshipay.streamlit.app")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Stripe Connect ヘルパー関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_connect_account():
    """Stripe Express接続アカウントを作成"""
    account = stripe.Account.create(
        type="express",
        country="JP",
        capabilities={
            "card_payments": {"requested": True},
            "transfers": {"requested": True},
        },
        business_type="individual",
        business_profile={
            "mcc": "7922",
            "product_description": "OshiPay - 投げ銭サービス",
        },
    )
    return account.id


def create_account_link(account_id, return_params=""):
    """Stripeオンボーディング用のリンクを生成"""
    return_url = f"{BASE_URL}?page=dashboard&acct={account_id}{return_params}"
    refresh_url = f"{BASE_URL}?page=dashboard&acct={account_id}&refresh=1{return_params}"
    link = stripe.AccountLink.create(
        account=account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )
    return link.url


def send_support_email(to_email, creator_name, amount, message):
    """クリエイターに応援メッセージと金額をメールで通知"""
    try:
        smtp_server = st.secrets.get("SMTP_SERVER")
        smtp_port = st.secrets.get("SMTP_PORT", 587)
        smtp_user = st.secrets.get("SMTP_USER")
        smtp_pass = st.secrets.get("SMTP_PASS")

        if not all([smtp_server, smtp_user, smtp_pass]):
            return False, "SMTP設定が不足しています"

        subject = f"🔥 {creator_name}さんに応援が届きました！ (OshiPay)"
        body = f"""
{creator_name}さん

OshiPayを通じて応援が届きました！

💰 応援金額: {amount:,}円
💬 メッセージ:
{message if message else "（メッセージなし）"}

温かいサポート、嬉しいですね！
引き続き活動を頑張ってください！

--
OshiPay
{BASE_URL}
"""
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = smtp_user
        msg["To"] = to_email
        msg["Date"] = formatdate(localtime=True)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_pass)
            server.send_message(msg)
        return True, "送信成功"
    except Exception as e:
        return False, str(e)


def check_account_status(account_id):
    """接続アカウントの状態を確認"""
    try:
        account = stripe.Account.retrieve(account_id)
        return {
            "charges_enabled": account.charges_enabled,
            "payouts_enabled": account.payouts_enabled,
            "details_submitted": account.details_submitted,
        }
    except Exception:
        return None


def generate_qr_data(data: str) -> tuple[str, bytes]:
    """QRコードを生成し、中央にロゴを配置して(Base64文字列, バイト列)を返す"""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(data)
    qr.make(fit=True)

    # QRコードを画像として生成 (RGB)
    qr_img = qr.make_image(fill_color="black", back_color="white").convert('RGB')
    
    # ロゴ画像の読み込み
    logo_path = "assets/oshi_logo.png"
    if os.path.exists(logo_path):
        try:
            logo = Image.open(logo_path).convert("RGBA")
            qr_width, qr_height = qr_img.size
            logo_size = int(qr_width * 0.22)
            logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
            pos = ((qr_width - logo_size) // 2, (qr_height - logo_size) // 2)
            qr_img.paste(logo, pos, logo)
        except Exception:
            pass # ロゴ読み込み失敗時は通常のQRのみ
    
    # バッファに保存
    buffered = io.BytesIO()
    qr_img.save(buffered, format="PNG")
    qr_bytes = buffered.getvalue()
    img_b64 = base64.b64encode(qr_bytes).decode()
    
    return img_b64, qr_bytes




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# プレミアムCSS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=Noto+Sans+JP:wght@400;500;700;900&display=swap');

/* ── Streamlit UI非表示 ── */
#MainMenu {visibility: hidden;}
header {visibility: hidden;}
footer {visibility: hidden;}
.stDeployButton {display: none;}
[data-testid="stToolbar"] {display: none;}
[data-testid="stDecoration"] {display: none;}

/* ── 背景 ── */
.stApp {
    background: #08080f !important;
    font-family: 'Inter', 'Noto Sans JP', sans-serif !important;
}

.stApp::before {
    content: '';
    position: fixed;
    top: -50%; left: -50%;
    width: 200%; height: 200%;
    background:
        radial-gradient(ellipse at 20% 20%, rgba(139,92,246,0.08) 0%, transparent 50%),
        radial-gradient(ellipse at 80% 80%, rgba(236,72,153,0.06) 0%, transparent 50%),
        radial-gradient(ellipse at 50% 50%, rgba(249,115,22,0.04) 0%, transparent 50%);
    z-index: 0;
    pointer-events: none;
    animation: bgShift 20s ease-in-out infinite alternate;
}

@keyframes bgShift {
    0% { transform: translate(0, 0) rotate(0deg); }
    100% { transform: translate(-2%, -2%) rotate(3deg); }
}

.stMainBlockContainer, .block-container {
    position: relative;
    z-index: 1;
    max-width: 460px !important;
    padding-top: 2rem !important;
}

/* ── ロゴ ── */
.oshi-logo {
    text-align: center;
    margin-bottom: 6px;
}
.oshi-logo .icon { font-size: 28px; }
.oshi-logo .text {
    font-size: 22px;
    font-weight: 800;
    background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    letter-spacing: -0.5px;
}
.oshi-tagline {
    text-align: center;
    font-size: 13px;
    color: rgba(240,240,245,0.35);
    margin-bottom: 28px;
    letter-spacing: 1px;
}

/* ── グラスカード (装飾用、Streamlit widgetは包めないので背景として使用) ── */
.glass-card {
    background: rgba(255,255,255,0.04);
    backdrop-filter: blur(20px);
    -webkit-backdrop-filter: blur(20px);
    border: 1px solid rgba(255,255,255,0.08);
    border-radius: 28px;
    padding: 32px 24px;
    position: relative;
    overflow: hidden;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
    margin-bottom: 16px;
}
.glass-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 1px;
    background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
}

/* ── メインコンテンツブロックにグラス効果を適用 ── */
.stMainBlockContainer > div > div > div > div {
    position: relative;
    z-index: 1;
}

/* ── セクションタイトル ── */
.section-title {
    font-size: 20px;
    font-weight: 700;
    text-align: center;
    color: #f0f0f5;
    margin-bottom: 6px;
}
.section-subtitle {
    font-size: 13px;
    color: rgba(240,240,245,0.6);
    text-align: center;
    margin-bottom: 24px;
    line-height: 1.8;
}

/* ── 応援ターゲット ── */
.support-avatar {
    width: 72px; height: 72px;
    border-radius: 50%;
    background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 32px;
    margin: 0 auto 14px;
    box-shadow: 0 0 30px rgba(139,92,246,0.3);
    animation: avatarPulse 3s ease-in-out infinite;
}
@keyframes avatarPulse {
    0%, 100% { box-shadow: 0 0 30px rgba(139,92,246,0.3); }
    50% { box-shadow: 0 0 50px rgba(139,92,246,0.5), 0 0 80px rgba(236,72,153,0.2); }
}
.support-name {
    font-size: 22px;
    font-weight: 800;
    text-align: center;
    color: #f0f0f5;
    margin-bottom: 4px;
}
.support-label {
    font-size: 13px;
    color: rgba(240,240,245,0.6);
    text-align: center;
    margin-bottom: 20px;
}

/* ── 金額グリッド ── */
.amount-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
    margin-bottom: 16px;
}
.amount-btn {
    padding: 18px 8px;
    background: rgba(255,255,255,0.04);
    border: 2px solid rgba(255,255,255,0.08);
    border-radius: 14px;
    color: #f0f0f5;
    font-family: 'Inter', 'Noto Sans JP', sans-serif;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
    transition: all 0.3s cubic-bezier(0.34,1.56,0.64,1);
    text-align: center;
}
.amount-btn:hover {
    border-color: #8b5cf6;
    background: rgba(139,92,246,0.08);
    transform: translateY(-2px);
}
.amount-btn.selected {
    border-color: #8b5cf6;
    background: rgba(139,92,246,0.15);
    box-shadow: 0 0 20px rgba(139,92,246,0.3), inset 0 0 20px rgba(139,92,246,0.05);
}

/* ── Columns内ボタン（金額＆アイコン）はカードスタイル ── */
div[data-testid="stHorizontalBlock"] .stButton > button {
    background: rgba(255,255,255,0.04) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    box-shadow: none !important;
    border-radius: 14px !important;
    padding: 12px 8px !important;
    font-size: 22px !important;
    transition: all 0.2s ease !important;
}
div[data-testid="stHorizontalBlock"] .stButton > button:hover {
    background: rgba(139,92,246,0.1) !important;
    border-color: #8b5cf6 !important;
    transform: translateY(-2px) !important;
    box-shadow: none !important;
}

/* ── 金額表示 ── */
.selected-amount-display {
    text-align: center;
    font-size: 36px;
    font-weight: 900;
    background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    margin: 10px 0 8px;
    min-height: 48px;
}

/* ── 区切り線 ── */
.oshi-divider {
    height: 1px;
    background: rgba(255,255,255,0.08);
    margin: 20px 0;
}

/* ── Streamlit ボタンのスタイル上書き ── */
.stButton > button {
    width: 100%;
    background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316) !important;
    color: white !important;
    border: none !important;
    border-radius: 9999px !important;
    padding: 16px 32px !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    font-family: 'Inter', 'Noto Sans JP', sans-serif !important;
    box-shadow: 0 4px 20px rgba(139,92,246,0.3) !important;
    transition: all 0.3s cubic-bezier(0.16,1,0.3,1) !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    box-shadow: 0 6px 30px rgba(139,92,246,0.5) !important;
    transform: translateY(-2px) !important;
}
.stButton > button:active {
    transform: scale(0.97) !important;
}

/* セカンダリボタン */
div[data-testid="stHorizontalBlock"] .stDownloadButton > button,
.secondary-btn .stButton > button,
.secondary-btn .stDownloadButton > button {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    box-shadow: none !important;
}
.secondary-btn .stButton > button:hover,
.secondary-btn .stDownloadButton > button:hover {
    background: rgba(255,255,255,0.1) !important;
    box-shadow: none !important;
}
.stDownloadButton > button {
    width: 100%;
    background: rgba(255,255,255,0.06) !important;
    color: white !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 9999px !important;
    padding: 12px 20px !important;
    font-size: 14px !important;
    font-weight: 600 !important;
    font-family: 'Inter', 'Noto Sans JP', sans-serif !important;
    box-shadow: none !important;
}

/* ── Input スタイル ── */
input, .stTextInput input, .stNumberInput input,
[data-baseweb="input"] input,
[data-baseweb="base-input"] input {
    background: rgba(255,255,255,0.05) !important;
    background-color: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
    color: #f0f0f5 !important;
    font-family: 'Inter', 'Noto Sans JP', sans-serif !important;
    font-size: 15px !important;
    padding: 14px 18px !important;
    caret-color: #8b5cf6 !important;
}
input:focus, .stTextInput input:focus, .stNumberInput input:focus {
    border-color: #8b5cf6 !important;
    box-shadow: 0 0 0 3px rgba(139,92,246,0.15) !important;
}
input::placeholder {
    color: rgba(240,240,245,0.3) !important;
}
[data-baseweb="base-input"] {
    background-color: rgba(255,255,255,0.05) !important;
    border-color: rgba(255,255,255,0.08) !important;
    border-radius: 14px !important;
}
.stTextInput label, .stNumberInput label {
    font-size: 12px !important;
    font-weight: 600 !important;
    color: rgba(240,240,245,0.6) !important;
    text-transform: uppercase !important;
    letter-spacing: 1px !important;
}
/* ── Streamlit警告/エラー ── */
.stAlert {
    background: rgba(255,255,255,0.04) !important;
    border-radius: 14px !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
}

/* ── QR表示 ── */
.qr-frame {
    background: white;
    padding: 16px;
    border-radius: 20px;
    box-shadow: 0 0 60px rgba(139,92,246,0.25), 0 0 120px rgba(236,72,153,0.1);
    display: inline-block;
    margin: 0 auto;
}
.qr-frame img {
    display: block;
    width: 200px;
    height: 200px;
}

/* ── 成功アイコン ── */
.success-icon {
    width: 100px; height: 100px;
    border-radius: 50%;
    background: linear-gradient(135deg, #10b981, #34d399);
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 48px;
    margin: 0 auto 24px;
    animation: successPop 0.6s cubic-bezier(0.34,1.56,0.64,1);
    box-shadow: 0 0 40px rgba(16,185,129,0.3);
}
@keyframes successPop {
    0% { transform: scale(0); opacity: 0; }
    50% { transform: scale(1.2); }
    100% { transform: scale(1); opacity: 1; }
}

/* ── フッター ── */
.oshi-footer {
    text-align: center;
    margin-top: 24px;
    font-size: 11px;
    color: rgba(240,240,245,0.35);
    letter-spacing: 0.5px;
}
.oshi-footer a {
    color: #8b5cf6;
    text-decoration: none;
}

/* ── アニメーション ── */
@keyframes fadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to { opacity: 1; transform: translateY(0); }
}
@keyframes slideUp {
    from { opacity: 0; transform: translateY(30px); }
    to { opacity: 1; transform: translateY(0); }
}
.animate-fade-in { animation: fadeIn 0.6s cubic-bezier(0.16,1,0.3,1) both; }
.animate-slide-up { animation: slideUp 0.6s cubic-bezier(0.16,1,0.3,1) both; }
.delay-1 { animation-delay: 0.1s; }
.delay-2 { animation-delay: 0.2s; }
.delay-3 { animation-delay: 0.3s; }

/* ── Streamlitタブのスタイル ── */
.stTabs [data-baseweb="tab-list"] {
    gap: 8px;
    background: rgba(255,255,255,0.03);
    border-radius: 14px;
    padding: 4px;
    border: 1px solid rgba(255,255,255,0.06);
}
.stTabs [data-baseweb="tab"] {
    border-radius: 10px;
    color: rgba(240,240,245,0.5);
    font-weight: 600;
    font-size: 13px;
    padding: 8px 16px;
}
.stTabs [aria-selected="true"] {
    background: rgba(139,92,246,0.15) !important;
    color: #f0f0f5 !important;
}
.stTabs [data-baseweb="tab-highlight"] {
    background: transparent !important;
}
.stTabs [data-baseweb="tab-border"] {
    display: none;
}

/* ── リンクボタン ── */
.stLinkButton > a {
    width: 100%;
    background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316) !important;
    color: white !important;
    border: none !important;
    border-radius: 9999px !important;
    padding: 16px 32px !important;
    font-size: 16px !important;
    font-weight: 700 !important;
    box-shadow: 0 4px 20px rgba(139,92,246,0.3) !important;
    text-decoration: none !important;
}

    font-size: 11px;
    color: rgba(240,240,245,0.3);
}
/* パーティクル */
.particles-bg {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    pointer-events: none;
    z-index: 0;
    overflow: hidden;
}
.particle {
    position: absolute;
    border-radius: 50%;
    animation: floatParticle linear infinite;
    opacity: 0.15;
}
@keyframes floatParticle {
    0% { transform: translateY(100vh) rotate(0deg); opacity: 0; }
    10% { opacity: 0.15; }
    90% { opacity: 0.15; }
    100% { transform: translateY(-10vh) rotate(360deg); opacity: 0; }
}
</style>
""", unsafe_allow_html=True)

# ── パーティクル背景 ──
import random
particles_html = '<div class="particles-bg">'
for i in range(30):
    size = random.uniform(2, 5)
    left = random.uniform(0, 100)
    duration = random.uniform(15, 30)
    delay = random.uniform(0, 15)
    hue = random.choice([270, 330])
    particles_html += f'<div class="particle" style="width:{size}px;height:{size}px;left:{left}%;background:hsl({hue},80%,65%);animation-duration:{duration}s;animation-delay:{delay}s;"></div>'
particles_html += '</div>'
st.markdown(particles_html, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ページルーティング (query params)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
params = st.query_params
# パラメータがない場合は lp をデフォルトにする
page = params.get("page", "lp")

# 特定のパラメータがある場合はそれぞれのページへ誘導
if not params.get("page"):
    if params.get("user") or params.get("acct"):
        page = "support"
    else:
        page = "lp"

support_user = params.get("user", "")
support_name = params.get("name", "")
support_icon = params.get("icon", "🎤")
connect_acct = params.get("acct", "")  # Stripe Connect アカウントID
success_name = params.get("s_name", "")  # 決済成功時の名前
success_amount = params.get("s_amt", "") # 決済成功時の金額
session_id = params.get("session_id", "") # 決済成功時のセッションID


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 成功ページ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
if page == "success":
    # 紙吹雪アニメーション
    confetti_html = """
    <canvas id="confetti-canvas" style="position:fixed;top:0;left:0;width:100%;height:100%;pointer-events:none;z-index:100;"></canvas>
    <script>
    (function(){
        const canvas = document.getElementById('confetti-canvas');
        if(!canvas) return;
        const ctx = canvas.getContext('2d');
        let confetti = [], w, h, burstCount = 0;
        function resize(){ w = canvas.width = window.innerWidth; h = canvas.height = window.innerHeight; }
        resize(); window.addEventListener('resize', resize);
        const colors = ['#8b5cf6','#ec4899','#f97316','#22d3ee','#10b981','#fbbf24'];
        class C {
            constructor(){ this.x=Math.random()*w; this.y=-20; this.size=Math.random()*8+4;
            this.sy=Math.random()*3+2; this.sx=(Math.random()-0.5)*4;
            this.r=Math.random()*360; this.rs=(Math.random()-0.5)*10;
            this.color=colors[Math.floor(Math.random()*colors.length)]; this.o=1; }
            update(){ this.y+=this.sy; this.x+=this.sx; this.r+=this.rs; this.sy+=0.05; if(this.y>h)this.o-=0.02; }
            draw(){ if(this.o<=0)return; ctx.save(); ctx.translate(this.x,this.y); ctx.rotate(this.r*Math.PI/180);
            ctx.globalAlpha=this.o; ctx.fillStyle=this.color; ctx.fillRect(-this.size/2,-this.size/2,this.size,this.size*0.6); ctx.restore(); }
        }
        const bi = setInterval(()=>{ for(let i=0;i<15;i++) confetti.push(new C()); burstCount++; if(burstCount>6) clearInterval(bi); }, 400);
        function animate(){ ctx.clearRect(0,0,w,h); confetti=confetti.filter(c=>c.o>0); confetti.forEach(c=>{c.update();c.draw();}); if(confetti.length>0||burstCount<=6) requestAnimationFrame(animate); }
        animate();
    })();
    </script>
    """
    st.markdown(confetti_html, unsafe_allow_html=True)

    # ロゴ
    st.markdown('<div class="oshi-logo animate-fade-in"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)


    st.markdown('<div class="success-icon">🎉</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">応援完了！</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">あなたの応援が届きました！<br>温かいサポート、ありがとうございます 🙏✨</div>', unsafe_allow_html=True)
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)

    # メール送信ロジック（一度だけ実行）
    if session_id and "processed_sessions" not in st.session_state:
        st.session_state.processed_sessions = set()

    if session_id and session_id not in st.session_state.processed_sessions:
        try:
            # セッション詳細を取得
            checkout_session = stripe.checkout.Session.retrieve(session_id, expand=["payment_intent"])
            msg_content = checkout_session.metadata.get("support_message", "")
            amt_val = checkout_session.amount_total
            
            # クリエイターのアカウント情報を取得
            creator_acct_id = checkout_session.metadata.get("user_id")
            if creator_acct_id:
                creator_acct = stripe.Account.retrieve(creator_acct_id)
                creator_email = creator_acct.email
                creator_name = creator_acct.settings.dashboard.display_name or creator_name
                
                if creator_email:
                    success, error = send_support_email(creator_email, creator_name, amt_val, msg_content)
                    if success:
                        st.toast("応援メッセージをメールで送信しました！📧")
                    else:
                        st.warning(f"メール送信に失敗しました: {error}")
            
            st.session_state.processed_sessions.add(session_id)
        except Exception as e:
            st.error(f"情報の取得に失敗しました: {e}")

    # Xシェア文言のカスタマイズ
    if success_name and success_amount:
        share_text = f"{success_name}さんに{success_amount}円 応援したよ！\nhttps://oshipay.streamlit.app/ \n#OshiPay"
    else:
        share_text = "OshiPay で応援しました！🔥 #OshiPay"
    
    encoded_text = urllib.parse.quote(share_text)
    st.link_button("𝕏 でシェア", f"https://twitter.com/intent/tweet?text={encoded_text}", use_container_width=True)

    st.markdown("""
    <div class="oshi-footer animate-fade-in delay-3">Powered by <a href="?page=dashboard">OshiPay</a></div>
    <div class="legal-links animate-fade-in delay-3" style="margin-top:20px;">
        <a href="#">利用規約</a>
        <a href="#">プライバシーポリシー</a>
        <a href="#">特定商取引法に基づく表記</a>
    </div>
    """, unsafe_allow_html=True)




# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 キャンセルページ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "cancel":
    st.markdown('<div class="oshi-logo animate-fade-in"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)


    st.markdown('<div style="text-align:center;font-size:64px;margin-bottom:16px;">🤔</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">キャンセルしました</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">決済はキャンセルされました。<br>またいつでも応援できます！<br>お気持ちだけで嬉しいです 😊</div>', unsafe_allow_html=True)


    st.markdown('<div class="oshi-footer animate-fade-in delay-3">Powered by <a href="?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 ランディングページ (提供された最新デザイン)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "lp":
    # ユーザー提供のHTMLをベースに、ボタンクリックで dashboard へ遷移するように Aタグを修正
    lp_html = """
<!DOCTYPE html>
<html lang="ja">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>OshiPay - その感動、今すぐカタチに。</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script src="https://unpkg.com/lucide@latest"></script>
  <style>
    body { font-family: 'Helvetica Neue', Arial, 'Hiragino Kaku Gothic ProN', 'Hiragino Sans', Meiryo, sans-serif; }
    .fade-in-section { opacity: 0; transform: translateY(40px); transition: opacity 1s ease-out, transform 1s ease-out; will-change: opacity, visibility; }
    .fade-in-section.is-visible { opacity: 1; transform: translateY(0); }
  </style>
</head>
<body class="min-h-screen bg-[#0a0a0f] text-slate-200 selection:bg-purple-500/30 overflow-x-hidden relative">
  <div class="absolute top-0 left-1/2 -translate-x-1/2 w-full max-w-5xl h-[500px] bg-gradient-to-b from-purple-900/20 via-orange-900/5 to-transparent blur-3xl pointer-events-none -z-10"></div>
  <div class="absolute top-1/4 left-10 w-72 h-72 bg-purple-600/10 rounded-full blur-[100px] pointer-events-none -z-10"></div>
  <div class="absolute bottom-1/4 right-10 w-96 h-96 bg-orange-600/10 rounded-full blur-[100px] pointer-events-none -z-10"></div>
  <header class="flex items-center justify-between px-6 py-6 max-w-6xl mx-auto relative z-10">
    <div class="flex items-center gap-2">
      <i data-lucide="flame" class="text-orange-500 w-8 h-8 drop-shadow-[0_0_15px_rgba(249,115,22,0.5)]"></i>
      <span class="text-2xl font-bold bg-clip-text text-transparent bg-gradient-to-r from-orange-400 to-purple-500 tracking-tight">OshiPay</span>
    </div>
    <nav class="hidden md:flex gap-8 text-sm font-medium text-slate-400">
      <a href="#how-it-works" class="hover:text-white transition-colors">使い方</a>
      <a href="#usecases" class="hover:text-white transition-colors">利用シーン</a>
      <a href="#security" class="hover:text-white transition-colors">安全性</a>
    </nav>
  </header>
  <main class="max-w-7xl mx-auto px-6 pt-16 pb-32 relative z-10 flex flex-col lg:flex-row items-center gap-12">
    <div class="flex-1 text-center lg:text-left">
      <div class="fade-in-section">
        <div class="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs text-purple-300 mb-8 backdrop-blur-sm">
          <span class="relative flex h-2 w-2">
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
            <span class="relative inline-flex rounded-full h-2 w-2 bg-purple-500"></span>
          </span>
          サービス提供開始
        </div>
      </div>
      <div class="fade-in-section" style="transition-delay: 100ms;">
        <h1 class="text-5xl md:text-7xl lg:text-6xl xl:text-7xl font-extrabold tracking-tight mb-8 leading-[1.15]">
          その感動、<br class="hidden lg:block" />
          <span class="bg-clip-text text-transparent bg-gradient-to-r from-purple-400 via-pink-500 to-orange-400 drop-shadow-sm">今すぐカタチに。</span>
        </h1>
      </div>
      <div class="fade-in-section" style="transition-delay: 200ms;">
        <p class="text-lg md:text-xl text-slate-400 max-w-2xl mx-auto lg:mx-0 mb-12 leading-relaxed font-light">
          アカウントを作ってQRコードを表示するだけ。<br />
          汗水流して頑張るあなたへ、応援したい人の温かい気持ちをダイレクトに届けます。
        </p>
      </div>
      <div class="fade-in-section" style="transition-delay: 300ms;">
        <div class="flex flex-col sm:flex-row items-center justify-center lg:justify-start gap-4">
          <a href="?page=dashboard" target="_top" class="group relative w-full sm:w-auto px-8 py-4 bg-gradient-to-r from-purple-600 to-orange-500 rounded-full text-white font-bold text-lg hover:shadow-[0_0_30px_rgba(168,85,247,0.4)] transition-all duration-300 hover:scale-105 overflow-hidden text-center no-underline decoration-transparent">
            <div class="absolute inset-0 bg-white/20 group-hover:translate-x-full -translate-x-full skew-x-12 transition-transform duration-500"></div>
            <span class="flex items-center justify-center gap-2 relative z-10">🚀 今すぐはじめる (無料)</span>
          </a>
          <a href="#how-it-works" class="group w-full sm:w-auto px-8 py-4 rounded-full text-white font-medium text-lg border border-white/10 hover:bg-white/5 transition-all duration-300 flex items-center justify-center gap-2 no-underline decoration-transparent">
            詳しい使い方を見る
            <i data-lucide="arrow-right" class="w-5 h-5 group-hover:translate-x-1 transition-transform"></i>
          </a>
        </div>
      </div>
    </div>
    <div class="flex-1 w-full max-w-xl lg:max-w-none relative mt-8 lg:mt-0">
      <div class="fade-in-section" style="transition-delay: 400ms;">
        <div class="relative rounded-2xl overflow-hidden shadow-2xl shadow-purple-900/40 aspect-[4/3] border border-white/10 group">
          <div class="absolute inset-0 bg-gradient-to-t from-[#0a0a0f] via-transparent to-transparent z-10"></div>
          <img src="https://images.unsplash.com/photo-1511671782779-c97d3d27a1d4?q=80&w=2070&auto=format&fit=crop" alt="ストリートパフォーマンス" class="w-full h-full object-cover group-hover:scale-105 transition-transform duration-700 opacity-90" />
          <div class="absolute bottom-6 right-6 z-20 bg-white/10 backdrop-blur-md p-4 rounded-xl border border-white/20 shadow-2xl flex flex-col items-center gap-2 transform rotate-[-5deg] group-hover:rotate-0 transition-transform duration-500">
            <div class="bg-white p-2.5 rounded-lg shadow-inner relative flex items-center justify-center">
              <i data-lucide="qr-code" class="w-16 h-16 text-slate-900"></i>
              <div class="absolute bg-white rounded-full p-0.5 flex items-center justify-center">
                <i data-lucide="flame" class="w-5 h-5 text-orange-500" style="fill: rgba(249,115,22,0.2);"></i>
              </div>
            </div>
            <div class="text-xs font-extrabold tracking-wide bg-gradient-to-r from-purple-400 to-orange-400 bg-clip-text text-transparent">SCAN TO SUPPORT</div>
          </div>
        </div>
      </div>
    </div>
  </main>
  <section id="how-it-works" class="py-24 relative z-10 bg-white/[0.02] border-y border-white/5">
    <div class="max-w-6xl mx-auto px-6">
      <div class="fade-in-section text-center mb-16">
        <h2 class="text-sm font-bold tracking-widest text-orange-400 uppercase mb-3">How it works</h2>
        <h3 class="text-3xl md:text-4xl font-bold">応援が届くまで、わずか3ステップ</h3>
      </div>
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-16 lg:gap-24">
        <div class="relative">
          <h4 class="text-xl md:text-2xl font-bold mb-10 flex items-center justify-center lg:justify-start gap-3">
            <span class="bg-purple-500/20 text-purple-400 p-2.5 rounded-xl"><i data-lucide="mic" class="w-6 h-6"></i></span>応援を受けたい人
          </h4>
          <div class="space-y-8 relative before:absolute before:inset-0 before:ml-[1.15rem] before:-translate-x-px md:before:ml-[1.15rem] before:h-full before:w-0.5 before:bg-gradient-to-b before:from-purple-500/50 before:to-transparent">
            <div class="fade-in-section relative flex items-center group" style="transition-delay: 100ms;">
              <div class="flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0f] bg-purple-500 text-white font-bold z-10 shrink-0">1</div>
              <div class="ml-6 p-5 bg-white/5 rounded-2xl border border-white/10 w-full hover:bg-white/10 transition-colors">
                <h5 class="font-bold text-lg mb-2">Stripeで決済登録</h5>
                <p class="text-sm text-slate-400 leading-relaxed">安全なStripe経由で口座情報を登録します。審査なしで即日完了。</p>
              </div>
            </div>
            <div class="fade-in-section relative flex items-center group" style="transition-delay: 200ms;">
              <div class="flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0f] bg-purple-500 text-white font-bold z-10 shrink-0">2</div>
              <div class="ml-6 p-5 bg-white/5 rounded-2xl border border-white/10 w-full hover:bg-white/10 transition-colors">
                <h5 class="font-bold text-lg mb-2">専用QRの発行</h5>
                <p class="text-sm text-slate-400 leading-relaxed">あなただけの応援用QRコードが生成されます。</p>
              </div>
            </div>
            <div class="fade-in-section relative flex items-center group" style="transition-delay: 300ms;">
              <div class="flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0f] bg-purple-500 text-white font-bold z-10 shrink-0">3</div>
              <div class="ml-6 p-5 bg-white/5 rounded-2xl border border-white/10 w-full hover:bg-white/10 transition-colors">
                <h5 class="font-bold text-lg mb-2">QRをさりげなく公開</h5>
                <p class="text-sm text-slate-400 leading-relaxed">路上に置いたり、胸にシールで貼ったり。ファンが見える場所に掲示するだけ。</p>
              </div>
            </div>
          </div>
        </div>
        <div class="relative">
          <h4 class="text-xl md:text-2xl font-bold mb-10 flex items-center justify-center lg:justify-start gap-3">
            <span class="bg-orange-500/20 text-orange-400 p-2.5 rounded-xl"><i data-lucide="heart" class="w-6 h-6"></i></span>応援したい人
          </h4>
          <div class="space-y-8 relative before:absolute before:inset-0 before:ml-[1.15rem] before:-translate-x-px md:before:ml-[1.15rem] before:h-full before:w-0.5 before:bg-gradient-to-b before:from-orange-500/50 before:to-transparent">
            <div class="fade-in-section relative flex items-center group" style="transition-delay: 200ms;">
              <div class="flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0f] bg-orange-500 text-white font-bold z-10 shrink-0"><i data-lucide="smartphone" class="w-4 h-4"></i></div>
              <div class="ml-6 p-5 bg-white/5 rounded-2xl border border-white/10 w-full hover:bg-white/10 transition-colors">
                <h5 class="font-bold text-lg mb-2">QRコードをスキャン</h5>
                <p class="text-sm text-slate-400 leading-relaxed">専用アプリは不要。スマホの標準カメラでサッと読み取るだけ。</p>
              </div>
            </div>
            <div class="fade-in-section relative flex items-center group" style="transition-delay: 300ms;">
              <div class="flex items-center justify-center w-10 h-10 rounded-full border-4 border-[#0a0a0f] bg-orange-500 text-white font-bold z-10 shrink-0"><i data-lucide="credit-card" class="w-4 h-4"></i></div>
              <div class="ml-6 p-5 bg-white/5 rounded-2xl border border-white/10 w-full hover:bg-white/10 transition-colors">
                <h5 class="font-bold text-lg mb-2">応援金額を入力して決済</h5>
                <p class="text-sm text-slate-400 leading-relaxed">Apple PayやGoogle Payで、わずか数秒でスマートに支払いが完了。温かい応援メッセージも一緒に送れます。</p>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
  <section id="usecases" class="py-24 relative z-10">
    <div class="max-w-6xl mx-auto px-6">
      <div class="fade-in-section text-center mb-16">
        <h2 class="text-sm font-bold tracking-widest text-purple-400 uppercase mb-3">Use Cases</h2>
        <h3 class="text-3xl md:text-4xl font-bold">いろんなシーンで応援を</h3>
      </div>
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div class="fade-in-section" style="transition-delay: 100ms;">
          <div class="group bg-white/[0.03] border border-white/10 rounded-3xl p-8 hover:bg-white/[0.06] transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:shadow-purple-500/10 h-full backdrop-blur-sm relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-purple-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div class="w-14 h-14 bg-purple-500/20 rounded-2xl flex items-center justify-center mb-6 text-2xl group-hover:scale-110 transition-transform">🎤</div>
            <h4 class="text-xl font-bold mb-3 text-white">ストリートパフォーマンス</h4>
            <p class="text-slate-400 leading-relaxed font-light">QRコードを貼るだけで、聴衆から直接応援が届きます。小銭を持ち歩かない時代に最適な、新しい投げ銭のカタチです。</p>
          </div>
        </div>
        <div class="fade-in-section" style="transition-delay: 200ms;">
          <div class="group bg-white/[0.03] border border-white/10 rounded-3xl p-8 hover:bg-white/[0.06] transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:shadow-orange-500/10 h-full backdrop-blur-sm relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-orange-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div class="w-14 h-14 bg-orange-500/20 rounded-2xl flex items-center justify-center mb-6 text-2xl group-hover:scale-110 transition-transform">☕</div>
            <h4 class="text-xl font-bold mb-3 text-white">カフェ・飲食店</h4>
            <p class="text-slate-400 leading-relaxed font-light">素晴らしい接客やサービスへの感謝をチップとして。店員さん個人への応援を、スマートかつスムーズに実現します。</p>
          </div>
        </div>
        <div class="fade-in-section" style="transition-delay: 300ms;">
          <div class="group bg-white/[0.03] border border-white/10 rounded-3xl p-8 hover:bg-white/[0.06] transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:shadow-blue-500/10 h-full backdrop-blur-sm relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div class="w-14 h-14 bg-blue-500/20 rounded-2xl flex items-center justify-center mb-6 text-2xl group-hover:scale-110 transition-transform">🧹</div>
            <h4 class="text-xl font-bold mb-3 text-white">施設の清掃・維持</h4>
            <p class="text-slate-400 leading-relaxed font-light">いつも綺麗な環境への感謝を。トイレやビルの清掃員さんなど、見えないところで影で支える人々へ直接お礼を。</p>
          </div>
        </div>
        <div class="fade-in-section" style="transition-delay: 400ms;">
          <div class="group bg-white/[0.03] border border-white/10 rounded-3xl p-8 hover:bg-white/[0.06] transition-all duration-300 hover:-translate-y-1 hover:shadow-2xl hover:shadow-pink-500/10 h-full backdrop-blur-sm relative overflow-hidden">
            <div class="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-pink-500 to-transparent opacity-0 group-hover:opacity-100 transition-opacity"></div>
            <div class="w-14 h-14 bg-pink-500/20 rounded-2xl flex items-center justify-center mb-6 text-2xl group-hover:scale-110 transition-transform">🔥</div>
            <h4 class="text-xl font-bold mb-3 text-white">あらゆるプロジェクト</h4>
            <p class="text-slate-400 leading-relaxed font-light">情熱を持って活動するすべての人に。面倒な登録は不要、最短1分であなた専用の投げ銭受付を開始できます。</p>
          </div>
        </div>
      </div>
    </div>
  </section>
  <section id="security" class="py-24 relative z-10">
    <div class="max-w-4xl mx-auto px-6">
      <div class="fade-in-section">
        <div class="relative rounded-3xl bg-gradient-to-b from-white/5 to-transparent border border-white/10 p-1 overflow-hidden">
          <div class="absolute inset-0 bg-[linear-gradient(to_right,rgba(255,255,255,0.02)_1px,transparent_1px),linear-gradient(to_bottom,rgba(255,255,255,0.02)_1px,transparent_1px)] bg-[size:20px_20px]"></div>
          <div class="relative bg-[#0d0d14] rounded-[22px] p-8 md:p-12 text-center backdrop-blur-xl border border-white/5">
            <div class="w-16 h-16 bg-white/5 rounded-full flex items-center justify-center mx-auto mb-6 text-green-400"><i data-lucide="shield-check" class="w-8 h-8"></i></div>
            <h3 class="text-2xl md:text-3xl font-bold mb-4">安心の決済システムと、完全なプライバシー保護。</h3>
            <p class="text-lg text-slate-400 mb-8 font-light leading-relaxed">
              世界基準のセキュリティを誇る <span class="text-white font-medium">Stripe決済</span> を利用。さらに、応援者と受取人の<span class="text-white font-medium border-b border-green-500/50 pb-0.5">個人名、住所、決済情報やメッセージは運営側（OshiPay）には一切知られません。</span><br class="hidden md:block" />お互いのプライバシーを完全に守りながら、応援された金額の <span class="text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-orange-400 font-bold text-xl">90%</span> がダイレクトに手元に届きます。
            </p>
            <div class="flex flex-wrap items-center justify-center gap-4">
              <div class="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-white/5 border border-white/10"><i data-lucide="eye-off" class="w-5 h-5 text-green-400"></i><span class="text-sm font-medium">個人情報・メッセージの完全非公開</span></div>
              <div class="inline-flex items-center gap-2 px-6 py-3 rounded-full bg-white/5 border border-white/10"><i data-lucide="heart" class="w-5 h-5 text-pink-500" style="fill: rgba(236,72,153,0.2);"></i><span class="text-sm font-medium">応援の気持ちを、そのままに</span></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </section>
  <footer class="border-t border-white/10 mt-12 py-12 relative z-10">
    <div class="max-w-6xl mx-auto px-6 flex flex-col md:flex-row items-center justify-between gap-6">
      <div class="flex items-center gap-2"><i data-lucide="flame" class="text-orange-500 w-6 h-6"></i><span class="text-xl font-bold text-white">OshiPay</span></div>
      <p class="text-sm text-slate-500">© 2026 OshiPay. All rights reserved.</p>
    </div>
  </footer>
  <script>
    document.addEventListener("DOMContentLoaded", function() {
      lucide.createIcons();
      const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
          if (entry.isIntersecting) {
            entry.target.classList.add('is-visible');
            observer.unobserve(entry.target);
          }
        });
      }, { threshold: 0.1, rootMargin: "0px 0px -50px 0px" });
      const fadeElements = document.querySelectorAll('.fade-in-section');
      fadeElements.forEach(el => observer.observe(el));
    });
  </script>
</body>
</html>
    """
    st.components.v1.html(lp_html, height=2500, scrolling=False)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 応援ページ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "support" and support_user:
    display_name = support_name or support_user

    # ロゴ
    st.markdown('<div class="oshi-logo animate-fade-in"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="oshi-tagline animate-fade-in delay-1">その感動、今すぐカタチに。</div>', unsafe_allow_html=True)



    # アバター・名前（選択されたアイコンを表示）
    st.markdown(f'<div class="support-avatar">{support_icon}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="support-name">{display_name}</div>', unsafe_allow_html=True)
    st.markdown('<div class="support-label">を応援しよう</div>', unsafe_allow_html=True)
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)

    # 金額選択（HTML ボタン + Streamlit連携）
    st.markdown('<p style="font-size:12px;font-weight:600;color:rgba(240,240,245,0.6);text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;">応援する金額を選んでください</p>', unsafe_allow_html=True)

    # セッションステートで選択金額を管理
    if "selected_amount" not in st.session_state:
        st.session_state.selected_amount = None

    # 金額ボタン（行ごとに columns を作ることで、モバイルでスタックされても順序が崩れないようにする）
    for i in range(0, len(PRESET_AMOUNTS), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j < len(PRESET_AMOUNTS):
                amount = PRESET_AMOUNTS[i + j]
                with cols[j]:
                    if st.button(f"¥{amount:,}", key=f"amt_{amount}", use_container_width=True):
                        st.session_state.selected_amount = amount
                        st.session_state.custom_mode = False

    # 任意の金額
    if "custom_mode" not in st.session_state:
        st.session_state.custom_mode = False

    if st.button("💰 任意の金額を入力", key="custom_btn", use_container_width=True):
        st.session_state.custom_mode = True
        st.session_state.selected_amount = None

    if st.session_state.custom_mode:
        custom = st.number_input("金額（100円〜）", min_value=100, max_value=1000000, step=100, key="custom_val")
        st.session_state.selected_amount = custom

    # 選択中の金額表示
    if st.session_state.selected_amount:
        st.markdown(f'<div class="selected-amount-display">¥{st.session_state.selected_amount:,}</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="selected-amount-display">&nbsp;</div>', unsafe_allow_html=True)

    # 応援メッセージ入力
    st.markdown('<p style="font-size:12px;font-weight:600;color:rgba(240,240,245,0.6);text-transform:uppercase;letter-spacing:1px;margin-top:24px;margin-bottom:12px;">応援メッセージ（140文字まで）</p>', unsafe_allow_html=True)
    support_message = st.text_area("応援のメッセージを添えてみませんか？", max_chars=140, placeholder="素敵なパフォーマンスでした！応援しています！", label_visibility="collapsed")


    # 応援するボタン
    if st.button("🔥 応援する！", key="support_btn", use_container_width=True):
        amount = st.session_state.selected_amount
        if not amount:
            st.warning("金額を選んでください")
        else:
            try:
                # Stripe Checkout Session 作成
                checkout_params = {
                    "payment_method_types": ["card"],
                    "line_items": [{
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
                    "mode": "payment",
                    "success_url": f"{BASE_URL}?page=success&s_name={urllib.parse.quote(display_name)}&s_amt={amount}&session_id={{CHECKOUT_SESSION_ID}}",
                    "cancel_url": f"{BASE_URL}?page=cancel",
                    "metadata": {
                        "user_id": support_user if not connect_acct else connect_acct,
                        "display_name": display_name,
                        "support_message": support_message,
                    },
                }

                # Stripe Connect: ダイレクト支払い（売り手が直接回収するモデル）
                if connect_acct:
                    fee = int(amount * PLATFORM_FEE_PERCENT / 100)
                    checkout_params["payment_intent_data"] = {
                        "application_fee_amount": fee,
                    }
                    # 連結アカウント（クリエイター）の権限でセッションを作成
                    session = stripe.checkout.Session.create(**checkout_params, stripe_account=connect_acct)
                else:
                    # 通常決済（テスト用またはプラットフォーム受取用）
                    session = stripe.checkout.Session.create(**checkout_params)

                # JavaScriptでStripe決済ページへリダイレクト
                components.html(
                    f'<script>window.top.location.href = "{session.url}";</script>',
                    height=0,
                )
                st.link_button("💳 自動で遷移しない場合はこちら", session.url, use_container_width=True)
            except Exception as e:
                st.error(f"決済エラー: {e}")

    st.markdown('<p style="text-align:center;margin-top:14px;font-size:11px;color:rgba(240,240,245,0.35);line-height:1.6;">クレジットカードで安全にお支払い（Stripe）<br>応援額の90%がクリエイターに届きます</p>', unsafe_allow_html=True)
    # フッター (応援ページ)
    st.markdown("""
    <div class="oshi-footer animate-fade-in delay-3" style="margin-top:40px;">Powered by <a href="?page=dashboard">OshiPay</a></div>
    <div class="legal-links animate-fade-in delay-3" style="margin-top:20px;">
        <a href="#">利用規約</a>
        <a href="#">プライバシーポリシー</a>
        <a href="#">特定商取引法に基づく表記</a>
    </div>
    """, unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 ダッシュボード（デフォルト）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
else:
    # ロゴ
    st.markdown('<div class="oshi-logo animate-fade-in"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="oshi-tagline animate-fade-in delay-1">応援を、もっとシンプルに。</div>', unsafe_allow_html=True)

    st.markdown('<div class="section-title">QRコードを発行</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">あなた専用のQRコードを作成して<br>応援を受け取りましょう</div>', unsafe_allow_html=True)

    # ── Stripe Connect の状態チェック ──
    acct_id = connect_acct or st.session_state.get("connect_acct_id", "")
    acct_ready = False
    refresh_needed = params.get("refresh", "") == "1"

    if acct_id:
        status = check_account_status(acct_id)
        if status and status["details_submitted"]:
            acct_ready = True
            st.session_state["connect_acct_id"] = acct_id
            st.markdown('<div style="text-align:center;margin:12px 0;"><span style="font-size:14px;color:#10b981;">✅ Stripeアカウント連携済み</span></div>', unsafe_allow_html=True)
        elif refresh_needed:
            # オンボーディング未完了 → 再度リンク生成
            try:
                link_url = create_account_link(acct_id)
                components.html(
                    f'<script>window.top.location.href = "{link_url}";</script>',
                    height=0,
                )
                st.info("Stripeオンボーディングを続けてください...")
                st.link_button("🔗 Stripe登録ページへ", link_url, use_container_width=True)
            except Exception as e:
                st.error(f"エラー: {e}")
        else:
            st.markdown('<div style="text-align:center;margin:12px 0;"><span style="font-size:14px;color:#fbbf24;">⏳ Stripeアカウント設定中...</span></div>', unsafe_allow_html=True)
            try:
                link_url = create_account_link(acct_id)
                st.link_button("🔗 Stripe登録を完了する", link_url, use_container_width=True)
            except Exception as e:
                st.error(f"エラー: {e}")

    # ── ステップ1: Stripeアカウント連携 ──
    if not acct_id:
        st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
        st.markdown('<p style="font-size:13px;color:rgba(240,240,245,0.6);text-align:center;line-height:1.8;">応援を受け取るには<br>Stripeアカウントの連携が必要です</p>', unsafe_allow_html=True)

        if st.button("🔗 Stripeアカウントを連携する", use_container_width=True):
            try:
                new_acct_id = create_connect_account()
                st.session_state["connect_acct_id"] = new_acct_id
                link_url = create_account_link(new_acct_id)
                components.html(
                    f'<script>window.top.location.href = "{link_url}";</script>',
                    height=0,
                )
                st.link_button("🔗 自動で遷移しない場合はこちら", link_url, use_container_width=True)
            except Exception as e:
                st.error(f"エラー: {e}")

        st.markdown('<p style="text-align:center;font-size:11px;color:rgba(240,240,245,0.3);margin-top:8px;line-height:1.8;">本人確認・振込先の登録を行います（無料）<br>🔒 個人情報・口座情報はStripeが安全に管理し、運営側には開示されません<br>応援額の90%があなたに支払われます（10%はシステム利用料）</p>', unsafe_allow_html=True)

    # ── ステップ2: QRコード生成（Stripe連携済みの場合のみ） ──
    if acct_ready:
        st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)

        creator_name = st.text_input("表示名", placeholder="例: ストリートミュージシャン太郎", max_chars=50)
        user_id = st.text_input("ユーザーID（任意）", placeholder="自動生成されます", max_chars=20)

        # アイコン選択
        st.markdown('<p style="font-size:12px;font-weight:600;color:rgba(240,240,245,0.6);text-transform:uppercase;letter-spacing:1px;margin-bottom:4px;margin-top:8px;">アイコンを選択</p>', unsafe_allow_html=True)

        icon_cols = st.columns(6)
        icon_list = list(ICON_OPTIONS.keys())
        if "selected_icon" not in st.session_state:
            st.session_state.selected_icon = "🎤"

        for i, emoji in enumerate(icon_list):
            with icon_cols[i % 6]:
                label = ICON_OPTIONS[emoji]
                if st.button(
                    emoji,
                    key=f"icon_{i}",
                    help=label,
                    use_container_width=True,
                ):
                    st.session_state.selected_icon = emoji

        # 選択中のアイコン表示
        st.markdown(f'<div style="text-align:center;margin:8px 0;"><span style="font-size:40px;">{st.session_state.selected_icon}</span><br><span style="font-size:12px;color:rgba(240,240,245,0.5);">{ICON_OPTIONS[st.session_state.selected_icon]}</span></div>', unsafe_allow_html=True)

        if st.button("✨ QRコードを生成", use_container_width=True):
            if not creator_name:
                st.warning("表示名を入力してください")
            else:
                if not user_id:
                    user_id = str(uuid.uuid4())[:8]

                selected_icon = st.session_state.selected_icon
                support_url = f"{BASE_URL}?page=support&user={user_id}&name={creator_name}&icon={selected_icon}&acct={acct_id}"

                qr_b64, qr_bytes = generate_qr_data(support_url)
                
                # 状態を保存
                st.session_state.last_qr = {
                    "b64": qr_b64,
                    "bytes": qr_bytes,
                    "url": support_url,
                    "user_id": user_id
                }

        # 生成済みQRコードがある場合は表示
        if "last_qr" in st.session_state:
            res = st.session_state.last_qr
            st.markdown(f"""
            <div style="text-align:center;margin:24px 0;animation:slideUp 0.5s ease both;">
                <div class="qr-frame">
                    <img src="data:image/png;base64,{res['b64']}" alt="QRコード" />
                </div>
                <p style="font-size:11px;color:rgba(240,240,245,0.35);text-align:center;word-break:break-all;max-width:300px;margin:16px auto;line-height:1.5;">{res['url']}</p>
            </div>
            """, unsafe_allow_html=True)

            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    "💾 QR保存",
                    data=res['bytes'],
                    file_name=f"oshiPay-qr-{res['user_id']}.png",
                    mime="image/png",
                    use_container_width=True,
                )
            with col2:
                if st.button("📋 URLコピー", use_container_width=True):
                    st.code(res['url'], language=None)
                    st.toast("URLをコピーできる状態にしました！")

    st.markdown('<div class="oshi-footer animate-fade-in delay-3">Powered by <a href="#">OshiPay</a></div>', unsafe_allow_html=True)