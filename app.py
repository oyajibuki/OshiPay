import os
import io
import base64
import uuid

import streamlit as st
import streamlit.components.v1 as components
import stripe
import qrcode
import urllib.parse

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
PRESET_AMOUNTS = [100, 500, 1000, 10000, 30000]

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


def get_qr_bytes(data: str) -> bytes:
    """QRコードをバイト列で返す（ダウンロード用）"""
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
    return buffer.getvalue()


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

/* ── ランディングページ専用 ── */
.lp-container {
    padding: 20px 0 60px;
    text-align: center;
}
.lp-hero {
    margin-bottom: 40px;
}
.lp-title {
    font-size: 3.5rem;
    font-weight: 800;
    margin-bottom: 1rem;
    background: linear-gradient(135deg, #fff 0%, rgba(255,255,255,0.7) 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
}
.lp-tagline {
    font-size: 1.2rem;
    color: rgba(240,240,245,0.7);
    margin-bottom: 2rem;
    line-height: 1.6;
}
.lp-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 20px;
    margin: 40px 0;
}
.lp-card {
    background: rgba(255,255,255,0.03);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 24px;
    padding: 30px;
    text-align: left;
    transition: all 0.3s ease;
}
.lp-card:hover {
    background: rgba(255,255,255,0.05);
    transform: translateY(-5px);
}
.lp-card-icon {
    font-size: 32px;
    margin-bottom: 16px;
}
.lp-card-title {
    font-size: 18px;
    font-weight: 700;
    margin-bottom: 8px;
    color: #fff;
}
.lp-card-text {
    font-size: 14px;
    color: rgba(240,240,245,0.6);
    line-height: 1.6;
}
.lp-step {
    font-size: 13px;
    color: #8b5cf6;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1px;
    margin-bottom: 20px;
    display: block;
}
.legal-links {
    display: flex;
    justify-content: center;
    gap: 20px;
    margin-top: 40px;
    font-size: 11px;
    color: rgba(240,240,245,0.3);
}
.legal-links a {
    color: inherit;
    text-decoration: none;
}
.legal-links a:hover {
    color: #8b5cf6;
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
# 何もパラメータがない場合は lp をデフォルトにする
page = params.get("page", "lp") if not params else params.get("page", "lp")

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

    # Xシェア文言のカスタマイズ
    if success_name and success_amount:
        share_text = f"{success_name}さんに{success_amount}円 応援したよ！\nhttps://oshipay.streamlit.app/ \n#OshiPay"
    else:
        share_text = "OshiPay で応援しました！🔥 #OshiPay"
    
    encoded_text = urllib.parse.quote(share_text)
    st.link_button("𝕏 でシェア", f"https://twitter.com/intent/tweet?text={encoded_text}", use_container_width=True)

    st.markdown('<div class="oshi-footer animate-fade-in delay-3">Powered by <a href="?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 🔥 ランディングページ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
elif page == "lp":
    st.markdown("""
    <div class="lp-container animate-fade-in">
        <div class="lp-hero">
            <div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>
            <h1 class="lp-title">その感動、今すぐカタチに。</h1>
            <p class="lp-tagline">
                アカウントを作ってQRコードを表示するだけ。<br>
                あなたの活動を応援したい気持ちを、ダイレクトに受け取れます。
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 「はじめる」ボタン
    if st.button("🚀 今すぐはじめる（無料）", use_container_width=True, key="lp_start"):
        st.query_params.page = "dashboard"
        st.rerun()

    st.markdown("""
    <div class="lp-container animate-fade-in delay-1">
        <span class="lp-step">Use Cases</span>
        <h2 style="font-size:24px; margin-bottom:30px;">いろんなシーンで応援を</h2>
        
        <div class="lp-grid">
            <div class="lp-card">
                <div class="lp-card-icon">🎤</div>
                <div class="lp-card-title">ストリートパフォーマンス</div>
                <div class="lp-card-text">QRコードを貼るだけで、聴衆から直接応援が届きます。小銭を持ち歩かない時代に最適です。</div>
            </div>
            <div class="lp-card">
                <div class="lp-card-icon">☕</div>
                <div class="lp-card-title">カフェ・飲食店</div>
                <div class="lp-card-text">素晴らしいサービスへの感謝をチップとして。店員さん個人への応援をスマートに実現。</div>
            </div>
            <div class="lp-card">
                <div class="lp-card-icon">🧹</div>
                <div class="lp-card-title">施設の清掃・維持</div>
                <div class="lp-card-text">いつも綺麗な環境への感謝を。トイレの清掃員さんなど、影で支える人へお礼を。</div>
            </div>
            <div class="lp-card">
                <div class="lp-card-icon">🔥</div>
                <div class="lp-card-title">あらゆるプロジェクト</div>
                <div class="lp-card-text">情熱を持って活動するすべての人に。登録不要、最短1分で投げ銭の受付を開始。</div>
            </div>
        </div>

        <div class="oshi-divider"></div>
        
        <div style="margin-top:40px;">
            <p style="font-size:14px; color:rgba(240,240,245,0.6); margin-bottom:20px;">
                安心のStripe決済を利用。応援額の90%があなたの手元に。
            </p>
        </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("🔥 応援を受け取りたい方はこちら（無料登録）", use_container_width=True, key="lp_start_bottom"):
        st.query_params.page = "dashboard"
        st.rerun()

    st.markdown("""
    <div class="legal-links animate-fade-in delay-3">
        <a href="#">利用規約</a>
        <a href="#">プライバシーポリシー</a>
        <a href="#">特定商取引法に基づく表記</a>
    </div>
    <div class="oshi-footer animate-fade-in delay-3">© 2026 OshiPay ― 応援を、もっとシンプルに。</div>
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

    # 金額ボタン（Streamlitのcolumns）
    cols = st.columns(3)
    for i, amount in enumerate(PRESET_AMOUNTS):
        col = cols[i % 3]
        with col:
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
                    "success_url": f"{BASE_URL}?page=success&s_name={urllib.parse.quote(display_name)}&s_amt={amount}",
                    "cancel_url": f"{BASE_URL}?page=cancel",
                    "metadata": {
                        "user_id": support_user,
                        "display_name": display_name,
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
    st.markdown('<div class="oshi-footer animate-fade-in delay-3">Powered by <a href="?page=dashboard">OshiPay</a> ― 応援を、もっとシンプルに。</div>', unsafe_allow_html=True)


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

                qr_b64 = generate_qr_base64(support_url)
                qr_bytes = get_qr_bytes(support_url)

                st.markdown(f"""
                <div style="text-align:center;margin:24px 0;animation:slideUp 0.5s ease both;">
                    <div class="qr-frame">
                        <img src="data:image/png;base64,{qr_b64}" alt="QRコード" />
                    </div>
                    <p style="font-size:11px;color:rgba(240,240,245,0.35);text-align:center;word-break:break-all;max-width:300px;margin:16px auto;line-height:1.5;">{support_url}</p>
                </div>
                """, unsafe_allow_html=True)

                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(
                        "💾 QR保存",
                        data=qr_bytes,
                        file_name=f"oshiPay-qr-{user_id}.png",
                        mime="image/png",
                        use_container_width=True,
                    )
                with col2:
                    if st.button("📋 URLコピー", use_container_width=True):
                        st.code(support_url, language=None)

    st.markdown('<div class="oshi-footer animate-fade-in delay-3">Powered by <a href="#">OshiPay</a></div>', unsafe_allow_html=True)