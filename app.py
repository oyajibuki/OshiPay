import os
import io
import base64
import uuid
import random
import datetime
import json
from governance import (
    validate_password, validate_username, validate_bio, validate_sns_url,
    normalize_sns_url, check_slug_locked,
)

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
    page_title="OshiPay",
    page_icon="https://oyajibuki.github.io/OshiPay/favicon.png?v=2",
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
BASE_URL = os.environ.get("APP_URL", "https://oshipay.streamlit.app").rstrip('/') + '/'

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ヘルパー関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def read_html_file(file_path):
    """HTMLファイルをディスクから読み込む"""
    try:
        cur_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(cur_dir, file_path)
        if os.path.exists(full_path):
            with open(full_path, "r", encoding="utf-8") as f:
                return f.read()
        return f"File not found: {file_path}"
    except Exception as e:
        return f"Error reading file {file_path}: {e}"

def inject_top_scroll_script(html_content):
    """ページ上部へのスクロールを強制するJSを注入"""
    script = """
    <script>
    if (window.top !== window.self) {
        window.scrollTo(0, 0);
    }
    document.addEventListener("DOMContentLoaded", function() {
        window.scrollTo(0, 0);
    });
    </script>
    """
    if "</body>" in html_content:
        return html_content.replace("</body>", f"{script}</body>")
    return html_content + script

def create_connect_account():
    account = stripe.Account.create(
        type="express", country="JP",
        capabilities={"card_payments": {"requested": True}, "transfers": {"requested": True}},
        business_type="individual",
        business_profile={
            "mcc": "7922", 
            "product_description": "OshiPay - 投げ銭サービス",
            "url": BASE_URL
        },
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
        subject = f"{creator_name}さんに応援が届きました！ (OshiPay)"
        body = f"{creator_name}さん\n\nOshiPayを通じて応援が届きました！\n\n💰 応援金額: {amount:,}円\n💬 メッセージ:\n{message if message else '（なし）'}\n\n--\nOshiPay\n{BASE_URL}"
        msg = MIMEText(body); msg["Subject"] = subject; msg["From"] = smtp_user; msg["To"] = to_email; msg["Date"] = formatdate(localtime=True)
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls(); server.login(smtp_user, smtp_pass); server.send_message(msg)
        return True, "送信成功"
    except Exception as e: return False, str(e)

def check_account_status(account_id):
    try:
        account = stripe.Account.retrieve(account_id)
        return {"charges_enabled": account.charges_enabled, "payouts_enabled": account.payouts_enabled, "details_submitted": account.details_submitted}
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
    buf = io.BytesIO(); qr_img.save(buf, format="PNG"); qr_bytes = buf.getvalue(); b64 = base64.b64encode(buf.getvalue()).decode()
    return b64, qr_bytes

def get_font(size):
    font_path = "assets/NotoSansJP-Bold.ttf"
    if not os.path.exists(font_path):
        os.makedirs("assets", exist_ok=True)
        # ── 新アーキテクチャ: 自動転送 ──
        # GitHub Pages (docsフォルダ) のURLを指定
        NEW_LP_URL = "https://oyajibuki.github.io/OshiPay/"
        url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP-Bold.ttf"
        try:
            import urllib.request
            urllib.request.urlretrieve(url, font_path)
        except Exception:
            from PIL import ImageFont
            return ImageFont.load_default()
    try:
        from PIL import ImageFont
        return ImageFont.truetype(font_path, size)
    except Exception:
        from PIL import ImageFont
        return ImageFont.load_default()

def generate_coin_image(creator_name, amount, date_str, support_id, rank=1, reply_tier="none"):
    """
    3軸スコアリングコインバッジ
    rank       : クリエイターへの何番目の応援か（1始まり）
    amount     : 応援金額（円）
    reply_tier : "none" | "emoji" | "text"

    ■ スコア計算
      rank_pts   : #1-9=3, #10-99=2, #100-999=1, #1000+=0
      amount_pts : 100,000+=3, 10,000+=2, 1,000+=1, <1,000=0
      score = rank_pts + amount_pts  (0〜6)

    ■ 本体色（score基準）
      6=LEGEND(紫), 5=DIAMOND(青), 4=GOLD(金), 2-3=SILVER(銀), 0-1=BRONZE(銅)

    ■ ふち色（reply_tier基準）
      text=ダイアモンドふち, emoji=ゴールドふち, none=ふちなし
    """
    from PIL import Image, ImageDraw
    size = 500
    img = Image.new("RGB", (size, size), "#08080f")
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # ── スコア計算 ──
    rank_pts   = 3 if rank <= 9   else (2 if rank <= 99   else (1 if rank <= 999 else 0))
    amount_pts = 3 if amount >= 100000 else (2 if amount >= 10000 else (1 if amount >= 1000 else 0))
    score = rank_pts + amount_pts  # 0〜6

    # ── 本体色（スコア基準）──
    if score == 6:
        # LEGEND: 深黒ボディ + レインボーリム（金テキスト）
        b_face="#1a0530"; b_hi="#3d0f7a"; b_dark="#0d0320"; b_text="#ffd700"; tier_label="LEGEND"
    elif score == 5:
        b_face="#a8d4ec"; b_hi="#e4f4fc"; b_dark="#4a8aaa"; b_text="#0d2030"; tier_label="DIAMOND"
    elif score >= 4:
        b_face="#ffd700"; b_hi="#fff8a0"; b_dark="#a07800"; b_text="#3d2800"; tier_label="GOLD"
    elif score >= 2:
        b_face="#c0c0c0"; b_hi="#e8e8e8"; b_dark="#606060"; b_text="#1a1a1a"; tier_label="SILVER"
    else:
        b_face="#6B3A12"; b_hi="#C87830"; b_dark="#3C1A06"; b_text="#f0c080"; tier_label="BRONZE"

    # ── ふち色（返信ステータス基準）──
    if reply_tier == "text":
        r_outer="#4a8aaa"; r_rim="#e4f4fc"   # ダイアモンドふち
    elif reply_tier == "emoji":
        r_outer="#9a7000"; r_rim="#c8a200"   # ゴールドふち
    else:
        r_outer="#505050"; r_rim="#909090"   # シルバーふち（返信なし）

    # ── 同心円コイン描画 ──
    draw.ellipse([cx-228, cy-228, cx+228, cy+228], fill="#08080f")  # bg shadow

    if tier_label == "LEGEND":
        # レインボーリム: 7色の扇形で360°を埋める
        rainbow_colors = [
            "#ff0040", "#ff6600", "#ffd700",
            "#00cc44", "#0099ff", "#7744ff", "#ff44cc"
        ]
        n = len(rainbow_colors)
        seg = 360.0 / n
        for i, rc in enumerate(rainbow_colors):
            draw.pieslice(
                [cx-220, cy-220, cx+220, cy+220],
                start=i * seg - 1, end=(i + 1) * seg + 1,
                fill=rc
            )
        draw.ellipse([cx-193, cy-193, cx+193, cy+193], fill=b_dark)  # 中央を本体暗で覆う
    else:
        draw.ellipse([cx-220, cy-220, cx+220, cy+220], fill=r_outer)  # ふち外
        draw.ellipse([cx-207, cy-207, cx+207, cy+207], fill=r_rim)    # ふち内
        draw.ellipse([cx-193, cy-193, cx+193, cy+193], fill=b_dark)   # 本体暗

    draw.ellipse([cx-180, cy-180, cx+180, cy+180], fill=b_face)     # 本体
    draw.ellipse([cx-166, cy-166, cx+166, cy+166], fill=b_hi)       # ハイライト
    draw.ellipse([cx-152, cy-152, cx+152, cy+152], fill=b_face)     # インナー面

    font_label = get_font(15)
    font_rank  = get_font(64)   # ランク番号を最大に
    font_amt   = get_font(34)
    font_name  = get_font(20)
    font_small = get_font(13)

    # ティアラベルバッジ（上部）
    try:
        draw.rounded_rectangle([cx-60, cy-148, cx+60, cy-120], radius=8, fill=b_dark)
    except AttributeError:
        draw.rectangle([cx-60, cy-148, cx+60, cy-120], fill=b_dark)
    draw.text((cx, cy-134), tier_label, font=font_label, fill=b_hi, anchor="mm")

    # ランク番号（最重要・最大表示）
    rank_str = f"#{rank:03d}" if rank <= 999 else f"#{rank}"
    draw.text((cx, cy-50), rank_str, font=font_rank, fill=b_text, anchor="mm")

    # 金額
    draw.text((cx, cy+30), f"{amount:,}", font=font_amt, fill=b_text, anchor="mm")

    # クリエイター名
    cn = creator_name if len(creator_name) <= 14 else creator_name[:13] + "\u2026"
    draw.text((cx, cy+76), cn, font=font_name, fill=b_text, anchor="mm")

    # スコア内訳（小さく）
    score_detail = f"rank+{rank_pts} amt+{amount_pts} = {score}pt"
    draw.text((cx, cy+108), score_detail, font=font_small, fill=b_dark, anchor="mm")

    # 日付
    draw.text((cx, cy+128), date_str, font=font_small, fill=b_dark, anchor="mm")

    # ID
    draw.text((cx, cy+146), f"ID: {support_id[:8]}", font=font_small, fill=b_dark, anchor="mm")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Supabase 永続化
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from supabase import create_client, Client

REPLY_EMOJIS = ["👍", "❤️", "🙏", "🎉", "😊", "🔥", "✨", "🌟"]

@st.cache_resource
def get_db() -> Client:
    """Supabaseクライアントをシングルトンで返す"""
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )

def add_support(support_id: str, creator_acct: str, creator_name: str, amount: int, message: str, supporter_id: str = None) -> None:
    """応援記録を追加（support_idのUNIQUE制約で重複は自動無視）"""
    try:
        # このクリエイターへの何番目の応援かを計算
        try:
            rank_resp = get_db().table("supports").select("id").eq("creator_acct", creator_acct).execute()
            creator_rank = len(rank_resp.data) + 1
        except Exception:
            creator_rank = 1
        data = {
            "support_id": support_id,
            "creator_acct": creator_acct,
            "creator_name": creator_name,
            "amount": amount,
            "message": message,
            "creator_rank": creator_rank,
        }
        if supporter_id:
            data["supporter_id"] = supporter_id
        get_db().table("supports").insert(data).execute()
    except Exception:
        pass  # unique制約違反（ページリロード時の重複）は無視

def get_support(support_id: str) -> dict | None:
    """support_id で1件取得"""
    try:
        resp = get_db().table("supports").select("*").eq("support_id", support_id).execute()
        return resp.data[0] if resp.data else None
    except Exception:
        return None

import hashlib

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_creator(acct_id: str, password: str) -> bool:
    try:
        resp = get_db().table("creators").select("*").eq("acct_id", acct_id).execute()
        if not resp.data: return False
        return resp.data[0]["password_hash"] == hash_password(password)
    except Exception: return False

def register_creator(acct_id: str, password: str) -> bool:
    try:
        get_db().table("creators").insert({"acct_id": acct_id, "password_hash": hash_password(password)}).execute()
        return True
    except Exception: return False

def set_reply(support_id: str, emoji: str, text: str) -> bool:
    """クリエイターの返信を保存"""
    resp = get_db().table("supports").update({
        "reply_emoji": emoji,
        "reply_text": text,
        "replied_at": datetime.datetime.utcnow().isoformat(),
    }).eq("support_id", support_id).execute()
    return bool(resp.data)

def get_supports_for_creator(creator_acct: str) -> list:
    """クリエイターの応援一覧を新着順で返す"""
    resp = (
        get_db().table("supports")
        .select("*")
        .eq("creator_acct", creator_acct)
        .order("created_at", desc=True)
        .execute()
    )
    return resp.data or []

def load_supports() -> list:
    """テストページ用: 全件取得（新着順）"""
    resp = get_db().table("supports").select("*").order("created_at", desc=True).execute()
    return resp.data or []

def delete_all_supports() -> None:
    """テストページ用: 全データ削除"""
    get_db().table("supports").delete().neq("support_id", "").execute()

def get_monthly_ranking() -> list:
    """月間ランキング用: 当月のsupportsを全取得"""
    now = datetime.datetime.now(datetime.timezone.utc)
    start = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc).isoformat()
    resp = get_db().table("supports").select("*").gte("created_at", start).execute()
    return resp.data or []

def get_all_time_ranking() -> list:
    """全期間ランキング用: 全supportsを取得"""
    resp = get_db().table("supports").select("*").execute()
    return resp.data or []

def get_supporters_map(supporter_ids: list) -> dict:
    """supporter_id リストから {supporter_id: display_name} マップを返す"""
    if not supporter_ids:
        return {}
    resp = (
        get_db().table("supporters")
        .select("supporter_id,display_name")
        .in_("supporter_id", supporter_ids)
        .execute()
    )
    return {r["supporter_id"]: r["display_name"] for r in (resp.data or [])}

def get_tier_badge(amount: int) -> tuple:
    """金額からコインティアバッジ情報を返す (label, color, bg_color)"""
    if amount >= 100000: return ("🌈 LEGEND",  "#ffd700", "rgba(26,5,48,0.9)")
    if amount >= 10000:  return ("💎 DIAMOND", "#a8d4ec", "rgba(168,212,236,0.2)")
    if amount >= 1000:   return ("🥇 GOLD",    "#fbbf24", "rgba(245,158,11,0.2)")
    if amount >= 500:    return ("🥈 SILVER",  "#94a3b8", "rgba(148,163,184,0.15)")
    return                      ("🟤 BRONZE",  "#A06830", "rgba(123,74,30,0.2)")

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# スタイル & UIパーツ
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&family=Noto+Sans+JP:wght@400;700;900&display=swap');
#MainMenu, header, footer, .stDeployButton {visibility: hidden; display: none !important;}
[data-testid="stToolbar"], [data-testid="stDecoration"], [data-testid="stHeader"] {display: none !important;}
.stApp { background: #08080f !important; font-family: 'Inter', 'Noto Sans JP', sans-serif !important; }
.stMainBlockContainer, .block-container { position: relative; z-index: 1; padding-top: 2rem !important; }
.oshi-logo { text-align: center; margin-bottom: 6px; }
.oshi-logo .icon { font-size: 28px; }
.oshi-logo .text { font-size: 22px; font-weight: 800; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
.oshi-tagline { text-align: center; font-size: 13px; color: rgba(240,240,245,0.35); margin-bottom: 28px; }
.section-title { font-size: 20px; font-weight: 700; text-align: center; color: #f0f0f5; margin-bottom: 6px; }
.section-subtitle { font-size: 13px; color: rgba(240,240,245,0.6); text-align: center; margin-bottom: 24px; }
.support-avatar { width: 72px; height: 72px; border-radius: 50%; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); display: flex; align-items: center; justify-content: center; font-size: 32px; margin: 0 auto 14px; box-shadow: 0 0 30px rgba(139,92,246,0.3); }
.support-name { font-size: 22px; font-weight: 800; text-align: center; color: #f0f0f5; }
.support-label { font-size: 13px; color: rgba(240,240,245,0.6); text-align: center; margin-bottom: 20px; }
.selected-amount-display { text-align: center; font-size: 36px; font-weight: 900; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 10px 0; }
.stButton > button:not([kind="secondary"]) { width: 100%; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316) !important; color: white !important; border: none !important; border-radius: 9999px !important; padding: 16px !important; font-weight: 700 !important; }
.stButton > button[kind="secondary"] { background: transparent !important; border: 1px solid rgba(250,250,250,0.25) !important; color: rgba(250,250,250,0.85) !important; border-radius: 0.5rem !important; padding: 0.45rem 1rem !important; }
.oshi-footer { text-align: center; margin-top: 24px; font-size: 11px; color: rgba(240,240,245,0.35); }
.oshi-footer a { color: #8b5cf6; text-decoration: none; }
.legal-links a { font-size: 10px; color: rgba(240,240,245,0.3); text-decoration: none; margin: 0 5px; }
.oshi-divider { height: 1px; background: rgba(255,255,255,0.08); margin: 20px 0; }
.qr-frame { background: white; padding: 16px; border-radius: 20px; display: inline-block; margin: 0 auto; }
</style>
<script>
// target="_top" リンクをStreamlitのiframe越しに確実に動かす
document.addEventListener('click', function(e) {
    var a = e.target.closest('a[target="_top"]');
    if (a && a.href) { e.preventDefault(); window.top.location.href = a.href; }
}, true);
</script>
""", unsafe_allow_html=True)

# ── ルーティング ──
params = st.query_params
page = params.get("page", "lp")

# LocalStorage保存用の簡易JS
def save_account_id_js(acct_id):
    if acct_id:
        st.components.v1.html(f"""
        <script>localStorage.setItem('oshipay_acct', '{acct_id}');</script>
        """, height=0)

if page == "dashboard":
    save_account_id_js(params.get("acct"))

# 法務ページ用の幅調整
IS_LEGAL_PAGE = page in ["terms", "privacy", "legal"]

if page == "lp":
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: none !important; padding: 0 !important; margin: 0 !important; width: 100% !important; }</style>", unsafe_allow_html=True)
elif IS_LEGAL_PAGE:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 800px !important; margin: 0 auto !important; }</style>", unsafe_allow_html=True)
elif page in ["reply_view", "ranking", "profile"]:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 700px !important; margin: 0 auto !important; }</style>", unsafe_allow_html=True)
else:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 460px !important; margin: 0 auto !important; }</style>", unsafe_allow_html=True)

# ── 外部HTMLファイルの表示 ──
LEGAL_MAP = {
    "terms": "role/index.html",
    "privacy": "role/index2.html",
    "legal": "role/index3v2.html"
}

if page in LEGAL_MAP:
    html_content = read_html_file(LEGAL_MAP[page])
    # スクロール位置リセット用JSを注入
    html_content = inject_top_scroll_script(html_content)
    components.html(html_content, height=900, scrolling=True)
    st.stop()

# ── ランディングページ ──
if page == "lp":
    # ── 新アーキテクチャ: 自動転送 ──
    NEW_LP_URL = "https://oyajibuki.github.io/OshiPay/"
    
    st.markdown(f"""
        <div style="text-align: center; padding: 50px; font-family: sans-serif;">
            <h2 style="color: white;">公式サイトへ移動しています...</h2>
            <p style="color: rgba(255,255,255,0.6);">自動的に移動しない場合は、<a href="{NEW_LP_URL}" style="color: #8b5cf6;">こちら</a>をクリックしてください。</p>
        </div>
    """, unsafe_allow_html=True)
    
    components.html(f"""
        <script>
            window.top.location.href = "{NEW_LP_URL}";
        </script>
    """, height=0)
    st.stop()

# ── 成功ページ ──
if page == "success":
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:80px;margin-bottom:20px;">🎉</div><div class="section-title">応援完了！</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">ありがとうございます！🙏</div>', unsafe_allow_html=True)

    s_name = params.get("s_name", "")
    s_amt_str = params.get("s_amt", "0")
    s_acct = params.get("s_acct", "")
    s_msg = params.get("s_msg", "")
    s_sid = params.get("s_sid", "")
    s_sup_id   = params.get("s_sup_id", "")
    s_sup_name = params.get("s_sup_name", "")

    # ── 応援金額のパース ──
    try:
        s_amt = int(s_amt_str)
    except ValueError:
        s_amt = 0

    # ── 名前入力からの軽量サポーターレコード作成 ──
    if s_sup_id and s_sup_name:
        try:
            get_db().table("supporters").insert(
                {"supporter_id": s_sup_id, "display_name": s_sup_name}
            ).execute()
        except Exception:
            pass  # UNIQUE制約違反（リロード時の重複）は無視

    # ── 応援記録を Supabase に保存（冪等: s_sid があれば1回のみ） ──
    if s_sid and s_acct and s_amt > 0:
        add_support(s_sid, s_acct, s_name, s_amt, s_msg, s_sup_id)

    # ── support_id を localStorage の履歴に追記 ＋ 名前・IDを保存 ──
    if s_sid:
        _save_name_js = ""
        if s_sup_id and s_sup_name:
            _safe_sup_id   = s_sup_id.replace("'", "")
            _safe_sup_name = s_sup_name.replace("'", "").replace("\\", "")
            _save_name_js  = f"localStorage.setItem('oshipay_supporter_id', '{_safe_sup_id}'); localStorage.setItem('oshipay_display_name', '{_safe_sup_name}');"
        components.html(f"""
        <script>
        try {{
            var h = JSON.parse(localStorage.getItem('oshipay_history') || '[]');
            if (!h.includes('{s_sid}')) {{
                h.unshift('{s_sid}');
                if (h.length > 50) h = h.slice(0, 50);
                localStorage.setItem('oshipay_history', JSON.stringify(h));
            }}
            {_save_name_js}
        }} catch(e) {{}}
        </script>
        """, height=0)

    # ── 応援証明カード ──
    if s_sid:
        my_support_url = f"{BASE_URL}?page=my_support&sid={s_sid}"
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(139,92,246,0.15), rgba(236,72,153,0.1));
                    border: 1px solid rgba(139,92,246,0.35); border-radius: 16px;
                    padding: 20px; margin: 20px 0; text-align: center;">
            <div style="font-size: 28px; margin-bottom: 8px;">🏅</div>
            <div style="color: #f0f0f5; font-weight: 700; font-size: 15px; margin-bottom: 6px;">応援証明をブックマークしよう</div>
            <div style="font-size: 12px; color: rgba(240,240,245,0.65); margin-bottom: 14px;">
                クリエイターからの返信もここで確認できます
            </div>
            <a href="{my_support_url}" target="_top"
               style="display:inline-block; background: linear-gradient(135deg,#8b5cf6,#ec4899);
                      color:white; text-decoration:none; border-radius:9999px;
                      padding:10px 24px; font-weight:700; font-size:14px;">
                🎫 応援証明を見る
            </a>
        </div>
        """, unsafe_allow_html=True)

    # ── 応援メール送信 ──
    if s_acct and s_name and s_amt > 0:
        try:
            acct_info = stripe.Account.retrieve(s_acct)
            creator_email = acct_info.get("email", "")
            if creator_email:
                ok, err = send_support_email(creator_email, s_name, s_amt, s_msg)
                if not ok:
                    st.error(f"⚠️ 通知メールの送信に失敗しました。\nエラー内容: {err}")
        except Exception:
            pass  # メール失敗はサイレントに

    if s_sup_id:
        st.markdown(
            f'<div style="background:rgba(139,92,246,0.12);border:1px solid rgba(139,92,246,0.4);'
            f'border-radius:16px;padding:20px;margin:16px 0;text-align:center;">'
            f'<div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:6px;">あなたのサポーターID</div>'
            f'<div style="font-size:22px;font-weight:900;color:#c4b5fd;letter-spacing:0.05em;font-family:monospace;">{s_sup_id}</div>'
            f'<div style="font-size:11px;color:rgba(240,240,245,0.4);margin-top:8px;">このIDでアカウント登録するとコインが積み重なります</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div style="text-align:center;margin-bottom:16px;">'
            f'<a href="{BASE_URL}?page=supporter_dashboard" target="_top" '
            f'style="display:inline-block;font-size:13px;font-weight:700;color:#c4b5fd;'
            f'text-decoration:none;background:rgba(139,92,246,0.15);'
            f'border:1px solid rgba(139,92,246,0.4);border-radius:12px;padding:10px 20px;">'
            f'🦸 このIDでアカウント登録する</a></div>',
            unsafe_allow_html=True
        )
    portfolio_url = f"{BASE_URL}?page=portfolio&id={s_sup_id}" if s_sup_id else BASE_URL
    share_text = f"{s_name}にOshiPayで応援したよ！\n#OshiPay\n{portfolio_url}"
    st.link_button("𝕏 でシェア", f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}", use_container_width=True)
    st.markdown(f'<div style="text-align:center;margin-top:10px;"><a href="{BASE_URL}?page=my_history" target="_top" style="font-size:12px;color:rgba(240,240,245,0.4); text-decoration:underline;">（ブラウザ限定）簡易履歴を見る</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms" target="_top">利用規約</a><a href="{BASE_URL}?page=privacy" target="_top">プライバシーポリシー</a><a href="{BASE_URL}?page=legal" target="_top">特定商取引法</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 応援証明ページ（サポーター向け）──
if page == "my_support":
    s_sid = params.get("sid", "")
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏅 応援証明</div>', unsafe_allow_html=True)

    if not s_sid:
        st.error("応援IDが見つかりません。")
        st.stop()

    record = get_support(s_sid)
    if not record:
        st.warning("応援記録が見つかりません。決済直後の場合は数秒後に再読み込みしてください。")
        st.stop()

    # ── ランク & 返信ステータス判定 ──
    coin_rank   = record.get("creator_rank") or 1
    coin_amount = record.get("amount") or 0
    has_reply_text  = bool(record.get("reply_text"))
    has_reply_emoji = bool(record.get("reply_emoji"))

    if has_reply_text:
        reply_tier = "text";  rim_label = "GOLD RIM";   rim_color = "#ffd700"; status_text = "メッセージ返信あり 💬"
    elif has_reply_emoji:
        reply_tier = "emoji"; rim_label = "SILVER RIM"; rim_color = "#c0c0c0"; status_text = "スタンプ返信あり ✨"
    else:
        reply_tier = "none";  rim_label = "";            rim_color = "#555";    status_text = "返信待ち 🕐"

    # ── 3軸スコアリング（rank_pts + amount_pts → ティア）──
    rank_pts   = 3 if coin_rank <= 9   else (2 if coin_rank <= 99   else (1 if coin_rank <= 999 else 0))
    amount_pts = 3 if coin_amount >= 100000 else (2 if coin_amount >= 10000 else (1 if coin_amount >= 1000 else 0))
    score = rank_pts + amount_pts

    if score == 6:
        tier_label = "LEGEND";  tier_color = "#ffd700"   # レインボーコインなのでゴールド表示
    elif score == 5:
        tier_label = "DIAMOND"; tier_color = "#a8d4ec"
    elif score >= 4:
        tier_label = "GOLD";    tier_color = "#ffd700"
    elif score >= 2:
        tier_label = "SILVER";  tier_color = "#c0c0c0"
    else:
        tier_label = "BRONZE";  tier_color = "#A06830"

    rank_str     = f"#{coin_rank:03d}" if coin_rank <= 999 else f"#{coin_rank}"
    amt_disp     = f"{record['amount']:,}"
    created_disp = record["created_at"][:10]

    # rim_badge_htmlを事前計算（nested f-stringバグ回避）
    rim_badge_html = (
        f'<span style="background:#ffd70022; border:1px solid #ffd70099; color:#ffd700; '
        f'font-size:11px; font-weight:700; padding:3px 10px; border-radius:20px;">{rim_label}</span>'
    ) if rim_label else ''

    # コイン画像生成（3軸スコアリング）
    b64_card = generate_coin_image(
        record['creator_name'], record['amount'], created_disp, record['support_id'],
        rank=coin_rank, reply_tier=reply_tier
    )

    st.markdown(
        f'<div style="text-align:center; margin-bottom:20px;">'
        f'<img src="data:image/png;base64,{b64_card}" '
        f'style="width:260px; height:260px; border-radius:50%; box-shadow:0 8px 32px rgba(0,0,0,0.55);" /></div>',
        unsafe_allow_html=True,
    )

    st.download_button(
        label="📥 コインバッジを保存",
        data=base64.b64decode(b64_card),
        file_name=f"oshipay_coin_{record['support_id'][:8]}.png",
        mime="image/png",
        use_container_width=True,
    )

    # ── ステータスカード（内容は非表示・ステータスのみ）──
    card_html = (
        f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:20px;margin:16px 0;">'
        f'<div style="display:flex;align-items:center;gap:12px;">'
        f'<div style="width:44px;height:44px;border-radius:50%;background:linear-gradient(135deg,#8b5cf6,#ec4899,#f97316);display:flex;align-items:center;justify-content:center;font-size:20px;">🔥</div>'
        f'<div style="flex:1;">'
        f'<div style="color:#f0f0f5;font-weight:700;font-size:16px;">{record["creator_name"]}</div>'
        f'<div style="color:rgba(240,240,245,0.5);font-size:12px;">{created_disp} に応援</div>'
        f'</div>'
        f'<div style="font-size:22px;font-weight:900;background:linear-gradient(135deg,#8b5cf6,#ec4899,#f97316);-webkit-background-clip:text;-webkit-text-fill-color:transparent;">{amt_disp}</div>'
        f'</div>'
        f'<div style="margin-top:14px;display:flex;align-items:center;gap:8px;flex-wrap:wrap;">'
        f'<span style="background:{tier_color}22;border:1px solid {tier_color}99;color:{tier_color};font-size:11px;font-weight:700;padding:3px 10px;border-radius:20px;">{tier_label} {rank_str}</span>'
        f'{rim_badge_html}'
        f'<span style="font-size:12px;color:rgba(240,240,245,0.6);">{status_text}</span>'
        f'</div>'
        f'<div style="margin-top:8px;font-size:11px;color:rgba(240,240,245,0.35);">応援ID: {record["support_id"][:8]}</div>'
        f'</div>'
    )
    st.markdown(card_html, unsafe_allow_html=True)

    if record.get("supporter_id"):
        st.markdown(
            f'<div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.2);'
            f'border-radius:12px;padding:14px;margin:12px 0;text-align:center;">'
            f'<div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:4px;">サポーターID</div>'
            f'<div style="font-size:16px;font-weight:700;color:#c4b5fd;font-family:monospace;">{record["supporter_id"]}</div>'
            f'<div style="font-size:10px;color:rgba(240,240,245,0.35);margin-top:4px;">'
            f'<a href="{BASE_URL}?page=supporter_dashboard" target="_top" style="color:#c4b5fd;text-decoration:underline;">'
            f'アカウント登録</a>するとコインが積み重なります</div>'
            f'</div>',
            unsafe_allow_html=True
        )
    st.markdown(f'<div style="text-align:center;margin-top:16px;"><a href="{BASE_URL}?page=coin_preview" target="_top" style="font-size:11px;color:rgba(240,240,245,0.3);text-decoration:underline;">🪙 コイン全色プレビューを見る</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="oshi-footer" style="margin-top:12px;">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms" target="_top">利用規約</a><a href="{BASE_URL}?page=privacy" target="_top">プライバシーポリシー</a><a href="{BASE_URL}?page=legal" target="_top">特定商取引法</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 返信ダッシュボードページ（クリエイター向け）──
if page == "reply_view":
    rv_acct = params.get("acct", "")
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">💌 返信ダッシュボード</div>', unsafe_allow_html=True)
    
    if st.session_state.get("reply_success_msg"):
        st.success(st.session_state["reply_success_msg"])
        del st.session_state["reply_success_msg"]

    if not rv_acct:
        st.markdown('<div class="section-subtitle">クリエーターIDとパスワードでログイン</div>', unsafe_allow_html=True)
        rv_lp_acct = st.text_input("クリエーターID", placeholder="acct_xxxxxxxxxxxxxxxxxx", key="rv_lp_acct")
        rv_lp_pass = st.text_input("パスワード", type="password", key="rv_lp_pass")
        if st.button("🔓 ログイン", type="primary", use_container_width=True):
            _rid = rv_lp_acct.strip()
            if _rid.startswith("acct_") and rv_lp_pass:
                if verify_creator(_rid, rv_lp_pass):
                    st.session_state["reply_auth"] = _rid
                    st.session_state["creator_auth"] = _rid
                    st.query_params["acct"] = _rid
                    st.rerun()
                else:
                    st.error("IDまたはパスワードが違います。")
            else:
                st.error("クリエーターIDとパスワードを入力してください。")
        st.stop()

    # ── パスワード認証 ──
    # rv_acct は URL の acct= パラメーターから取得済みのため、
    # verify_creator(rv_acct, pw) は「このURLのクリエイター専用」の認証になります。
    # ダッシュボードからのセッション引き継ぎ（パスワード2重入力を回避）
    if st.session_state.get("creator_auth") == rv_acct and st.session_state.get("reply_auth") != rv_acct:
        st.session_state["reply_auth"] = rv_acct
        st.rerun()
    if st.session_state.get("reply_auth") != rv_acct:
        st.markdown(f"""
        <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);
                    border-radius:14px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:12px;color:rgba(240,240,245,0.5);margin-bottom:4px;">ログイン対象のクリエイターID</div>
            <div style="font-family:monospace;font-size:14px;color:#c4b5fd;font-weight:700;">{rv_acct}</div>
            <div style="font-size:11px;color:rgba(240,240,245,0.35);margin-top:6px;">
                ※ このIDはURLに含まれています。別のIDのDLを開くには、そのクリエイターのURLから開いてください。
            </div>
        </div>
        """, unsafe_allow_html=True)
        rv_pass = st.text_input("パスワード", type="password", key="rv_pass")
        if st.button("🔓 ロックを解除", type="primary", use_container_width=True):
            if verify_creator(rv_acct, rv_pass):
                st.session_state["reply_auth"] = rv_acct
                st.rerun()
            else:
                st.error("パスワードが違います。")
        st.stop()

    # ── マイクロサイトへのリンク ──
    try:
        _cr_for_rv = get_db().table("creators").select("slug").eq("acct_id", rv_acct).maybe_single().execute()
        _rv_slug = (_cr_for_rv.data or {}).get("slug") or rv_acct
    except Exception:
        _rv_slug = rv_acct
    _microsite_url = f"https://oyajibuki.github.io/OshiPay/creator.html?id={_rv_slug}"
    _rv_col1, _rv_col2 = st.columns(2, vertical_alignment="top")
    _rv_col1.link_button("🌐 マイクロサイトを見る", _microsite_url, use_container_width=True, type="secondary")
    if _rv_col2.button("✏️ プロフィール編集", use_container_width=True, type="secondary"):
        st.session_state["creator_auth"] = rv_acct
        st.query_params["page"] = "dashboard"
        st.query_params["acct"] = rv_acct
        st.rerun()

    supports = get_supports_for_creator(rv_acct)

    if not supports:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.12);
                    border-radius:12px;padding:32px;text-align:center;margin-top:20px;">
            <div style="font-size:48px;margin-bottom:12px;">📭</div>
            <div style="color:rgba(240,240,245,0.5);font-size:14px;">まだ応援が届いていません</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # 未返信 / 返信済み カウント
    unreplied = [s for s in supports if not s["reply_emoji"] and not s["reply_text"]]
    replied = [s for s in supports if s["reply_emoji"] or s["reply_text"]]
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("応援総数", f"{len(supports)}件")
    col_b.metric("未返信", f"{len(unreplied)}件")
    col_c.metric("返信済", f"{len(replied)}件")

    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:14px;color:rgba(240,240,245,0.6);margin-bottom:16px;">新着 {len(supports)} 件の応援メッセージ</div>', unsafe_allow_html=True)

    for idx, record in enumerate(supports):
        sid = record["support_id"]
        amt_disp = f"{record['amount']:,}"
        date_disp = record["created_at"][:10]
        msg_disp = record["message"] if record["message"] else "（メッセージなし）"
        has_reply = bool(record["reply_emoji"] or record["reply_text"])
        badge_color = "#22c55e" if has_reply else "#f97316"
        badge_text = "✅ 返信済" if has_reply else "⏳ 未返信"

        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);
                    border-radius:14px;padding:18px;margin-bottom:14px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div style="font-size:22px;font-weight:900;
                            background:linear-gradient(135deg,#8b5cf6,#ec4899);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                    {amt_disp}
                </div>
                <span style="font-size:11px;font-weight:700;color:{badge_color};
                             background:rgba(255,255,255,0.06);border-radius:9999px;
                             padding:3px 10px;border:1px solid {badge_color}40;">
                    {badge_text}
                </span>
            </div>
            <div style="font-size:13px;color:rgba(240,240,245,0.75);margin-bottom:6px;">
                💬 {msg_disp}
            </div>
            <div style="font-size:11px;color:rgba(240,240,245,0.4);">{date_disp}</div>
        </div>
        """, unsafe_allow_html=True)

        # 返信フォーム (Streamlit ウィジェット)
        with st.expander("📝 返信する" if not has_reply else "✏️ 返信を編集", expanded=False):
            # 絵文字 & テキストをセッション初期化（value=渡しによる毎rerunリセットを防ぐ）
            emoji_key = f"emoji_{sid}"
            txt_key   = f"rtxt_{sid}"
            if emoji_key not in st.session_state:
                st.session_state[emoji_key] = record.get("reply_emoji") or REPLY_EMOJIS[0]
            if txt_key not in st.session_state:
                st.session_state[txt_key] = record.get("reply_text") or ""

            cols = st.columns(len(REPLY_EMOJIS))
            for ci, em in enumerate(REPLY_EMOJIS):
                if cols[ci].button(em, key=f"em_{sid}_{ci}"):
                    st.session_state[emoji_key] = em
                    st.rerun()

            chosen_emoji = st.session_state[emoji_key]
            st.markdown(f'<div style="text-align:center;font-size:36px;margin:8px 0;">{chosen_emoji}</div>', unsafe_allow_html=True)

            reply_text = st.text_area(
                "メッセージ（任意）",
                max_chars=200,
                key=txt_key,
                placeholder="ありがとう！いつも応援してくれて嬉しいです 😊",
            )

            if st.button("📨 送信する", key=f"send_{sid}", type="primary"):
                ok = set_reply(sid, chosen_emoji, reply_text)
                if ok:
                    st.session_state["reply_success_msg"] = "返信を保存しました！"
                    st.rerun()
                else:
                    st.error("保存に失敗しました。")

            # 応援証明リンク
            proof_url = f"{BASE_URL}?page=my_support&sid={sid}"
            st.markdown(f'<div style="margin-top:8px;font-size:12px;color:rgba(240,240,245,0.4);">🔗 <a href="{proof_url}" target="_top" style="color:#8b5cf6;">応援証明ページを確認</a></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="oshi-footer" style="margin-top:28px;">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 応援履歴ページ（サポーター向け）──
if page == "my_history":
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">📋 応援履歴</div>', unsafe_allow_html=True)

    sids_param = params.get("sids", "")

    if not sids_param:
        # localStorageからsupport_idリストを読み込んでURLに付け直す
        components.html(f"""
        <script>
        try {{
            var h = JSON.parse(localStorage.getItem('oshipay_history') || '[]');
            if (h.length > 0) {{
                window.top.location.href = '{BASE_URL}?page=my_history&sids=' + h.join(',');
            }}
        }} catch(e) {{}}
        </script>
        """, height=60)
        st.markdown('<div style="text-align:center;color:rgba(240,240,245,0.45);font-size:13px;margin-top:20px;">読み込み中... または応援履歴がありません。</div>', unsafe_allow_html=True)
        st.stop()

    sids = [s.strip() for s in sids_param.split(",") if s.strip()][:50]
    records = [get_support(sid) for sid in sids]
    records = [r for r in records if r]

    if not records:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.12);
                    border-radius:12px;padding:32px;text-align:center;margin-top:20px;">
            <div style="font-size:48px;margin-bottom:12px;">📭</div>
            <div style="color:rgba(240,240,245,0.5);font-size:14px;">応援履歴がありません</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    st.markdown(f'<div style="font-size:13px;color:rgba(240,240,245,0.5);margin-bottom:16px;">{len(records)}件の応援記録</div>', unsafe_allow_html=True)

    for record in records:
        amt_disp = f"{record['amount']:,}"
        date_disp = record["created_at"][:10]
        msg_disp = record["message"] if record["message"] else "（メッセージなし）"
        has_reply = bool(record.get("reply_emoji") or record.get("reply_text"))
        proof_url = f"{BASE_URL}?page=my_support&sid={record['support_id']}"
        reply_badge = f'<span style="color:#22c55e;font-size:11px;">💬 返信あり</span>' if has_reply else '<span style="color:rgba(240,240,245,0.35);font-size:11px;">⏳ 返信待ち</span>'

        st.markdown(f"""
        <a href="{proof_url}" target="_top" style="text-decoration:none;">
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);
                    border-radius:14px;padding:16px;margin-bottom:10px;cursor:pointer;
                    transition:border-color 0.2s;" onmouseover="this.style.borderColor='rgba(139,92,246,0.4)'"
                    onmouseout="this.style.borderColor='rgba(255,255,255,0.1)'">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <div style="font-weight:700;color:#f0f0f5;font-size:15px;">{record['creator_name']}</div>
                <div style="font-size:20px;font-weight:900;
                            background:linear-gradient(135deg,#8b5cf6,#ec4899);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                    {amt_disp}
                </div>
            </div>
            <div style="font-size:12px;color:rgba(240,240,245,0.6);margin-bottom:4px;">💬 {msg_disp}</div>
            <div style="display:flex;justify-content:space-between;align-items:center;">
                <div style="font-size:11px;color:rgba(240,240,245,0.35);">{date_disp}</div>
                {reply_badge}
            </div>
        </div>
        </a>
        """, unsafe_allow_html=True)

    st.markdown(f'<div style="text-align:center;margin-top:20px;"><a href="{BASE_URL}?page=supporter_dashboard" target="_top" style="display:inline-block; font-size:14px; font-weight:700; color:#c4b5fd; text-decoration:none; background:rgba(139,92,246,0.15); border:1px solid rgba(139,92,246,0.4); border-radius:12px; padding:10px 20px;">🦸 IDを作ってクラウドで一括管理する</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="oshi-footer" style="margin-top:24px;">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.stop()

# ── キャンセル ──
if page == "cancel":
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:80px;margin-bottom:20px;">🤔</div><div class="section-title">キャンセルしました</div>', unsafe_allow_html=True)
    st.stop()

# ── テストページ（開発用）──
if page == "test":
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🧪 テスト用シミュレーター</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">Stripe決済をスキップして機能を確認</div>', unsafe_allow_html=True)
    st.warning("⚠️ このページは開発テスト専用です。本番では使わないでください。")

    # ── テストデータを追加 ──
    with st.form("test_support_form"):
        st.markdown("#### 応援をシミュレート")
        c1, c2 = st.columns(2)
        t_creator = c1.text_input("クリエイター名", value="テストクリエイター")
        t_acct = c2.text_input("アカウントID", value="acct_test_001")
        t_amount = st.select_slider("応援金額", options=[100, 500, 1000, 3000, 5000, 10000], value=500)
        t_msg = st.text_input("メッセージ", value="いつも応援してます！")
        go = st.form_submit_button("🔥 テスト応援を追加する", type="primary", use_container_width=True)

    if go:
        new_sid = str(uuid.uuid4())
        add_support(new_sid, t_acct, t_creator, t_amount, t_msg)
        my_url = f"{BASE_URL}?page=my_support&sid={new_sid}"
        rv_url = f"{BASE_URL}?page=reply_view&acct={t_acct}"
        st.success(f"追加完了！ `{new_sid[:8]}...`")
        b1, b2 = st.columns(2)
        b1.link_button("🏅 応援証明を確認", my_url, use_container_width=True)
        b2.link_button("💌 返信ダッシュボード", rv_url, use_container_width=True)

    # ── 保存済みデータ一覧 ──
    all_supports = load_supports()
    st.markdown(f"#### 保存済みデータ（{len(all_supports)}件）")
    if not all_supports:
        st.info("まだデータがありません。上フォームから追加してください。")
    else:
        for s in reversed(all_supports):
            replied = s["reply_emoji"] or s["reply_text"]
            badge = f"✅ {s['reply_emoji']}" if replied else "⏳ 未返信"
            my_url = f"{BASE_URL}?page=my_support&sid={s['support_id']}"
            rv_url  = f"{BASE_URL}?page=reply_view&acct={s['creator_acct']}"
            st.markdown(f"""
            <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);
                        border-radius:10px;padding:14px;margin-bottom:8px;font-size:13px;
                        color:rgba(240,240,245,0.85);">
                <div style="display:flex;justify-content:space-between;margin-bottom:4px;">
                    <b style="color:#c4b5fd;">{s['creator_name']}</b>
                    <span style="font-weight:700;color:#f97316;">{s['amount']:,}</span>
                </div>
                <div style="font-size:11px;color:rgba(240,240,245,0.45);margin-bottom:4px;">
                    acct: {s['creator_acct']} &nbsp;|&nbsp; {s['created_at'][:10]}
                </div>
                <div style="margin-bottom:6px;">💬 {s['message'] or '（なし）'}</div>
                <div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:8px;">{badge}</div>
                <a href="{my_url}" target="_top" style="color:#8b5cf6;font-size:12px;margin-right:12px;">🏅 応援証明</a>
                <a href="{rv_url}" target="_top" style="color:#8b5cf6;font-size:12px;">💌 返信DL</a>
            </div>
            """, unsafe_allow_html=True)

        if st.button("🗑️ テストデータを全消去", type="secondary"):
            delete_all_supports()
            st.rerun()

    st.stop()

# ── ランキング（月間 / 全期間）──
if page == "ranking":
    now = datetime.datetime.now(datetime.timezone.utc)
    month_label = f"{now.year}年{now.month}月"

    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏆 応援ランキング</div>', unsafe_allow_html=True)

    def render_ranking(supports, total_label):
        if not supports:
            st.markdown('<div style="text-align:center;padding:60px 20px;color:rgba(255,255,255,0.35);font-size:14px;">まだ応援データがありません 🌱</div>', unsafe_allow_html=True)
            return
        # クリエイター別に集計
        creator_map = {}
        for s in supports:
            acct = s["creator_acct"]
            if acct not in creator_map:
                creator_map[acct] = {"name": s["creator_name"], "acct": acct, "total": 0, "supports": []}
            creator_map[acct]["total"] += s["amount"]
            creator_map[acct]["supports"].append(s)

        ranked = sorted(creator_map.values(), key=lambda x: x["total"], reverse=True)

        # creatorsテーブルから display_name / slug を一括取得して上書き
        try:
            _acct_ids = [c["acct"] for c in ranked]
            _cr_rows = get_db().table("creators").select("acct_id,display_name,name,slug,photo_url").in_("acct_id", _acct_ids).execute()
            _cr_name_map = {r["acct_id"]: r for r in (_cr_rows.data or [])}
            for c in ranked:
                _cr = _cr_name_map.get(c["acct"], {})
                _dn = _cr.get("display_name") or _cr.get("name") or _cr.get("slug") or c["name"]
                c["name"] = _dn
                c["photo_url"] = _cr.get("photo_url") or ""
        except Exception:
            pass

        # サポーター名マップを一括取得
        all_sup_ids = list({s["supporter_id"] for c in ranked for s in c["supports"] if s.get("supporter_id")})
        sup_name_map = get_supporters_map(all_sup_ids)

        rank_medals = ["🥇", "🥈", "🥉"]

        for i, creator in enumerate(ranked):
            medal = rank_medals[i] if i < 3 else f"{i + 1}位"
            creator_url = f"https://oyajibuki.github.io/OshiPay/creator.html?id={creator['acct']}"
            top3 = sorted(creator["supports"], key=lambda x: x["amount"], reverse=True)[:3]

            sup_rows_html = ""
            for j, sup in enumerate(top3):
                amt = sup["amount"]
                tier_label, tier_color, tier_bg = get_tier_badge(amt)
                sup_id = sup.get("supporter_id")
                sup_name = sup_name_map.get(sup_id, "（匿名）") if sup_id else "（匿名）"
                row_medal = ["🥇", "🥈", "🥉"][j]
                if sup_id:
                    port_url = f"{BASE_URL}?page=portfolio&id={sup_id}"
                    name_html = f'<a href="{port_url}" target="_blank" style="color:{tier_color};text-decoration:none;font-weight:700;">{sup_name}</a>'
                else:
                    name_html = f'<span style="color:rgba(255,255,255,0.45);">{sup_name}</span>'
                row_div = (
                    f'<div style="display:flex;align-items:center;gap:8px;padding:7px 0;border-bottom:1px solid rgba(255,255,255,0.05);">'
                    f'<span style="font-size:15px;min-width:22px;">{row_medal}</span>'
                    f'<span style="flex:1;font-size:13px;">{name_html}</span>'
                    f'<span style="font-size:11px;padding:2px 9px;border-radius:20px;background:{tier_bg};color:{tier_color};border:1px solid {tier_color};white-space:nowrap;">{tier_label}</span>'
                    f'<span style="font-size:13px;font-weight:700;color:rgba(255,255,255,0.9);white-space:nowrap;margin-left:8px;">{amt:,}</span>'
                    f'</div>'
                )
                sup_rows_html += row_div

            _photo_url = creator.get("photo_url", "")
            if _photo_url:
                _avatar_html = (
                    f'<img src="{_photo_url}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;'
                    f'border:2px solid rgba(255,255,255,0.15);flex-shrink:0;" />'
                )
            else:
                _avatar_html = (
                    f'<div style="width:40px;height:40px;border-radius:50%;background:rgba(139,92,246,0.2);'
                    f'border:2px solid rgba(139,92,246,0.3);display:flex;align-items:center;justify-content:center;'
                    f'font-size:18px;flex-shrink:0;">🎤</div>'
                )
            card_html = (
                f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:16px 20px;margin-bottom:12px;cursor:pointer;" onclick="window.open(\'{creator_url}\', \'_blank\')">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">'
                f'<span style="font-size:22px;min-width:28px;text-align:center;">{medal}</span>'
                f'{_avatar_html}'
                f'<a href="{creator_url}" target="_blank" style="font-size:16px;font-weight:900;color:#f0f0f5;text-decoration:none;flex:1;">{creator["name"]}</a>'
                f'<span style="font-size:11px;color:rgba(240,240,245,0.4);">{total_label}</span>'
                f'<span style="font-size:18px;font-weight:900;color:#f97316;">{creator["total"]:,}</span>'
                f'</div>'
                f'{sup_rows_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    tab_monthly, tab_alltime = st.tabs([f"📅 月間 ({month_label})", "🌟 全期間"])

    with tab_monthly:
        render_ranking(get_monthly_ranking(), "月間合計")

    with tab_alltime:
        render_ranking(get_all_time_ranking(), "全期間合計")

    # フッター（OshiPay宣伝）
    footer_html = (
        f'<div style="margin-top:40px;padding:20px 24px;background:rgba(249,115,22,0.08);border:1px solid rgba(249,115,22,0.3);border-radius:16px;text-align:center;">'
        f'<div style="font-size:20px;font-weight:900;color:#f97316;margin-bottom:6px;">OshiPayで推しを応援しよう</div>'
        f'<div style="font-size:12px;color:rgba(240,240,245,0.55);margin-bottom:12px;">あなたの応援がランキングに刻まれます</div>'
        f'<a href="{BASE_URL}" target="_top" style="font-size:12px;color:#f97316;background:rgba(249,115,22,0.15);padding:6px 14px;border-radius:8px;text-decoration:none;">応援する →</a>'
        f'</div>'
    )
    st.markdown(footer_html, unsafe_allow_html=True)
    st.stop()

# ── コインプレビュー（開発用）──
if page == "coin_preview":
    st.markdown('<div class="section-title">🪙 コイン全色プレビュー</div>', unsafe_allow_html=True)
    st.markdown("**ティア一覧（返信なし）**")
    tier_cases = [
        ("🌈 LEGEND",  100000, 1,  "none"),
        ("💎 DIAMOND",  10000, 1,  "none"),
        ("🥇 GOLD",      1000, 1,  "none"),
        ("🥈 SILVER",     500,  50,   "none"),
        ("🟤 BRONZE",     100,  1000, "none"),
    ]
    cols = st.columns(5)
    for col, (label, amt, rank, rim) in zip(cols, tier_cases):
        b64 = generate_coin_image("テストクリエイター", amt, "2026-03", "abc12345", rank=rank, reply_tier=rim)
        col.markdown(f'<div style="text-align:center;font-size:12px;margin-bottom:4px;">{label}</div>', unsafe_allow_html=True)
        col.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%;border-radius:50%;">', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown("**ふちバリエーション（GOLDで確認）**")
    rim_cases = [
        ("シルバーふち（返信なし）",        1000, 1, "none"),
        ("ゴールドふち（絵文字あり）",     1000, 1, "emoji"),
        ("ダイアモンドふち（返信あり）",   1000, 1, "text"),
    ]
    cols2 = st.columns(3)
    for col, (label, amt, rank, rim) in zip(cols2, rim_cases):
        b64 = generate_coin_image("テストクリエイター", amt, "2026-03", "abc12345", rank=rank, reply_tier=rim)
        col.markdown(f'<div style="text-align:center;font-size:12px;margin-bottom:4px;">{label}</div>', unsafe_allow_html=True)
        col.markdown(f'<img src="data:image/png;base64,{b64}" style="width:100%;border-radius:50%;">', unsafe_allow_html=True)
    st.stop()

# ── 開発ナビゲーション ──
if page == "nav":
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🗺️ 全ページ一覧</div>', unsafe_allow_html=True)
    st.markdown('<div style="background:rgba(249,115,22,0.12);border:1px solid rgba(249,115,22,0.4);border-radius:10px;padding:10px 14px;font-size:12px;color:#f97316;margin-bottom:24px;">⚠️ 開発確認用ページ — ダミーアカウント使用</div>', unsafe_allow_html=True)
    _qname = urllib.parse.quote("テストクリエイター")
    def _nav_header(txt):
        st.markdown(f'<div style="font-size:13px;font-weight:700;color:rgba(240,240,245,0.5);letter-spacing:0.08em;margin:20px 0 8px;">{txt}</div>', unsafe_allow_html=True)
    _nav_header("🌐 公開ページ")
    st.link_button("🏆 月間ランキング（公開用）", f"{BASE_URL}?page=ranking", use_container_width=True)
    _nav_header("🧭 サポーター導線")
    st.link_button("🏠 LP（サービス紹介）", f"{BASE_URL}?page=lp", use_container_width=True)
    st.link_button("📋 応援履歴（ブラウザ保存）", f"{BASE_URL}?page=my_history", use_container_width=True)
    st.link_button("🦸 サポーターDL", f"{BASE_URL}?page=supporter_dashboard", use_container_width=True)
    _nav_header("🎤 クリエイター導線")
    st.link_button("🛠️ クリエイターDL（QRコード発行）", f"{BASE_URL}?page=dashboard", use_container_width=True)
    _nav_header("📄 法的ページ")
    col1, col2, col3 = st.columns(3)
    col1.link_button("利用規約", f"{BASE_URL}?page=terms", use_container_width=True)
    col2.link_button("プライバシー", f"{BASE_URL}?page=privacy", use_container_width=True)
    col3.link_button("特定商取引法", f"{BASE_URL}?page=legal", use_container_width=True)
    _nav_header("🧪 開発")
    st.link_button("テストシミュレーター（決済スキップ）", f"{BASE_URL}?page=test", use_container_width=True)
    st.markdown('<div style="margin-top:32px;padding:16px;background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:12px;font-size:12px;color:rgba(240,240,245,0.6);line-height:1.8;">💡 <b style="color:#c4b5fd;">⑤ サポーターID自動入力の確認手順</b><br>① 上の「サポーターDL」でログイン<br>② ログイン後、画面内のリンクから「応援ページ」へ遷移<br>③ サポーターIDが自動入力されているのを確認</div>', unsafe_allow_html=True)
    st.stop()

# ── 応援・ダッシュボード ──
support_user = params.get("user", "")
connect_acct = params.get("acct", "")
support_name = params.get("name", "")
support_icon = params.get("icon", "🎤")
support_photo = ""

# 新URL形式: ?page=support&creator={slug or acct_id}
_creator_param = params.get("creator", "")
if _creator_param and not support_user:
    try:
        _cr_resp = get_db().table("creators").select(
            "acct_id,display_name,name,photo_url"
        ).or_(f"slug.eq.{_creator_param},acct_id.eq.{_creator_param}").maybe_single().execute()
        if _cr_resp.data:
            _cr = _cr_resp.data
            support_user  = _cr.get("acct_id", _creator_param)
            connect_acct  = _cr.get("acct_id", _creator_param)
            support_name  = _cr.get("display_name") or _cr.get("name") or _creator_param
            support_photo = _cr.get("photo_url") or ""
    except Exception:
        pass
elif support_user:
    # 旧URL形式でもDBからphoto_urlを取得
    try:
        _cr_resp2 = get_db().table("creators").select("photo_url").or_(
            f"slug.eq.{support_user},acct_id.eq.{support_user}"
        ).maybe_single().execute()
        support_photo = (_cr_resp2.data or {}).get("photo_url") or ""
    except Exception:
        pass

if page == "support" and support_user:
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    if support_photo:
        st.markdown(f'<div style="width:72px;height:72px;border-radius:50%;margin:0 auto 14px;box-shadow:0 0 30px rgba(139,92,246,0.25);overflow:hidden;border:2px solid rgba(139,92,246,0.3);"><img src="{support_photo}" style="width:100%;height:100%;object-fit:cover;"></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="support-avatar">{support_icon}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="support-name">{support_name or "Creator"}</div><div class="support-label">を応援しよう</div>', unsafe_allow_html=True)
    if "amt" not in st.session_state: st.session_state.amt = 100
    
    st.markdown('<div class="section-subtitle">応援する金額を選んで、メッセージを送ろう</div>', unsafe_allow_html=True)
    
    # 金額の選択肢（ドラム用）: 非線形で作成して操作性を向上
    # 100-1000(100刻み), 1000-10000(500刻み), 10000-100000(5000刻み), 100000-1000000(50000刻み)
    slider_options = (
        list(range(100, 1000, 100)) + 
        list(range(1000, 10000, 500)) + 
        list(range(10000, 100000, 5000)) + 
        list(range(100000, 1000001, 50000))
    )
    # 現在のamtがoptionsにない場合は一番近い値を探す
    current_amt = int(st.session_state.amt)
    if current_amt not in slider_options:
        current_amt = min(slider_options, key=lambda x: abs(x - current_amt))

    # ドラム型スライダー
    selected_amt = st.select_slider(
        "応援金額を選択 (ドラムロール)",
        options=slider_options,
        value=current_amt,
        key="amt_slider"
    )
    if selected_amt != st.session_state.amt:
        st.session_state.amt = selected_amt
        st.rerun()

    st.markdown(f'<div class="selected-amount-display">{int(st.session_state.amt):,}</div>', unsafe_allow_html=True)
    msg = st.text_area("応援メッセージ（オプション）", max_chars=140)

    st.markdown('<div class="section-subtitle" style="text-align:left;margin-bottom:4px;">👤 お名前（任意）</div><div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:8px;">入力するとランキングにお名前が表示されます</div>', unsafe_allow_html=True)
    _default_name = st.session_state.get("supporter_auth", {}).get("display_name", "")
    sup_display_name = st.text_input("お名前", value=_default_name, placeholder="例: たろう", label_visibility="collapsed")

    # ボタンの無効化処理を追加
    is_disabled = st.session_state.amt < 100
    if is_disabled:
        st.info("💡 応援は100円から受け付けています。金額を選択してください。")

    # ── 改正特商法に基づく最終確認表示 ──
    st.markdown(f"""
    <div style="background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 16px; margin-top: 20px; margin-bottom: 20px;">
        <div style="font-size: 13px; color: #f0f0f5; font-weight: 700; margin-bottom: 10px; border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 5px;">最終確認</div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span style="font-size: 12px; color: rgba(240,240,245,0.6);">支払総額（税込）</span>
            <span style="font-size: 14px; color: #f97316; font-weight: 700;">{int(st.session_state.amt):,}</span>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 6px;">
            <span style="font-size: 12px; color: rgba(240,240,245,0.6);">支払時期</span>
            <span style="font-size: 12px; color: #f0f0f5;">決済手続き完了時</span>
        </div>
        <div style="margin-top: 10px; padding-top: 10px; border-top: 1px dashed rgba(255,255,255,0.1);">
            <div style="font-size: 11px; color: rgba(240,240,245,0.5); line-height: 1.4;">
                ※デジタルコンテンツおよび投げ銭の性質上、決済手続き完了後のキャンセル、返金、返品には一切応じられません。
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle" style="text-align:left; margin-bottom:5px;">🎫 あなたのサポーターID（任意）</div><div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:10px;">IDを入れると実績が自動でアカウントに紐づきます。</div>', unsafe_allow_html=True)
    _default_sup_id = st.session_state.get("supporter_auth", {}).get("supporter_id", "")
    opt_sup_id = st.text_input("サポーターID", value=_default_sup_id, placeholder="sup_xxxxxxxx", label_visibility="collapsed")

    if st.button("🔥 応援する！", disabled=is_disabled):
        amt = st.session_state.amt
        support_id = str(uuid.uuid4())  # 応援証明用ユニークID
        # 名前入力ありでsup_idなし → 自動生成
        final_sup_id = opt_sup_id or ("sup_" + uuid.uuid4().hex[:8] if sup_display_name else "")
        try:
            checkout_params = {
                "payment_method_types": ["card"], "mode": "payment",
                "line_items": [{"price_data": {"currency": "jpy", "product_data": {"name": f"{support_name}への応援"}, "unit_amount": amt}, "quantity": 1}],
                "success_url": f"{BASE_URL}?page=success&s_name={urllib.parse.quote(support_name)}&s_amt={amt}&s_acct={connect_acct}&s_msg={urllib.parse.quote(msg or '')}&s_sid={support_id}&s_sup_id={final_sup_id}&s_sup_name={urllib.parse.quote(sup_display_name or '')}",
                "cancel_url": f"{BASE_URL}?page=cancel",
                "metadata": {"user_id": support_user, "message": msg, "support_id": support_id, "supporter_id": opt_sup_id}
            }
            if connect_acct:
                checkout_params["payment_intent_data"] = {"application_fee_amount": int(amt * 0.1)}
                session = stripe.checkout.Session.create(**checkout_params, stripe_account=connect_acct)
            else: session = stripe.checkout.Session.create(**checkout_params)
            st.markdown(f'<script>window.top.location.href = "{session.url}";</script>', unsafe_allow_html=True)
            st.link_button("💳 決済ページへ", session.url)
        except Exception as e: st.error(e)
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms" target="_top">利用規約</a><a href="{BASE_URL}?page=privacy" target="_top">プライバシーポリシー</a><a href="{BASE_URL}?page=legal" target="_top">特定商取引法</a></div>', unsafe_allow_html=True)

# ── サポーター公開ポートフォリオ ──
elif page == "portfolio":
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 600px !important; margin: 0 auto; }</style>", unsafe_allow_html=True)
    p_id = params.get("id", "")
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    if not p_id:
        st.error("サポーターIDが指定されていません。")
        st.stop()
        
    resp = get_db().table("supporters").select("*").eq("supporter_id", p_id).execute()
    if not resp.data:
        st.error("サポーターが見つかりません。")
        st.stop()
        
    supporter = resp.data[0]
    st.markdown(f'<div class="section-title">{supporter["display_name"]} の応援実績 🏅</div>', unsafe_allow_html=True)
    
    s_resp = get_db().table("supports").select("*").eq("supporter_id", p_id).order("created_at", desc=True).execute()
    s_data = s_resp.data or []
    
    if not s_data:
        st.write("まだ応援実績がありません。")
        st.stop()
        
    total_amount = sum(s["amount"] for s in s_data)
    creators = list(set([s["creator_name"] for s in s_data]))
    
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div style="background:rgba(255,165,0,0.1); border-radius:12px; padding:16px; text-align:center;"><div style="font-size:12px; color:rgba(255,255,255,0.6);">累計応援額</div><div style="font-size:24px; font-weight:700; color:#f97316;">{total_amount:,}</div></div>', unsafe_allow_html=True)
    with c2:
        st.markdown(f'<div style="background:rgba(139,92,246,0.1); border-radius:12px; padding:16px; text-align:center;"><div style="font-size:12px; color:rgba(255,255,255,0.6);">応援した推し</div><div style="font-size:24px; font-weight:700; color:#c4b5fd;">{len(creators)}人</div></div>', unsafe_allow_html=True)
    
    st.markdown("<br>### 🏆 応援実績リスト", unsafe_allow_html=True)
    for s in s_data:
        my_url = f"{BASE_URL}?page=my_support&sid={s['support_id']}"
        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1); border-radius:12px; padding:16px; margin-bottom:10px;">
            <div style="display:flex; justify-content:space-between; align-items:center;">
                <div>
                    <div style="font-weight:700;color:#f0f0f5;font-size:15px;">{s['creator_name']} 様へ {s['amount']:,}</div>
                    <div style="font-size:11px;color:rgba(240,240,245,0.5);margin-top:4px;">{s['created_at'][:10]}</div>
                </div>
                <a href="{my_url}" target="_top" style="font-size:12px;color:#8b5cf6;text-decoration:none;">📄 証明証</a>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    share_text = f"私のOshiPay応援実績はこちら！総額 {total_amount:,}\n#OshiPay\n{BASE_URL}?page=portfolio&id={p_id}"
    st.link_button("𝕏 で公開する", f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}", use_container_width=True)
    st.link_button("あなたもOshiPayを始めよう", f"{BASE_URL}?page=lp", use_container_width=True)
    st.stop()

# ── サポーター用ダッシュボード ──
elif page == "supporter_dashboard":
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">サポーター・ダッシュボード</div>', unsafe_allow_html=True)
    
    if "supporter_auth" not in st.session_state:
        st.info("過去の応援を一つにまとめた、公開ポートフォリオを作成できます。")
        tab_login, tab_register, tab_forgot = st.tabs(["🔑 ログイン", "✨ 新規登録", "🔓 パスワードを忘れた"])

        with tab_login:
            l_id = st.text_input("サポーターID", key="l_id")
            l_pass = st.text_input("パスワード", type="password", key="l_pass")
            if st.button("ログイン", use_container_width=True):
                resp = get_db().table("supporters").select("*").eq("supporter_id", l_id).execute()
                if not resp.data:
                    st.error("アカウントが見つかりません。")
                else:
                    if resp.data[0]["password_hash"] == hash_password(l_pass):
                        st.session_state["supporter_auth"] = resp.data[0]
                        st.rerun()
                    else:
                        st.error("パスワードが違います。")

        with tab_register:
            st.markdown('<div style="font-size:12px;color:rgba(255,255,255,0.6);margin-bottom:12px;">応援完了画面に表示されたサポーターIDとメールアドレスで登録します。</div>', unsafe_allow_html=True)
            r_sid  = st.text_input("サポーターID（応援完了画面に表示されたID）", key="r_sid", placeholder="sup_xxxxxxxx")
            r_email = st.text_input("メールアドレス", key="r_email", placeholder="example@email.com")
            r_name = st.text_input("表示名（公開されます）", key="r_name")
            r_pass = st.text_input("パスワードを設定", type="password", key="r_pass")
            if st.button("新規アカウントを作成", type="primary", use_container_width=True):
                if r_sid and r_email and r_name and r_pass:
                    existing = get_db().table("supporters").select("*").eq("supporter_id", r_sid).execute()
                    if existing.data:
                        row = existing.data[0]
                        if row.get("password_hash"):
                            st.error("このIDは既に登録済みです。ログインしてください。")
                        else:
                            get_db().table("supporters").update({
                                "display_name": r_name,
                                "email": r_email,
                                "password_hash": hash_password(r_pass)
                            }).eq("supporter_id", r_sid).execute()
                            st.success("登録完了！ログインしました。")
                            st.session_state["supporter_auth"] = {"supporter_id": r_sid, "display_name": r_name, "email": r_email}
                            st.rerun()
                    else:
                        sup_check = get_db().table("supports").select("support_id").eq("supporter_id", r_sid).execute()
                        if not sup_check.data:
                            st.error("このサポーターIDが見つかりません。応援完了画面に表示されたIDを入力してください。")
                        else:
                            try:
                                get_db().table("supporters").insert({
                                    "supporter_id": r_sid,
                                    "display_name": r_name,
                                    "email": r_email,
                                    "password_hash": hash_password(r_pass)
                                }).execute()
                                st.success("登録完了！ログインしました。")
                                st.session_state["supporter_auth"] = {"supporter_id": r_sid, "display_name": r_name, "email": r_email}
                                st.rerun()
                            except Exception as e:
                                st.error(f"登録エラー: {e}")
                else:
                    st.warning("全ての項目を入力してください。")

        with tab_forgot:
            st.markdown('<div style="font-size:12px;color:rgba(255,255,255,0.6);margin-bottom:12px;">登録時のサポーターIDとメールアドレスを入力すると、仮パスワードが発行されます。</div>', unsafe_allow_html=True)
            f_sid   = st.text_input("サポーターID", key="f_sid", placeholder="sup_xxxxxxxx")
            f_email = st.text_input("登録メールアドレス", key="f_email", placeholder="example@email.com")
            if st.button("仮パスワードを発行", use_container_width=True):
                if f_sid and f_email:
                    resp = get_db().table("supporters").select("*").eq("supporter_id", f_sid).execute()
                    if not resp.data:
                        st.error("アカウントが見つかりません。")
                    elif resp.data[0].get("email") != f_email.strip():
                        st.error("メールアドレスが一致しません。")
                    else:
                        temp_pass = uuid.uuid4().hex[:8]
                        get_db().table("supporters").update({"password_hash": hash_password(temp_pass)}).eq("supporter_id", f_sid).execute()
                        st.success("仮パスワードが発行されました。ログイン後にパスワードを変更してください。")
                        st.info(f"🔑 仮パスワード: `{temp_pass}`")
                else:
                    st.warning("IDとメールアドレスを入力してください。")
        st.stop()
        
    sup_user = st.session_state["supporter_auth"]
    st.markdown(f'<div style="font-size:18px; font-weight:700; text-align:center; color:#f0f0f5; margin-bottom:5px;">ようこそ、{sup_user["display_name"]} さん！</div>', unsafe_allow_html=True)
    st.markdown(f'<div style="font-size:13px; text-align:center; color:rgba(255,255,255,0.5); margin-bottom:20px;">あなたのサポーターID: <code>{sup_user["supporter_id"]}</code></div>', unsafe_allow_html=True)
    
    st.markdown("""
    <div style="background: rgba(139,92,246,0.1); border: 1px solid rgba(139,92,246,0.2); border-radius: 12px; padding: 16px; margin-bottom: 24px;">
        <div style="color: #8b5cf6; font-weight: 700; font-size: 14px; margin-bottom: 8px;">ℹ️ 次回からの応援について</div>
        <div style="font-size: 12px; color: rgba(240,240,245,0.7);">
            応援画面（決済画面）でオプションの「サポーターID」欄に上記のIDを入力すると、自動でここに応援実績が貯まります。
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="header" style="font-size:16px;">📊 応援実績をシェアする</div>', unsafe_allow_html=True)
    portfolio_url = f"{BASE_URL}?page=portfolio&id={sup_user['supporter_id']}"
    st.link_button("🌐 応援実績ページを見る（公開用）", portfolio_url, use_container_width=True)
    st.code(portfolio_url, language="text")
    
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    with st.expander("🔑 パスワードを変更する"):
        cp_curr = st.text_input("現在のパスワード", type="password", key="cp_curr")
        cp_new  = st.text_input("新しいパスワード", type="password", key="cp_new")
        cp_new2 = st.text_input("新しいパスワード（確認）", type="password", key="cp_new2")
        if st.button("パスワードを更新", key="cp_btn"):
            if cp_curr and cp_new and cp_new2:
                if cp_new != cp_new2:
                    st.error("新しいパスワードが一致しません。")
                else:
                    chk = get_db().table("supporters").select("password_hash").eq("supporter_id", sup_user["supporter_id"]).execute()
                    if chk.data and chk.data[0]["password_hash"] == hash_password(cp_curr):
                        get_db().table("supporters").update({"password_hash": hash_password(cp_new)}).eq("supporter_id", sup_user["supporter_id"]).execute()
                        st.success("パスワードを更新しました！")
                    else:
                        st.error("現在のパスワードが違います。")
            else:
                st.warning("全ての項目を入力してください。")
    if st.button("🚪 ログアウト", type="secondary"):
        del st.session_state["supporter_auth"]
        st.rerun()
    st.stop()

else: # Dashboard
    st.markdown('<div class="oshi-logo"><span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">QRコードを発行</div>', unsafe_allow_html=True)
    # アカウントIDの特定
    acct_id = connect_acct or params.get("acct")
    
    if not acct_id:
        if not params.get("fresh"):
            # ① localStorage からアカウントIDを自動復元
            components.html(f"""<script>
            (function(){{
              try {{
                var saved = localStorage.getItem('oshipay_acct');
                if (saved && saved.startsWith('acct_')) {{
                  window.parent.location.href = '{BASE_URL}?page=dashboard&acct=' + encodeURIComponent(saved);
                }}
              }} catch(e) {{}}
            }})();
            </script>""", height=0)
        st.markdown('<div class="header">応援用QRコードを作成・復元</div>', unsafe_allow_html=True)
        st.write("新しく応援（決済）を受け取るための設定を行うか、以前作成したアカウントを復元します。")

        tab_new, tab_recover, tab_forgot_c = st.tabs(["✨ 新規作成", "🔑 既存アカウントの復元", "🔓 パスワードを忘れた"])
        
        with tab_new:
            st.info("新しく応援受け取りを開始するには、管理用パスワードを作成してください。")
            st.caption("🔐 パスワード条件: 8文字以上・英字＋数字必須・同じ文字の3連続禁止（例: Oshi1234）")
            new_pass = st.text_input("管理用パスワードを作成", type="password", key="new_pass")

            _pass_ok = False
            if new_pass:
                _pass_ok, _pass_err = validate_password(new_pass)
                if not _pass_ok:
                    st.error(f"⚠️ {_pass_err}")
                else:
                    st.success("✅ パスワードOK")

            # 明示的なボタンによる発行の意思確認
            if st.checkbox("利用規約に同意して、新規にQRコードを発行して応援を受け取りますか？"):
                if not new_pass:
                    st.warning("パスワードを入力してください。")
                elif not _pass_ok:
                    st.warning("パスワードの条件を満たしてください。")
                elif "onboarding_url" not in st.session_state:
                    if st.button("🔗 Stripeアカウントを連携する"):
                        with st.spinner("Stripeと連携する準備をしています... (数秒かかります)"):
                            try:
                                # アカウント作成（ウェブサイトURLなどを事前注入）
                                acct_id = create_connect_account()
                                register_creator(acct_id, new_pass)
                                st.session_state["creator_auth"] = acct_id
                                # 登録用リンクを取得して保存
                                st.session_state.onboarding_url = create_account_link(acct_id)
                                st.rerun()
                            except Exception as e:
                                st.error(f"連携エラー: {e}")
                
                if "onboarding_url" in st.session_state:
                    st.markdown(f"""
                    <div style="background: rgba(139,92,246,0.1); border: 1px solid rgba(139,92,246,0.2); border-radius: 12px; padding: 20px; text-align: center;">
                        <div style="font-size: 24px; margin-bottom: 12px;">🌟</div>
                        <div style="color: #f0f0f5; font-weight: 700; font-size: 16px; margin-bottom: 8px;">ステップ 1/2: Stripeで本人確認</div>
                        <div style="font-size: 13px; color: rgba(240,240,245,0.7); margin-bottom: 20px;">
                            下のボタンを押して、Stripeの画面で「本人確認」と「銀行口座」の設定を完了させてください。<br>
                            完了すると自動的にここに戻ってきます。
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    st.link_button("👉 Stripeの登録画面へ進む", st.session_state.onboarding_url, type="primary")
                    # 念のための自動リダイレクトJSも併用
                    components.html(f'<script>window.top.location.href = "{st.session_state.onboarding_url}";</script>', height=0)
                    if st.button("❌ キャンセルしてやり直す"):
                        del st.session_state.onboarding_url
                        st.rerun()
            else:
                st.warning("発行・連携を進めるには上のチェックボックスをオンにしてください。")

        with tab_recover:
            # ── 既存アカウント復元フォーム ──
            st.markdown("""
            <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);
                        border-radius:14px;padding:16px 20px;margin-bottom:4px;">
                <div style="font-size:13px;font-weight:700;color:rgba(240,240,245,0.85);margin-bottom:4px;">
                    🔑 既にアカウントをお持ちの方
                </div>
                <div style="font-size:12px;color:rgba(240,240,245,0.5);">
                    以前に発行したURLに含まれる <code>acct_</code> から始まるIDを入力してください
                </div>
            </div>
            """, unsafe_allow_html=True)
            recover_input = st.text_input("アカウントID", placeholder="acct_xxxxxxxxxxxxxxxxxx", label_visibility="collapsed")
            recover_pass = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
            if st.button("✅ このアカウントで開く", use_container_width=True):
                rid = recover_input.strip()
                if rid.startswith("acct_") and len(rid) > 10 and recover_pass:
                    resp = get_db().table("creators").select("*").eq("acct_id", rid).execute()
                    if not resp.data:
                        # まだパスワードが設定されていない既存アカウントへの対応
                        register_creator(rid, recover_pass)
                        st.success("初期パスワードを設定しました！")
                        st.query_params["acct"] = rid
                        st.session_state["creator_auth"] = rid
                        st.rerun()
                    else:
                        if verify_creator(rid, recover_pass):
                            st.query_params["acct"] = rid
                            st.session_state["creator_auth"] = rid
                            st.rerun()
                        else:
                            st.error("パスワードが間違っています。")
                else:
                    st.error("アカウントIDとパスワードを正しく入力してください。")

        with tab_forgot_c:
            st.markdown('<div style="font-size:12px;color:rgba(255,255,255,0.6);margin-bottom:12px;">Stripe連携時のメールアドレスで本人確認し、仮パスワードを発行します。</div>', unsafe_allow_html=True)
            fc_acct  = st.text_input("アカウントID", key="fc_acct", placeholder="acct_xxxxxxxxxxxxxxxxxx")
            fc_email = st.text_input("Stripe登録メールアドレス", key="fc_email", placeholder="example@email.com")
            if st.button("仮パスワードを発行", key="fc_btn", use_container_width=True):
                if fc_acct and fc_email:
                    try:
                        acct_info = stripe.Account.retrieve(fc_acct)
                        stripe_email = acct_info.get("email", "")
                        if stripe_email.lower() == fc_email.strip().lower():
                            temp_pass = uuid.uuid4().hex[:8]
                            resp = get_db().table("creators").select("acct_id").eq("acct_id", fc_acct).execute()
                            if resp.data:
                                get_db().table("creators").update({"password_hash": hash_password(temp_pass)}).eq("acct_id", fc_acct).execute()
                            else:
                                register_creator(fc_acct, temp_pass)
                            st.success("本人確認完了！ログイン後にパスワードを変更してください。")
                            st.info(f"🔑 仮パスワード: `{temp_pass}`")
                        else:
                            st.error("メールアドレスが一致しません。Stripe連携時のメールアドレスを入力してください。")
                    except Exception:
                        st.error("アカウントIDが見つかりません。")
                else:
                    st.warning("IDとメールアドレスを入力してください。")
    else:
        # 認証チェック
        if st.session_state.get("creator_auth") != acct_id:
            st.warning("このダッシュボードを開くにはパスワードが必要です。")
            auth_pass = st.text_input("パスワードを入力", type="password", key="auth_pass")
            if st.button("ロックを解除", type="primary"):
                resp = get_db().table("creators").select("*").eq("acct_id", acct_id).execute()
                if not resp.data:
                    # 既存ユーザーだが未パスワード設定の場合はここで初回設定扱いにする
                    register_creator(acct_id, auth_pass)
                    st.session_state["creator_auth"] = acct_id
                    st.rerun()
                elif verify_creator(acct_id, auth_pass):
                    st.session_state["creator_auth"] = acct_id
                    st.rerun()
                else:
                    st.error("パスワードが違います。")
            st.markdown(f'<div style="text-align:center;margin-top:12px;"><a href="{BASE_URL}?page=dashboard&fresh=1" target="_top" style="font-size:11px;color:rgba(240,240,245,0.35);text-decoration:underline;">🔄 別のアカウントを使う / 新規作成</a></div>', unsafe_allow_html=True)
            st.stop()

        st.markdown(f"""
        <div style="background: rgba(139,92,246,0.1); border: 1px solid rgba(139,92,246,0.2); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
            <div style="color: #8b5cf6; font-weight: 700; font-size: 14px; margin-bottom: 4px;">✅ Stripe連携済み</div>
            <div style="font-size: 12px; color: rgba(240,240,245,0.6); margin-bottom: 12px;">ID: <code>{acct_id}</code></div>
            <div style="font-size: 11px; color: #f97316; font-weight: 700; margin-bottom: 8px;">ブラウザを閉じるとログアウトされます。必ずこのページをブックマークして保存してください！</div>
        </div>
        """, unsafe_allow_html=True)
        
        _icon_list = list(ICON_OPTIONS.keys())

        # ── プロフィールテキスト（先に取得してdisplay_nameをデフォルト値に使う）──
        try:
            _cr = get_db().table("creators").select("bio,genre,slug,photo_url,display_name,sns_links").eq("acct_id", acct_id).maybe_single().execute()
            _cr_data = _cr.data or {}
        except Exception:
            _cr_data = {}

        _def_name = st.session_state.get(f"creator_name_{acct_id}", "")
        if not _def_name:
            # 1) creatorsテーブルのdisplay_nameを優先
            _def_name = _cr_data.get("display_name") or ""
        if not _def_name:
            # 2) supports履歴から取得（フォールバック）
            try:
                last_s = get_db().table("supports").select("creator_name").eq("creator_acct", acct_id).order("created_at", desc=True).limit(1).execute()
                if last_s.data:
                    _def_name = last_s.data[0]["creator_name"]
            except Exception:
                pass
        _def_icon = st.session_state.get(f"creator_icon_{acct_id}", _icon_list[0])
        _def_icon_idx = _icon_list.index(_def_icon) if _def_icon in _icon_list else 0
        name = st.text_input("表示名", value=_def_name)
        icon = st.selectbox("アイコン", _icon_list, index=_def_icon_idx, key=f"icon_{acct_id}")

        # SNSリンクの既存値を取得
        _sns_raw = _cr_data.get("sns_links") or {}
        if isinstance(_sns_raw, str):
            try:
                _sns_raw = json.loads(_sns_raw)
            except Exception:
                _sns_raw = {}

        # 現在の写真を表示
        _current_photo = _cr_data.get("photo_url") or ""
        if _current_photo:
            st.image(_current_photo, width=80, caption="現在のプロフィール写真")

        bio  = st.text_area("自己紹介（bio）", value=_cr_data.get("bio") or "", max_chars=500, key=f"bio_{acct_id}",
                            help="最大500文字。電話番号・メール・LINE IDは入力不可")
        st.caption(f"{len(_cr_data.get('bio') or '')}/500文字")
        slug = st.text_input("ユーザーID（マイクロページURL用）", value=_cr_data.get("slug") or "", key=f"slug_{acct_id}",
                             help="例: asagiri → oshipay.com/asagiri（3〜20文字・英数字・ハイフンのみ）")

        st.markdown("**🔗 SNSリンク**（X・Instagram・YouTube・TikTok・note・Facebook・LINE）")
        _sns_x    = st.text_input("X（旧Twitter）",  value=_sns_raw.get("x", ""),         placeholder="https://x.com/username",              key=f"sns_x_{acct_id}")
        _sns_ig   = st.text_input("Instagram",        value=_sns_raw.get("instagram", ""), placeholder="https://instagram.com/username",       key=f"sns_ig_{acct_id}")
        _sns_yt   = st.text_input("YouTube",          value=_sns_raw.get("youtube", ""),   placeholder="https://youtube.com/@username",        key=f"sns_yt_{acct_id}")
        _sns_tt   = st.text_input("TikTok",           value=_sns_raw.get("tiktok", ""),    placeholder="https://tiktok.com/@username",         key=f"sns_tt_{acct_id}")
        _sns_note = st.text_input("note",             value=_sns_raw.get("note", ""),      placeholder="https://note.com/username",            key=f"sns_note_{acct_id}")
        _sns_fb   = st.text_input("Facebook",         value=_sns_raw.get("facebook", ""),  placeholder="https://facebook.com/username",        key=f"sns_fb_{acct_id}")
        _sns_line = st.text_input("LINE（公式アカウント）", value=_sns_raw.get("line", ""), placeholder="https://line.me/R/ti/p/@username",  key=f"sns_line_{acct_id}")

        if st.button("プロフィールを保存", key=f"save_profile_{acct_id}"):
            _save_errors = []
            # bio バリデーション
            _bio_ok, _bio_err = validate_bio(bio)
            if not _bio_ok:
                _save_errors.append(_bio_err)
            # slug バリデーション
            if slug:
                _slug_ok, _slug_err = validate_username(slug)
                if not _slug_ok:
                    _save_errors.append(_slug_err)
                else:
                    dup = get_db().table("creators").select("acct_id").eq("slug", slug).neq("acct_id", acct_id).execute()
                    if dup.data or check_slug_locked(get_db(), slug):
                        _save_errors.append(f"「{slug}」はすでに使われています。別のスラッグを入力してください。")
            # SNSリンク バリデーション（https:// 欠落を自動補完）
            _sns_inputs = {
                "x": _sns_x, "instagram": _sns_ig, "youtube": _sns_yt,
                "tiktok": _sns_tt, "note": _sns_note, "facebook": _sns_fb, "line": _sns_line,
            }
            _sns_normalized = {k: normalize_sns_url(v) for k, v in _sns_inputs.items()}
            _label_map = {"x": "X", "instagram": "Instagram", "youtube": "YouTube",
                          "tiktok": "TikTok", "note": "note", "facebook": "Facebook", "line": "LINE"}
            for _key, _url in _sns_normalized.items():
                _ok, _err = validate_sns_url(_url)
                if not _ok:
                    _save_errors.append(f"{_label_map[_key]}: {_err}")
            if _save_errors:
                for _e in _save_errors:
                    st.error(f"⚠️ {_e}")
            else:
                _sns_save = {k: v for k, v in _sns_normalized.items() if v}
                get_db().table("creators").update({
                    "bio":          bio,
                    "slug":         slug.lower() if slug else None,
                    "sns_links":    json.dumps(_sns_save, ensure_ascii=False),
                    "display_name": name or None,
                }).eq("acct_id", acct_id).execute()
                st.success("プロフィールを保存しました！")
                _saved_slug = slug.lower() if slug else acct_id
                _ms_preview_url = f"https://oyajibuki.github.io/OshiPay/creator.html?id={_saved_slug}"
                st.link_button("🌐 マイクロサイトを確認する", _ms_preview_url, use_container_width=True)

        # ── プロフィール写真アップロード ──
        uploaded_photo = st.file_uploader("プロフィール写真（任意・2MBまで）", type=["jpg", "jpeg", "png"], key=f"photo_{acct_id}")
        if uploaded_photo and uploaded_photo.size > 2 * 1024 * 1024:
            st.error("2MB以下の画像をアップロードしてください。")
            uploaded_photo = None
        if uploaded_photo:
            try:
                img = Image.open(uploaded_photo).convert("RGB")
                img.thumbnail((200, 200), Image.LANCZOS)
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=85)
                buf.seek(0)
                img_bytes = buf.read()
                file_path = f"creators/{acct_id}.jpg"
                get_db().storage.from_("creator-photos").upload(
                    file_path, img_bytes,
                    {"content-type": "image/jpeg", "upsert": "true"}
                )
                photo_url = get_db().storage.from_("creator-photos").get_public_url(file_path)
                get_db().table("creators").update({"photo_url": photo_url}).eq("acct_id", acct_id).execute()
                st.success("写真を保存しました！")
                st.image(img, width=100)
            except Exception as e:
                st.error(f"写真の保存に失敗しました: {e}")

        col1, col2 = st.columns([2, 1])
        if col1.button("✨ QRコードを生成", use_container_width=True):
            _final_id = slug.lower() if slug else acct_id
            support_url = f"{BASE_URL}?page=support&creator={_final_id}"
            st.session_state.qr_url = support_url
            st.session_state.qr_just_generated = True
            st.session_state[f"creator_name_{acct_id}"] = name
            st.session_state[f"creator_icon_{acct_id}"] = icon

        # 返信ダッシュボードへのリンク
        if st.button("💌 応援メッセージ・返信ダッシュボードを開く", use_container_width=True):
            st.query_params["page"] = "reply_view"
            st.query_params["acct"] = acct_id
            st.rerun()

        # パスワード変更
        with st.expander("🔑 パスワードを変更する"):
            cc_curr = st.text_input("現在のパスワード", type="password", key="cc_curr")
            cc_new  = st.text_input("新しいパスワード", type="password", key="cc_new")
            cc_new2 = st.text_input("新しいパスワード（確認）", type="password", key="cc_new2")
            if st.button("パスワードを更新", key="cc_btn"):
                if cc_curr and cc_new and cc_new2:
                    if cc_new != cc_new2:
                        st.error("新しいパスワードが一致しません。")
                    else:
                        chk = get_db().table("creators").select("password_hash").eq("acct_id", acct_id).execute()
                        if chk.data and chk.data[0]["password_hash"] == hash_password(cc_curr):
                            get_db().table("creators").update({"password_hash": hash_password(cc_new)}).eq("acct_id", acct_id).execute()
                            st.success("パスワードを更新しました！")
                        else:
                            st.error("現在のパスワードが違います。")
                else:
                    st.warning("全ての項目を入力してください。")

        # 連携解除ボタン
        if col2.button("🚫 連携解除"):
            st.components.v1.html("""
            <script>
            localStorage.removeItem('oshipay_acct');
            const url = new URL(window.location.href);
            url.searchParams.delete('acct');
            window.location.href = url.href;
            </script>
            """, height=0)
            st.stop()
        if "qr_url" in st.session_state:
            b64_qr, qr_bytes = generate_qr_data(st.session_state.qr_url)
            reply_dash_url = f"{BASE_URL}?page=reply_view&acct={acct_id}"
            info_txt = f"クリエイターID: {acct_id}\n応援URL: {st.session_state.qr_url}\n返信ダッシュボード: {reply_dash_url}"
            # QR画像とURLを表示
            st.markdown(f'<div class="qr-frame"><img src="data:image/png;base64,{b64_qr}"></div>', unsafe_allow_html=True)
            st.code(st.session_state.qr_url)
            # DLボタン2つ（PNG / テキスト）
            dl_col1, dl_col2 = st.columns(2)
            dl_col1.download_button(
                label="📥 QR画像を保存（PNG）",
                data=qr_bytes,
                file_name=f"oshipay2_qr_{acct_id}.png",
                mime="image/png",
                use_container_width=True,
            )
            dl_col2.download_button(
                label="📄 ID/URLをテキスト保存",
                data=info_txt.encode("utf-8"),
                file_name=f"oshipay2_info_{acct_id}.txt",
                mime="text/plain",
                use_container_width=True,
            )
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms" target="_top">利用規約</a><a href="{BASE_URL}?page=privacy" target="_top">プライバシーポリシー</a><a href="{BASE_URL}?page=legal" target="_top">特定商取引法</a></div>', unsafe_allow_html=True)