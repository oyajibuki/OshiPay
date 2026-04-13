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
import requests as _req
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.image import MIMEImage
from email.mime.text import MIMEText
from email.utils import formatdate
from PIL import Image

# ── ページ設定 ──
st.set_page_config(
    page_title="oshipay",
    page_icon="https://raw.githubusercontent.com/oyajibuki/OshiPay/main/docs/favicon.png",
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
    "💻": "エンジニア・クリエイター", "🎭": "役者・パフォーマー",
    "🐱": "猫", "🐶": "犬", "🔥": "その他",
}
BASE_URL = os.environ.get("APP_URL", "https://oshipay.me").rstrip('/') + '/'
LP_URL   = "https://oshipay.me/"
QR_BASE  = "https://oshipay.me"   # QRコードのベースURL（カスタムドメイン）

# ── Google OAuth 設定 ──
GOOGLE_CLIENT_ID     = ""
GOOGLE_CLIENT_SECRET = ""
try:
    GOOGLE_CLIENT_ID     = st.secrets["GOOGLE_CLIENT_ID"]
    GOOGLE_CLIENT_SECRET = st.secrets["GOOGLE_CLIENT_SECRET"]
except Exception:
    pass
GOOGLE_REDIRECT_URI = "https://oshipay.streamlit.app"

def _google_auth_url(state: str = "g_sup") -> str:
    return "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope": "openid email profile",
        "prompt": "select_account",
        "state": state,
    })

def _exchange_google_code(code: str) -> dict | None:
    try:
        tok = _req.post("https://oauth2.googleapis.com/token", data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }).json()
        at = tok.get("access_token")
        if not at:
            return None
        return _req.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {at}"},
        ).json()
    except Exception:
        return None

# ── Discord OAuth 設定 ──
DISCORD_CLIENT_ID     = ""
DISCORD_CLIENT_SECRET = ""
try:
    DISCORD_CLIENT_ID     = st.secrets["DISCORD_CLIENT_ID"]
    DISCORD_CLIENT_SECRET = st.secrets["DISCORD_CLIENT_SECRET"]
except Exception:
    pass
DISCORD_REDIRECT_URI = "https://oshipay.streamlit.app"

def _discord_auth_url(state: str = "d_sup") -> str:
    return "https://discord.com/api/oauth2/authorize?" + urllib.parse.urlencode({
        "client_id": DISCORD_CLIENT_ID,
        "redirect_uri": DISCORD_REDIRECT_URI,
        "response_type": "code",
        "scope": "identify email",
        "state": state,
    })

def _exchange_discord_code(code: str) -> dict | None:
    try:
        tok = _req.post("https://discord.com/api/oauth2/token", data={
            "code": code,
            "client_id": DISCORD_CLIENT_ID,
            "client_secret": DISCORD_CLIENT_SECRET,
            "redirect_uri": DISCORD_REDIRECT_URI,
            "grant_type": "authorization_code",
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
        at = tok.get("access_token")
        if not at:
            return None
        user = _req.get(
            "https://discord.com/api/users/@me",
            headers={"Authorization": f"Bearer {at}"},
        ).json()
        if not user.get("verified"):
            user["email"] = ""
        return user
    except Exception:
        return None

# ── LINE OAuth 設定 ──
LINE_CLIENT_ID     = ""
LINE_CLIENT_SECRET = ""
try:
    LINE_CLIENT_ID     = st.secrets["LINE_CLIENT_ID"]
    LINE_CLIENT_SECRET = st.secrets["LINE_CLIENT_SECRET"]
except Exception:
    pass
LINE_REDIRECT_URI = "https://oshipay.streamlit.app"

def _line_auth_url(state: str = "l_sup") -> str:
    return "https://access.line.me/oauth2/v2.1/authorize?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id":     LINE_CLIENT_ID,
        "redirect_uri":  LINE_REDIRECT_URI,
        "state":         state,
        "scope":         "profile openid",
    })

def _exchange_line_code(code: str) -> dict | None:
    try:
        tok = _req.post("https://api.line.me/oauth2/v2.1/token", data={
            "code":          code,
            "client_id":     LINE_CLIENT_ID,
            "client_secret": LINE_CLIENT_SECRET,
            "redirect_uri":  LINE_REDIRECT_URI,
            "grant_type":    "authorization_code",
        }, headers={"Content-Type": "application/x-www-form-urlencoded"}).json()
        at = tok.get("access_token")
        if not at:
            return None
        # プロフィール取得: {"userId": "...", "displayName": "...", "pictureUrl": "..."}
        return _req.get(
            "https://api.line.me/v2/profile",
            headers={"Authorization": f"Bearer {at}"},
        ).json()
    except Exception:
        return None

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
            "product_description": "oshipay - 投げ銭サービス",
            "url": BASE_URL
        },
        settings={
            "payouts": {
                "schedule": {"interval": "manual"}  # ¥10,000達成時にcronで自動ペイアウト
            }
        },
    )
    return account.id

def create_account_link(account_id, creator_acct_id=None, return_params=""):
    # return_url は oshipay の内部 acct_id（usr_XXX など）を使う
    _ret_acct = creator_acct_id or account_id
    return_url  = f"{BASE_URL}?page=dashboard&acct={_ret_acct}{return_params}"
    refresh_url = f"{BASE_URL}?page=dashboard&acct={_ret_acct}&refresh=1{return_params}"
    link = stripe.AccountLink.create(
        account=account_id, refresh_url=refresh_url, return_url=return_url, type="account_onboarding",
    )
    return link.url

# ── メール送信共通ヘルパー（Resend API）──────────────────────────────
RESEND_FROM = "noreply@oshipay.me"

def _send_email(to_email: str, subject: str, body: str, attachments: list = None) -> tuple[bool, str]:
    """Resend API でメール送信する共通関数"""
    try:
        import resend as _resend
        _resend.api_key = st.secrets.get("RESEND_API_KEY", os.environ.get("RESEND_API_KEY", ""))
        if not _resend.api_key:
            return False, "RESEND_API_KEY未設定"
        params = {"from": RESEND_FROM, "to": [to_email], "subject": subject, "text": body}
        if attachments:
            params["attachments"] = attachments
        _resend.Emails.send(params)
        return True, "送信成功"
    except Exception as e:
        return False, str(e)

def send_support_email(to_email, creator_name, amount, message, supporter_name=""):
    subject = f"{creator_name}さんに応援が届きました！ (oshipay)"
    sup_disp = supporter_name.strip() or "匿名"
    body = (
        f"{creator_name}さん\n\n"
        f"{sup_disp}さんからoshipayを通じて応援が届きました！\n\n"
        f"💰 応援金額: {amount:,}円\n"
        f"💬 メッセージ:\n{message if message else '（なし）'}\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def send_qr_email(to_email: str, acct_id: str, support_url: str, qr_bytes: bytes) -> tuple[bool, str]:
    subject = "【oshipay】QRコード・応援URLをお送りします"
    body = f"oshipayをご利用いただきありがとうございます。\n\nQRコードと応援URLをお送りします。\nSNSやイベントでファンに共有してください！\n\n📎 応援URL:\n{support_url}\n\nQRコードは添付ファイルをご確認ください。\n\n--\noshipay\n{BASE_URL}"
    attachments = [{"filename": f"oshipay_qr_{acct_id}.png", "content": list(qr_bytes)}]
    return _send_email(to_email, subject, body, attachments)

def send_welcome_email(to_email: str, display_name: str, supporter_id: str) -> tuple[bool, str]:
    subject = "【oshipay】ご登録ありがとうございます"
    dashboard_url = f"{BASE_URL}?page=supporter_dashboard&sid={supporter_id}"
    body = (
        f"{display_name} さん\n\n"
        f"oshipayへのご登録ありがとうございます！\n\n"
        f"🎫 サポーターID: {supporter_id}\n\n"
        f"このIDはログイン時に必要です。大切に保管してください。\n\n"
        f"📊 ダッシュボード（応援履歴・アカウント管理）:\n{dashboard_url}\n\n"
        f"これからも推し活をお楽しみください！\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def send_acct_id_email(to_email: str, acct_id: str, display_name: str = "") -> tuple[bool, str]:
    subject = "【oshipay】クリエイターIDのご確認"
    name_line = f"{display_name.strip()}さん\n\n" if display_name.strip() else ""
    body = (
        f"{name_line}"
        f"oshipayをご利用いただきありがとうございます。\n\n"
        f"ダッシュボードへのログインに必要なIDをお送りします。\n\n"
        f"🔑 クリエイターID: {acct_id}\n\n"
        f"このIDは大切に保管してください。\n\n"
        f"ダッシュボードURL:\n{BASE_URL}?page=dashboard&acct={acct_id}\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def get_or_create_supporter_by_email(email: str, display_name: str = "") -> tuple[str, bool]:
    """メアドからsup_idを取得または新規作成。(sup_id, is_new) を返す"""
    email_lc = email.strip().lower()
    try:
        _ex = get_db().table("supporters").select("supporter_id").eq("email", email_lc).limit(1).execute()
        if _ex.data:
            return _ex.data[0]["supporter_id"], False
    except Exception:
        pass
    new_sid = "sup_" + uuid.uuid4().hex[:12]
    _disp = display_name.strip() or email_lc.split("@")[0]
    get_db().table("supporters").insert({"supporter_id": new_sid, "email": email_lc, "display_name": _disp}).execute()
    return new_sid, True

def send_support_complete_email(to_email: str, creator_name: str, amount: int, sup_id: str, display_name: str = "") -> tuple[bool, str]:
    subject = f"【oshipay】{creator_name}さんへの応援が完了しました！"
    dashboard_url = f"{BASE_URL}?page=supporter_dashboard&sid={sup_id}"
    sup_disp = display_name.strip() or "匿名"
    body = (
        f"{sup_disp}さん\n\n"
        f"応援ありがとうございます！\n\n"
        f"✅ 応援内容\n"
        f"  クリエーター: {creator_name}\n"
        f"  応援金額: {amount:,}円\n\n"
        f"🪙 あなたのサポーターID: {sup_id}\n\n"
        f"以下のURLからダッシュボードにアクセスすると、応援履歴の確認やアカウント登録ができます。\n"
        f"{dashboard_url}\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def send_registration_otp_email(to_email: str, otp: str) -> tuple[bool, str]:
    subject = "【oshipay】メールアドレスの確認コード"
    body = f"oshipayへようこそ！\n\n以下の6桁のコードを入力して、メールアドレスを確認してください。\n\n確認コード: {otp}\n\nこのコードは5分間有効です。\n登録を依頼していない場合は、このメールを無視してください。\n\n--\noshipay\n{BASE_URL}"
    return _send_email(to_email, subject, body)

def send_pending_payment_url_email(to_email: str, creator_name: str, amount: int, pay_url: str, expires_str: str, display_name: str = "") -> tuple[bool, str]:
    subject = f"【oshipay】{creator_name}さんへの応援の支払いが可能になりました"
    sup_disp = display_name.strip() or "匿名"
    body = (
        f"{sup_disp}さん\n\n"
        f"お待たせしました！\n\n"
        f"{creator_name}さんが口座登録を完了しました。\n"
        f"以下のURLから応援金額をお支払いください。\n\n"
        f"💰 応援金額: {amount:,}円\n\n"
        f"🔗 支払いURL:\n{pay_url}\n\n"
        f"⏰ 有効期限: {expires_str}\n"
        f"期限を過ぎると自動的にキャンセルとなります。\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def send_pending_reservation_supporter_email(to_email: str, creator_name: str, amount: int, reservation_no: int = None, display_name: str = "") -> tuple[bool, str]:
    """仮予約時にサポーターへ送る確認メール"""
    subject = f"【oshipay】{creator_name}さんへの応援を受け付けました"
    res_line = f"🎫 予約番号: #{reservation_no}\n" if reservation_no else ""
    sup_disp = display_name.strip() or "匿名"
    body = (
        f"{sup_disp}さん\n\n"
        f"応援ありがとうございます！\n\n"
        f"以下の内容で仮予約を受け付けました。\n\n"
        f"{res_line}"
        f"💰 応援金額: {amount:,}円\n"
        f"👤 クリエイター: {creator_name}\n\n"
        f"現在、{creator_name}さんはまだ口座登録が完了していません。\n"
        f"口座登録が完了次第、支払いURLをお送りします。\n\n"
        f"⏰ クリエイターが72時間以内に口座登録を完了しない場合、\n"
        f"自動的にキャンセルとなります。\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def send_pending_reservation_creator_email(to_email: str, creator_name: str, amount: int, message: str, dashboard_url: str, expires_str: str = "", supporter_name: str = "") -> tuple[bool, str]:
    """仮予約時にクリエイターへ送る通知メール（メッセージ内容は口座登録完了後に開放）"""
    subject = f"【oshipay】応援の仮予約が届きました！口座登録をお急ぎください"
    msg_hint = "応援メッセージ: あり（口座登録完了後に内容を確認できます）" if message else "応援メッセージ: なし"
    exp_line = f"⏰ 口座登録期限: {expires_str}\n" if expires_str else ""
    sup_disp = supporter_name.strip() or "匿名"
    body = (
        f"{creator_name}さん\n\n"
        f"{sup_disp}さんからoshipayに応援の仮予約が届きました！\n\n"
        f"💰 金額: {amount:,}円\n"
        f"💬 {msg_hint}\n"
        f"{exp_line}\n"
        f"⚠️ 72時間以内に口座登録を完了しないと自動キャンセルになります。\n\n"
        f"👉 口座登録はこちら:\n{dashboard_url}\n\n"
        f"--\noshipay\n{BASE_URL}"
    )
    return _send_email(to_email, subject, body)

def send_merge_otp_email(to_email: str, otp: str) -> tuple[bool, str]:
    subject = "【oshipay】サポーターIDマージの確認コード"
    body = f"oshipayをご利用いただきありがとうございます。\n\nサポーターIDのマージ操作が行われました。\n以下の6桁のコードを入力してマージを完了させてください。\n\n確認コード: {otp}\n\nこのコードは5分間有効です。\nマージを依頼していない場合は、このメールを無視してください。\n\n--\noshipay\n{BASE_URL}"
    return _send_email(to_email, subject, body)

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

@st.cache_resource(ttl=0)
def get_db() -> Client:
    """Supabaseクライアントをシングルトンで返す"""
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )

def add_support(support_id: str, creator_acct: str, creator_name: str, amount: int, message: str, supporter_id: str = None, locked_rank: int = None) -> None:
    """応援記録を追加（support_idのUNIQUE制約で重複は自動無視）"""
    try:
        # creator_rank: locked_rank（72時間予約経由）があればそれを使う。なければ動的計算
        if locked_rank and int(locked_rank) > 0:
            creator_rank = int(locked_rank)
        else:
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
            "show_on_profile": True,  # プロフィールページ（creator.html）に表示
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

def register_creator(acct_id: str, password: str, email: str = "") -> tuple[bool, str]:
    try:
        data = {"acct_id": acct_id, "password_hash": hash_password(password)}
        if email:
            data["email"] = email
        get_db().table("creators").insert(data).execute()
        return True, ""
    except Exception as e:
        return False, str(e)

def set_reply(support_id: str, emoji: str, text: str, show_on_profile: bool = True) -> bool:
    """クリエイターの返信を保存"""
    try:
        resp = get_db().table("supports").update({
            "reply_emoji": emoji,
            "reply_text": text,
            "replied_at": datetime.datetime.utcnow().isoformat(),
            "show_on_profile": show_on_profile,
        }).eq("support_id", support_id).execute()
        return bool(resp.data)
    except Exception:
        # show_on_profile カラム未作成の場合はフォールバック
        try:
            resp = get_db().table("supports").update({
                "reply_emoji": emoji,
                "reply_text": text,
                "replied_at": datetime.datetime.utcnow().isoformat(),
            }).eq("support_id", support_id).execute()
            return bool(resp.data)
        except Exception:
            return False

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

def get_weekly_ranking() -> list:
    """週間ランキング用: 水曜00:00〜翌週火曜23:59 JST"""
    jst = datetime.timezone(datetime.timedelta(hours=9))
    now_jst = datetime.datetime.now(jst)
    days_since_wed = (now_jst.weekday() - 2) % 7
    week_start = (now_jst - datetime.timedelta(days=days_since_wed)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_end = week_start + datetime.timedelta(days=7) - datetime.timedelta(seconds=1)
    ws_iso = week_start.astimezone(datetime.timezone.utc).isoformat()
    we_iso = week_end.astimezone(datetime.timezone.utc).isoformat()
    resp = get_db().table("supports").select("*").gte("created_at", ws_iso).lte("created_at", we_iso).execute()
    return resp.data or []

def get_stamp_ranking() -> list:
    """スタンプランキング（全期間）"""
    try:
        from collections import Counter
        resp = get_db().table("stamps").select("creator_acct").execute()
        counter = Counter(r["creator_acct"] for r in (resp.data or []))
        return [{"creator_acct": acct, "stamp_count": cnt} for acct, cnt in counter.most_common()]
    except Exception:
        return []

def get_stamp_monthly_ranking() -> list:
    """スタンプランキング（月間）"""
    try:
        from collections import Counter
        now = datetime.datetime.now(datetime.timezone.utc)
        start = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc).isoformat()
        resp = get_db().table("stamps").select("creator_acct").gte("created_at", start).execute()
        counter = Counter(r["creator_acct"] for r in (resp.data or []))
        return [{"creator_acct": acct, "stamp_count": cnt} for acct, cnt in counter.most_common()]
    except Exception:
        return []

def get_stamp_weekly_ranking() -> list:
    """スタンプランキング（週間: 水〜火）"""
    try:
        from collections import Counter
        jst = datetime.timezone(datetime.timedelta(hours=9))
        now_jst = datetime.datetime.now(jst)
        days_since_wed = (now_jst.weekday() - 2) % 7
        week_start = (now_jst - datetime.timedelta(days=days_since_wed)).replace(hour=0, minute=0, second=0, microsecond=0)
        ws_iso = week_start.astimezone(datetime.timezone.utc).isoformat()
        resp = get_db().table("stamps").select("creator_acct").gte("created_at", ws_iso).execute()
        counter = Counter(r["creator_acct"] for r in (resp.data or []))
        return [{"creator_acct": acct, "stamp_count": cnt} for acct, cnt in counter.most_common()]
    except Exception:
        return []

def get_message_ranking_alltime() -> list:
    """応援メッセージランキング（全期間・件数）"""
    try:
        from collections import Counter
        resp = get_db().table("free_messages").select("creator_acct").execute()
        counter = Counter(r["creator_acct"] for r in (resp.data or []))
        return [{"creator_acct": acct, "msg_count": cnt} for acct, cnt in counter.most_common()]
    except Exception:
        return []

def get_message_ranking_monthly() -> list:
    """応援メッセージランキング（月間）※将来表示用"""
    try:
        from collections import Counter
        now = datetime.datetime.now(datetime.timezone.utc)
        start = datetime.datetime(now.year, now.month, 1, tzinfo=datetime.timezone.utc).isoformat()
        resp = get_db().table("free_messages").select("creator_acct").gte("created_at", start).execute()
        counter = Counter(r["creator_acct"] for r in (resp.data or []))
        return [{"creator_acct": acct, "msg_count": cnt} for acct, cnt in counter.most_common()]
    except Exception:
        return []

def get_message_ranking_weekly() -> list:
    """応援メッセージランキング（週間: 水〜火）※将来表示用"""
    try:
        from collections import Counter
        jst = datetime.timezone(datetime.timedelta(hours=9))
        now_jst = datetime.datetime.now(jst)
        days_since_wed = (now_jst.weekday() - 2) % 7
        week_start = (now_jst - datetime.timedelta(days=days_since_wed)).replace(hour=0, minute=0, second=0, microsecond=0)
        ws_iso = week_start.astimezone(datetime.timezone.utc).isoformat()
        resp = get_db().table("free_messages").select("creator_acct").gte("created_at", ws_iso).execute()
        counter = Counter(r["creator_acct"] for r in (resp.data or []))
        return [{"creator_acct": acct, "msg_count": cnt} for acct, cnt in counter.most_common()]
    except Exception:
        return []

def get_ranking_creators() -> list:
    """display_name が設定されたクリエイター一覧を取得（ランキング表示条件）"""
    try:
        resp = (
            get_db().table("creators")
            .select("acct_id,display_name,name,slug,bio,photo_url,stripe_acct_id,payout_enabled")
            .not_.is_("display_name", "null")
            .execute()
        )
        return [
            r for r in (resp.data or [])
            if r.get("display_name")
        ]
    except Exception:
        return []

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
[data-baseweb="popover"] { top: auto !important; bottom: auto !important; transform-origin: top center !important; }
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

# ── デバイスID（スタンプ重複防止用・URLパラメータで永続化）──
# ブラウザリフレッシュ後も同じIDを維持するためにURLパラメータに保存する
_qp_did = params.get("did", "")
if _qp_did:
    st.session_state["device_id"] = _qp_did
elif "device_id" not in st.session_state:
    _new_did = "dev_" + uuid.uuid4().hex[:20]
    st.session_state["device_id"] = _new_did
    st.query_params["did"] = _new_did

# ── Google OAuth コールバック処理 ──
if params.get("state") == "g_sup" and params.get("code") and not st.session_state.get("_g_done"):
    st.session_state["_g_done"] = True
    _g_info = _exchange_google_code(params["code"])
    if _g_info and _g_info.get("email"):
        _g_email = _g_info["email"].strip().lower()
        _g_sub   = str(_g_info.get("id", ""))
        _g_name  = _g_info.get("name", _g_email.split("@")[0])
        # google_sub で supporters を検索（一元管理）
        _sn_sub = get_db().table("supporters").select("*").eq("google_sub", _g_sub).limit(1).execute()
        if not _sn_sub.data:
            # supporter_accounts も念のため検索
            _sa_sub = get_db().table("supporter_accounts").select("supporter_id").eq("google_sub", _g_sub).limit(1).execute()
            if _sa_sub.data:
                _sn_sub = get_db().table("supporters").select("*").eq("supporter_id", _sa_sub.data[0]["supporter_id"]).limit(1).execute()
        if _sn_sub.data:
            # 既存アカウント（google_sub一致）→ 即ログイン
            _row  = _sn_sub.data[0]
            _disp = _row.get("display_name") or _g_name
            _mail = _row.get("email") or _g_email
            st.session_state["supporter_auth"] = {"supporter_id": _row["supporter_id"], "display_name": _disp, "email": _mail}
        else:
            # email で全テーブルを検索（スペース正規化して比較）
            _sn_em = get_db().table("supporters").select("supporter_id,display_name,email").execute()
            _seen, _candidates = set(), []
            for _r in (_sn_em.data or []):
                _r_email = (_r.get("email") or "").strip().lower()
                if _r_email == _g_email and _r["supporter_id"] not in _seen:
                    _seen.add(_r["supporter_id"])
                    _candidates.append({"supporter_id": _r["supporter_id"], "display_name": _r.get("display_name") or _r["supporter_id"]})
            if _candidates:
                st.session_state["_g_link_info"] = {
                    "email": _g_email, "sub": _g_sub, "name": _g_name, "candidates": _candidates
                }
            else:
                # 新規アカウント作成（1秒登録）
                _new_sid = "sup_" + uuid.uuid4().hex[:12]
                get_db().table("supporters").upsert({
                    "supporter_id": _new_sid, "display_name": _g_name, "email": _g_email, "google_sub": _g_sub,
                }).execute()
                get_db().table("supporter_accounts").insert({
                    "supporter_id": _new_sid, "email": _g_email, "google_sub": _g_sub,
                }).execute()
                st.session_state["supporter_auth"] = {"supporter_id": _new_sid, "display_name": _g_name, "email": _g_email}
                st.session_state["_g_new_name"] = _g_name
    else:
        st.session_state["_g_done"] = False
    st.query_params.clear()
    st.query_params["page"] = "supporter_dashboard"
    st.rerun()

# ── Google OAuth コールバック処理（クリエーター用）──
if params.get("state") == "g_creator" and params.get("code") and not st.session_state.get("_g_creator_done"):
    st.session_state["_g_creator_done"] = True
    _gc_info = _exchange_google_code(params["code"])
    if _gc_info and _gc_info.get("email"):
        _gc_email = _gc_info["email"].strip().lower()
        _gc_sub   = str(_gc_info.get("id", ""))
        _gc_name  = _gc_info.get("name", _gc_email.split("@")[0])
        # google_sub でクリエーターを検索
        _gc_sub_res = get_db().table("creators").select("acct_id,display_name,email").eq("google_sub", _gc_sub).limit(1).execute()
        if _gc_sub_res.data:
            # 既存クリエーター（google_sub一致）→ 即ログイン
            _gc_row = _gc_sub_res.data[0]
            _gc_login_id = _gc_row["acct_id"]
            st.session_state["creator_auth"] = _gc_login_id
        else:
            # emailで検索（複数ある場合は選択UI）
            _gc_em_res = get_db().table("creators").select("acct_id,display_name,email,slug").eq("email", _gc_email).execute()
            _gc_cands = _gc_em_res.data or []
            _gc_login_id = None
            if len(_gc_cands) == 1:
                # 1件のみ → google_sub を紐づけてログイン
                _gc_row = _gc_cands[0]
                get_db().table("creators").update({"google_sub": _gc_sub}).eq("acct_id", _gc_row["acct_id"]).execute()
                _gc_login_id = _gc_row["acct_id"]
                st.session_state["creator_auth"] = _gc_login_id
            elif len(_gc_cands) > 1:
                # 複数ある → 選択UIへ（acct未確定なのでdashboardトップに遷移）
                st.session_state["_gc_link_info"] = {
                    "email": _gc_email, "sub": _gc_sub, "name": _gc_name,
                    "candidates": [{"acct_id": r["acct_id"], "display_name": r.get("display_name") or r.get("slug") or r["acct_id"]} for r in _gc_cands]
                }
            else:
                # 新規クリエーター作成
                _gc_new_id = "usr_" + uuid.uuid4().hex[:16]
                get_db().table("creators").insert({
                    "acct_id": _gc_new_id, "email": _gc_email, "google_sub": _gc_sub,
                    "display_name": _gc_name, "password_hash": "",
                }).execute()
                _gc_login_id = _gc_new_id
                st.session_state["creator_auth"] = _gc_login_id
                st.session_state["_gc_new_name"] = _gc_name
    else:
        st.session_state["_gc_creator_done"] = False
        _gc_login_id = None
    st.query_params.clear()
    st.query_params["page"] = "dashboard"
    if _gc_login_id:
        st.query_params["acct"] = _gc_login_id
    st.rerun()

# ── Discord OAuth コールバック処理（サポーター用）──
if params.get("state") == "d_sup" and params.get("code") and not st.session_state.get("_d_sup_done"):
    st.session_state["_d_sup_done"] = True
    _ds_info = _exchange_discord_code(params["code"])
    if _ds_info and _ds_info.get("id"):
        _ds_sub   = str(_ds_info["id"])
        _ds_email = (_ds_info.get("email") or "").strip().lower()
        _ds_name  = _ds_info.get("global_name") or _ds_info.get("username") or _ds_email.split("@")[0] or "サポーター"
        _ds_sub_res = get_db().table("supporters").select("*").eq("discord_sub", _ds_sub).limit(1).execute()
        if _ds_sub_res.data:
            _row = _ds_sub_res.data[0]
            st.session_state["supporter_auth"] = {"supporter_id": _row["supporter_id"], "display_name": _row.get("display_name", _ds_name), "email": _row.get("email", _ds_email)}
        else:
            _candidates = []
            if _ds_email:
                _ds_em_all = get_db().table("supporters").select("supporter_id,display_name,email").execute()
                _seen = set()
                for _r in (_ds_em_all.data or []):
                    if (_r.get("email") or "").strip().lower() == _ds_email and _r["supporter_id"] not in _seen:
                        _seen.add(_r["supporter_id"])
                        _candidates.append({"supporter_id": _r["supporter_id"], "display_name": _r.get("display_name") or _r["supporter_id"]})
            if _candidates:
                st.session_state["_g_link_info"] = {"email": _ds_email, "sub": _ds_sub, "name": _ds_name, "candidates": _candidates, "provider": "discord"}
            else:
                _new_sid = "sup_" + uuid.uuid4().hex[:12]
                get_db().table("supporters").upsert({"supporter_id": _new_sid, "display_name": _ds_name, "email": _ds_email, "discord_sub": _ds_sub}).execute()
                if _ds_email:
                    try:
                        get_db().table("supporter_accounts").insert({"supporter_id": _new_sid, "email": _ds_email, "discord_sub": _ds_sub}).execute()
                    except Exception:
                        pass
                st.session_state["supporter_auth"] = {"supporter_id": _new_sid, "display_name": _ds_name, "email": _ds_email}
    else:
        st.session_state["_d_sup_done"] = False
    st.query_params.clear()
    st.query_params["page"] = "supporter_dashboard"
    st.rerun()

# ── Discord OAuth コールバック処理（クリエーター用）──
if params.get("state") == "d_creator" and params.get("code") and not st.session_state.get("_d_creator_done"):
    st.session_state["_d_creator_done"] = True
    _dc_info = _exchange_discord_code(params["code"])
    _dc_login_id = None
    if _dc_info and _dc_info.get("id"):
        _dc_sub   = str(_dc_info["id"])
        _dc_email = (_dc_info.get("email") or "").strip().lower()
        _dc_name  = _dc_info.get("global_name") or _dc_info.get("username") or _dc_email.split("@")[0] or "クリエーター"
        _dc_sub_res = get_db().table("creators").select("acct_id,display_name,email").eq("discord_sub", _dc_sub).limit(1).execute()
        if _dc_sub_res.data:
            _dc_login_id = _dc_sub_res.data[0]["acct_id"]
            st.session_state["creator_auth"] = _dc_login_id
        else:
            _dc_cands = []
            if _dc_email:
                _dc_em_res = get_db().table("creators").select("acct_id,display_name,email,slug").eq("email", _dc_email).execute()
                _dc_cands = _dc_em_res.data or []
            if len(_dc_cands) == 1:
                _dc_login_id = _dc_cands[0]["acct_id"]
                get_db().table("creators").update({"discord_sub": _dc_sub}).eq("acct_id", _dc_login_id).execute()
                st.session_state["creator_auth"] = _dc_login_id
            elif len(_dc_cands) > 1:
                st.session_state["_gc_link_info"] = {
                    "email": _dc_email, "sub": _dc_sub, "name": _dc_name, "provider": "discord",
                    "candidates": [{"acct_id": r["acct_id"], "display_name": r.get("display_name") or r.get("slug") or r["acct_id"]} for r in _dc_cands]
                }
            else:
                _dc_login_id = "usr_" + uuid.uuid4().hex[:16]
                get_db().table("creators").insert({
                    "acct_id": _dc_login_id, "email": _dc_email, "discord_sub": _dc_sub,
                    "display_name": _dc_name, "password_hash": "",
                }).execute()
                st.session_state["creator_auth"] = _dc_login_id
    st.query_params.clear()
    st.query_params["page"] = "dashboard"
    if _dc_login_id:
        st.query_params["acct"] = _dc_login_id
    st.rerun()

# ── LINE OAuth コールバック処理（サポーター用）──
if params.get("state") == "l_sup" and params.get("code") and not st.session_state.get("_l_sup_done"):
    st.session_state["_l_sup_done"] = True
    _ls_info = _exchange_line_code(params["code"])
    if _ls_info and _ls_info.get("userId"):
        _ls_sub  = str(_ls_info["userId"])
        _ls_name = _ls_info.get("displayName", "サポーター")
        _ls_sub_res = get_db().table("supporters").select("*").eq("line_sub", _ls_sub).limit(1).execute()
        if _ls_sub_res.data:
            # 既存アカウント（line_sub一致）→ 即ログイン
            _row = _ls_sub_res.data[0]
            st.session_state["supporter_auth"] = {
                "supporter_id": _row["supporter_id"],
                "display_name": _row.get("display_name") or _ls_name,
                "email":        _row.get("email", ""),
            }
        else:
            # 新規アカウント作成（LINEはメールなし）
            _new_sid = "sup_" + uuid.uuid4().hex[:12]
            get_db().table("supporters").upsert({
                "supporter_id": _new_sid,
                "display_name": _ls_name,
                "line_sub":     _ls_sub,
            }).execute()
            st.session_state["supporter_auth"] = {
                "supporter_id": _new_sid,
                "display_name": _ls_name,
                "email":        "",
            }
            st.session_state["_l_new_name"] = _ls_name
    else:
        st.session_state["_l_sup_done"] = False
    st.query_params.clear()
    st.query_params["page"] = "supporter_dashboard"
    st.rerun()

# ── Google OAuth コールバック処理（応援ページ用）──
_gsp_state = params.get("state", "")
if _gsp_state.startswith("gsp_") and params.get("code") and not st.session_state.get("_gsp_done"):
    _gsp_creator = _gsp_state[4:]
    st.session_state["_gsp_done"] = True
    _gsp_info = _exchange_google_code(params["code"])
    if _gsp_info and _gsp_info.get("email"):
        _gsp_email = _gsp_info["email"].strip().lower()
        _gsp_name  = _gsp_info.get("name", _gsp_email.split("@")[0])
        _gsp_sub   = str(_gsp_info.get("id", ""))
        _gsp_by_sub = get_db().table("supporters").select("*").eq("google_sub", _gsp_sub).limit(1).execute()
        if _gsp_by_sub.data:
            _gsp_row = _gsp_by_sub.data[0]
            st.session_state["supporter_auth"] = {
                "supporter_id": _gsp_row["supporter_id"],
                "display_name": _gsp_row.get("display_name") or _gsp_name,
                "email":        _gsp_row.get("email") or _gsp_email,
            }
        else:
            _gsp_sid, _ = get_or_create_supporter_by_email(_gsp_email, _gsp_name)
            if _gsp_sub:
                get_db().table("supporters").update({"google_sub": _gsp_sub}).eq("supporter_id", _gsp_sid).execute()
            _gsp_chk = get_db().table("supporters").select("display_name").eq("supporter_id", _gsp_sid).maybe_single().execute()
            st.session_state["supporter_auth"] = {
                "supporter_id": _gsp_sid,
                "display_name": (_gsp_chk.data or {}).get("display_name") or _gsp_name,
                "email":        _gsp_email,
            }
    st.query_params.clear()
    st.query_params["page"] = "support"
    st.query_params["creator"] = _gsp_creator
    st.rerun()

# ── Discord OAuth コールバック処理（応援ページ用）──
_dsp_state = params.get("state", "")
if _dsp_state.startswith("dsp_") and params.get("code") and not st.session_state.get("_dsp_done"):
    _dsp_creator = _dsp_state[4:]
    st.session_state["_dsp_done"] = True
    _dsp_info = _exchange_discord_code(params["code"])
    if _dsp_info and _dsp_info.get("id"):
        _dsp_sub   = str(_dsp_info["id"])
        _dsp_email = (_dsp_info.get("email") or "").strip().lower()
        _dsp_name  = _dsp_info.get("username", "サポーター")
        _dsp_by_sub = get_db().table("supporters").select("*").eq("discord_sub", _dsp_sub).limit(1).execute()
        if _dsp_by_sub.data:
            _dsp_row = _dsp_by_sub.data[0]
            st.session_state["supporter_auth"] = {
                "supporter_id": _dsp_row["supporter_id"],
                "display_name": _dsp_row.get("display_name") or _dsp_name,
                "email":        _dsp_row.get("email") or _dsp_email,
            }
        else:
            if _dsp_email:
                _dsp_sid, _ = get_or_create_supporter_by_email(_dsp_email, _dsp_name)
            else:
                _dsp_sid = "sup_" + uuid.uuid4().hex[:12]
                get_db().table("supporters").upsert({
                    "supporter_id": _dsp_sid,
                    "display_name": _dsp_name,
                }).execute()
            get_db().table("supporters").update({"discord_sub": _dsp_sub}).eq("supporter_id", _dsp_sid).execute()
            _dsp_chk = get_db().table("supporters").select("display_name").eq("supporter_id", _dsp_sid).maybe_single().execute()
            st.session_state["supporter_auth"] = {
                "supporter_id": _dsp_sid,
                "display_name": (_dsp_chk.data or {}).get("display_name") or _dsp_name,
                "email":        _dsp_email,
            }
    st.query_params.clear()
    st.query_params["page"] = "support"
    st.query_params["creator"] = _dsp_creator
    st.rerun()

# ── LINE OAuth コールバック処理（応援ページ用）──
_lsp_state = params.get("state", "")
if _lsp_state.startswith("lsp_") and params.get("code") and not st.session_state.get("_lsp_done"):
    _lsp_creator = _lsp_state[4:]
    st.session_state["_lsp_done"] = True
    _lsp_info = _exchange_line_code(params["code"])
    if _lsp_info and _lsp_info.get("userId"):
        _lsp_sub  = str(_lsp_info["userId"])
        _lsp_name = _lsp_info.get("displayName", "サポーター")
        _lsp_by_sub = get_db().table("supporters").select("*").eq("line_sub", _lsp_sub).limit(1).execute()
        if _lsp_by_sub.data:
            _lsp_row = _lsp_by_sub.data[0]
            st.session_state["supporter_auth"] = {
                "supporter_id": _lsp_row["supporter_id"],
                "display_name": _lsp_row.get("display_name") or _lsp_name,
                "email":        _lsp_row.get("email", ""),
            }
        else:
            _lsp_sid = "sup_" + uuid.uuid4().hex[:12]
            get_db().table("supporters").upsert({
                "supporter_id": _lsp_sid,
                "display_name": _lsp_name,
                "line_sub":     _lsp_sub,
            }).execute()
            st.session_state["supporter_auth"] = {
                "supporter_id": _lsp_sid,
                "display_name": _lsp_name,
                "email":        "",
            }
    st.query_params.clear()
    st.query_params["page"] = "support"
    st.query_params["creator"] = _lsp_creator
    st.rerun()

# ── LINE OAuth コールバック処理（クリエーター用）──
if params.get("state") == "l_creator" and params.get("code") and not st.session_state.get("_l_creator_done"):
    st.session_state["_l_creator_done"] = True
    _lc_info = _exchange_line_code(params["code"])
    _lc_login_id = None
    if _lc_info and _lc_info.get("userId"):
        _lc_sub  = str(_lc_info["userId"])
        _lc_name = _lc_info.get("displayName", "クリエーター")
        _lc_sub_res = get_db().table("creators").select("acct_id,display_name").eq("line_sub", _lc_sub).limit(1).execute()
        if _lc_sub_res.data:
            # 既存クリエーター → 即ログイン
            _lc_login_id = _lc_sub_res.data[0]["acct_id"]
            st.session_state["creator_auth"] = _lc_login_id
        else:
            # 新規クリエーター作成
            _lc_login_id = "usr_" + uuid.uuid4().hex[:16]
            get_db().table("creators").insert({
                "acct_id":      _lc_login_id,
                "line_sub":     _lc_sub,
                "display_name": _lc_name,
                "password_hash": "",
            }).execute()
            st.session_state["creator_auth"] = _lc_login_id
            st.session_state["_lc_new_name"] = _lc_name
    st.query_params.clear()
    st.query_params["page"] = "dashboard"
    if _lc_login_id:
        st.query_params["acct"] = _lc_login_id
    st.rerun()

# ── Googleログインボタン（st.link_button + CSS でGoogleアイコン付きスタイル）──
_GOOGLE_SVG_URI = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 48 48'%3E"
    "%3Cpath fill='%23EA4335' d='M24 9.5c3.54 0 6.71 1.22 9.21 3.6l6.85-6.85C35.9 2.38 30.47 0 24 0"
    " 14.62 0 6.51 5.38 2.56 13.22l7.98 6.19C12.43 13.72 17.74 9.5 24 9.5z'/%3E"
    "%3Cpath fill='%234285F4' d='M46.98 24.55c0-1.57-.15-3.09-.38-4.55H24v9.02h12.94c-.58 2.96-2.26"
    " 5.48-4.78 7.18l7.73 6c4.51-4.18 7.09-10.36 7.09-17.65z'/%3E"
    "%3Cpath fill='%23FBBC05' d='M10.53 28.59c-.48-1.45-.76-2.99-.76-4.59s.27-3.14.76-4.59l-7.98-6.19"
    "C.92 16.46 0 20.12 0 24c0 3.88.92 7.54 2.56 10.78l7.97-6.19z'/%3E"
    "%3Cpath fill='%2334A853' d='M24 48c6.48 0 11.93-2.13 15.89-5.81l-7.73-6c-2.18 1.48-4.97 2.31"
    "-8.16 2.31-6.26 0-11.57-4.22-13.47-9.91l-7.98 6.19C6.51 42.62 14.62 48 24 48z'/%3E%3C/svg%3E"
)

def _render_google_button(url: str, label: str = "Googleアカウントで登録 / ログイン"):
    # href に "accounts.google.com" が含まれるボタンだけ白スタイル
    st.markdown(f"""
    <style>
    [data-testid="stLinkButton"] > a[href*="accounts.google.com"] {{
        background: white url("{_GOOGLE_SVG_URI}") no-repeat 14px center / 22px 22px !important;
        padding-left: 44px !important;
        color: #3c4043 !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.3) !important;
        border: none !important;
    }}
    [data-testid="stLinkButton"] > a[href*="accounts.google.com"]:hover {{
        box-shadow: 0 4px 14px rgba(0,0,0,0.4) !important;
        background-color: #f8f8f8 !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    st.link_button(label, url, use_container_width=True)

_DISCORD_SVG_URI = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E"
    "%3Cpath fill='white' d='M20.317 4.37a19.791 19.791 0 0 0-4.885-1.515.074.074 0 0 0-.079.037"
    "c-.21.375-.444.864-.608 1.25a18.27 18.27 0 0 0-5.487 0 12.64 12.64 0 0 0-.617-1.25.077.077"
    " 0 0 0-.079-.037A19.736 19.736 0 0 0 3.677 4.37a.07.07 0 0 0-.032.027C.533 9.046-.32 13.58"
    ".099 18.057c.002.022.015.043.031.055a19.9 19.9 0 0 0 5.993 3.03.078.078 0 0 0 .084-.028"
    " 14.09 14.09 0 0 0 1.226-1.994.076.076 0 0 0-.041-.106 13.107 13.107 0 0 1-1.872-.892"
    ".077.077 0 0 1-.008-.128c.126-.094.252-.192.372-.292a.074.074 0 0 1 .077-.01c3.928 1.793"
    " 8.18 1.793 12.062 0a.074.074 0 0 1 .078.01c.12.098.246.198.373.292a.077.077 0 0 1-.006"
    ".127 12.299 12.299 0 0 1-1.873.892.077.077 0 0 0-.041.107c.36.698.772 1.362 1.225 1.993"
    "a.076.076 0 0 0 .084.028 19.839 19.839 0 0 0 6.002-3.03.077.077 0 0 0 .032-.054"
    "c.5-5.177-.838-9.674-3.549-13.66a.061.061 0 0 0-.031-.03z'/%3E%3C/svg%3E"
)

def _render_discord_button(url: str, label: str = "Discordアカウントで登録 / ログイン"):
    # href に "discord.com" が含まれるボタンだけblurpleスタイル
    st.markdown(f"""
    <style>
    [data-testid="stLinkButton"] > a[href*="discord.com"] {{
        background: #5865F2 url("{_DISCORD_SVG_URI}") no-repeat 14px center / 22px 22px !important;
        padding-left: 44px !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 8px rgba(88,101,242,0.4) !important;
        border: none !important;
    }}
    [data-testid="stLinkButton"] > a[href*="discord.com"]:hover {{
        box-shadow: 0 4px 14px rgba(88,101,242,0.6) !important;
        background-color: #4752C4 !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    st.link_button(label, url, use_container_width=True)

# LINE ロゴ（白いチャットバブル）data URI
_LINE_SVG_URI = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E"
    "%3Cpath fill='white' d='M12 2C6.48 2 2 6.01 2 11c0 3.15 1.67 5.95 4.24 7.76L6 22"
    "l3.15-1.57C10.01 20.77 11 21 12 21c5.52 0 10-4.01 10-9S17.52 2 12 2z"
    "m1 13H8v-1.5h5V15zm2-3H8v-1.5h7V12zm0-3H8V7.5h7V9z'%2F%3E%3C%2Fsvg%3E"
)

def _render_line_button(url: str, label: str = "LINEアカウントで登録 / ログイン"):
    # href に "access.line.me" が含まれるボタンだけLINEグリーンスタイル
    st.markdown(f"""
    <style>
    [data-testid="stLinkButton"] > a[href*="access.line.me"] {{
        background: #06C755 url("{_LINE_SVG_URI}") no-repeat 14px center / 22px 22px !important;
        padding-left: 44px !important;
        color: white !important;
        font-weight: 600 !important;
        font-size: 14px !important;
        border-radius: 10px !important;
        box-shadow: 0 2px 8px rgba(6,199,85,0.4) !important;
        border: none !important;
    }}
    [data-testid="stLinkButton"] > a[href*="access.line.me"]:hover {{
        box-shadow: 0 4px 14px rgba(6,199,85,0.6) !important;
        background-color: #05B34A !important;
    }}
    </style>
    """, unsafe_allow_html=True)
    st.link_button(label, url, use_container_width=True)

# LocalStorage保存用の簡易JS
def save_account_id_js(acct_id):
    if acct_id:
        st.components.v1.html(f"""
        <script>localStorage.setItem('oshipay_acct', '{acct_id}');</script>
        """, height=0)

if page == "dashboard":
    save_account_id_js(params.get("acct"))
    _cp = "oshipay-New-login" if params.get("tab") == "new" else "oshipay-login"
    components.html(f'<script>fetch("https://script.google.com/macros/s/AKfycbznxYkj5ixnK_pHkGR8LUYhEYdvSYpaiF3x4LaZy964wlu068oak1X1uuIiyqCEtGWF/exec?page={_cp}").catch(()=>{{}});</script>', height=0)

# 法務ページ用の幅調整
IS_LEGAL_PAGE = page in ["terms", "privacy", "legal"]

if page == "lp":
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: none !important; padding: 0 !important; margin: 0 !important; width: 100% !important; }</style>", unsafe_allow_html=True)
elif IS_LEGAL_PAGE:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 800px !important; margin: 0 auto !important; }</style>", unsafe_allow_html=True)
elif page in ["reply_view", "ranking", "profile", "calendar", "calendar_post", "calendar_agent", "calendar_claim"]:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 700px !important; margin: 0 auto !important; }</style>", unsafe_allow_html=True)
else:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 460px !important; margin: 0 auto !important; }</style>", unsafe_allow_html=True)

# ── 法的ページは oshipay.me の静的HTMLへリダイレクト ──
LEGAL_REDIRECT = {
    "terms":   "https://oshipay.me/terms",
    "privacy": "https://oshipay.me/privacy",
    "legal":   "https://oshipay.me/tokusho"
}

if page in LEGAL_REDIRECT:
    target = LEGAL_REDIRECT[page]
    components.html(f'<script>window.top.location.href="{target}";</script>', height=0)
    st.markdown(f'<meta http-equiv="refresh" content="0; url={target}">', unsafe_allow_html=True)
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

# ── 72時間予約 支払いページ ──
if page == "pay_pending":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    _pid  = params.get("pid", "")
    _p_email = params.get("email", "")

    if not _pid:
        st.error("支払い情報が見つかりません。"); st.stop()

    # pending_supports を取得
    try:
        _pr = get_db().table("pending_supports").select("*").eq("id", _pid).maybe_single().execute()
        _prow = _pr.data
    except Exception:
        _prow = None

    if not _prow:
        st.error("支払い情報が見つかりません。"); st.stop()

    if _prow.get("status") == "paid":
        st.success("✅ この応援はすでに支払い完了しています。")
        st.stop()

    if _prow.get("status") == "cancelled":
        st.error("❌ この応援はキャンセルされました。"); st.stop()

    # 有効期限チェック
    _pp_exp_at = _prow.get("expires_at", "")
    _pp_exp_str = "72時間以内"
    if _pp_exp_at:
        try:
            _pp_exp_dt = datetime.datetime.fromisoformat(_pp_exp_at.replace("Z", "+00:00"))
            if datetime.datetime.now(datetime.timezone.utc) > _pp_exp_dt:
                st.error("⏰ 支払い期限が過ぎています。このチケットは無効です。"); st.stop()
            _pp_exp_jst = _pp_exp_dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
            _pp_exp_str = _pp_exp_jst.strftime("%Y/%m/%d %H:%M（JST）")
        except Exception:
            pass

    _pp_creator_acct  = _prow.get("creator_acct", "")
    _pp_amount        = _prow.get("amount", 0)
    _pp_message       = _prow.get("message", "")
    _pp_sup_id        = _prow.get("supporter_id", "")
    _pp_locked_rank   = _prow.get("locked_rank") or ""
    _pp_res_no        = _prow.get("reservation_no") or ""

    # クリエイター情報取得
    try:
        _ppc = get_db().table("creators").select("display_name,name,stripe_acct_id,payout_enabled").eq("acct_id", _pp_creator_acct).maybe_single().execute()
        _ppc_data = _ppc.data or {}
    except Exception:
        _ppc_data = {}

    _ppc_name   = _ppc_data.get("display_name") or _ppc_data.get("name") or "クリエイター"
    _ppc_stripe = _ppc_data.get("stripe_acct_id", "")

    if not _ppc_stripe or not _ppc_data.get("payout_enabled"):
        st.error("クリエイターの口座情報が確認できません。"); st.stop()

    st.markdown(f'<div class="section-title">💜 {_ppc_name} への応援</div>', unsafe_allow_html=True)
    st.markdown(f"""
    <div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:14px;padding:24px;margin-bottom:16px;text-align:center;">
        <div style="font-size:12px;color:rgba(240,240,245,0.5);margin-bottom:6px;">応援金額</div>
        <div style="font-size:40px;font-weight:900;color:#f97316;">{_pp_amount:,}円</div>
        {"<div style='font-size:13px;color:rgba(240,240,245,0.6);margin-top:10px;'>💬 " + _pp_message + "</div>" if _pp_message else ""}
    </div>
    <div style="text-align:center;font-size:11px;color:#fbbf24;margin-bottom:20px;">⏰ 有効期限: {_pp_exp_str}</div>
    """, unsafe_allow_html=True)

    if st.button("💳 Stripeで支払う", type="primary", use_container_width=True):
        try:
            _pp_email_enc = urllib.parse.quote(_p_email) if _p_email else ""
            _pp_success_url = (
                f"{BASE_URL}?page=success"
                f"&s_name={urllib.parse.quote(_ppc_name)}"
                f"&s_amt={_pp_amount}"
                f"&s_acct={_pp_creator_acct}"
                f"&s_stripe_acct={_ppc_stripe}"
                f"&s_msg={urllib.parse.quote(_pp_message or '')}"
                f"&s_sid={uuid.uuid4()}"
                f"&s_sup_id={_pp_sup_id}"
                f"&s_email={_pp_email_enc}"
                f"&s_pid={_pid}"
                f"&s_locked_rank={_pp_locked_rank}"
                f"&s_res_no={_pp_res_no}"
                f"&s_session={{CHECKOUT_SESSION_ID}}"
            )
            _pp_checkout = stripe.checkout.Session.create(
                payment_method_types=["card"], mode="payment",
                line_items=[{"price_data": {"currency": "jpy", "product_data": {"name": f"{_ppc_name}への応援"}, "unit_amount": _pp_amount}, "quantity": 1}],
                success_url=_pp_success_url,
                cancel_url=f"{BASE_URL}?page=cancel",
                payment_intent_data={"application_fee_amount": int(_pp_amount * 0.1)},
                metadata={"pending_id": _pid, "supporter_id": _pp_sup_id},
                stripe_account=_ppc_stripe
            )
            st.markdown(f'<script>window.top.location.href = "{_pp_checkout.url}";</script>', unsafe_allow_html=True)
            st.link_button("💳 決済ページへ", _pp_checkout.url)
        except Exception as _ppe:
            st.error(f"エラー: {_ppe}")

    st.markdown(f'<div class="oshi-footer">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 成功ページ ──
if page == "success":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:80px;margin-bottom:20px;">🎉</div><div class="section-title">応援完了！</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">ありがとうございます！🙏</div>', unsafe_allow_html=True)

    s_name = params.get("s_name", "")
    s_amt_str = params.get("s_amt", "0")
    s_acct = params.get("s_acct", "")          # DBのacct_id（支払い記録用）
    s_stripe_acct = params.get("s_stripe_acct", "") or s_acct  # StripeアカウントID（メール送信用、後方互換でs_acctをフォールバック）
    s_msg = params.get("s_msg", "")
    s_sid = params.get("s_sid", "")
    s_sup_id   = params.get("s_sup_id", "")
    s_sup_name = params.get("s_sup_name", "")
    s_email    = params.get("s_email", "")
    s_session_id = params.get("s_session", "")
    s_pid         = params.get("s_pid", "")          # pending_supports.id（72時間予約経由の場合）
    s_locked_rank = params.get("s_locked_rank", "")  # 予約順メダル保証用ランク
    s_res_no      = params.get("s_res_no", "")       # 仮番号（表示用）

    # ── 応援金額のパース ──
    try:
        s_amt = int(s_amt_str)
    except ValueError:
        s_amt = 0

    # ── ① sup_idは常に作成（匿名でも必ず記録）──
    if s_sup_id:
        try:
            get_db().table("supporters").insert({
                "supporter_id": s_sup_id,
                "display_name": s_sup_name or "",
                "email": s_email.strip().lower() if s_email else None
            }).execute()
        except Exception:
            # 既存レコードの場合は display_name / email だけ更新
            try:
                _upd = {}
                if s_sup_name: _upd["display_name"] = s_sup_name
                if s_email:    _upd["email"] = s_email.strip().lower()
                if _upd:
                    get_db().table("supporters").update(_upd).eq("supporter_id", s_sup_id).execute()
            except Exception:
                pass

    # ── 72時間予約経由の場合: pending_supports を paid に更新 ──
    if s_pid:
        try:
            get_db().table("pending_supports").update({"status": "paid"}).eq("id", s_pid).execute()
        except Exception:
            pass

    # ── 応援完了メールをサポーターへ送信 ──
    if s_email and s_sup_id and s_name and s_amt > 0:
        try:
            send_support_complete_email(s_email.strip().lower(), s_name, s_amt, s_sup_id, display_name=s_sup_name)
        except Exception:
            pass

    # ── Stripeセッションからメアドも補完（Apple Pay等でs_emailがない場合のフォールバック）──
    if s_session_id and s_sup_id and s_stripe_acct and not s_email:
        try:
            _stripe_sess = stripe.checkout.Session.retrieve(s_session_id, stripe_account=s_stripe_acct)
            _stripe_email = (_stripe_sess.customer_details.email if _stripe_sess.customer_details else None)
            if _stripe_email:
                _stripe_email = _stripe_email.strip().lower()
                get_db().table("supporters").update({"email": _stripe_email}).eq("supporter_id", s_sup_id).is_("email", "null").execute()
                send_support_complete_email(_stripe_email, s_name, s_amt, s_sup_id, display_name=s_sup_name)
        except Exception:
            pass

    # ── 応援記録を Supabase に保存（冪等: s_sid があれば1回のみ） ──
    if s_sid and s_acct and s_amt > 0:
        _locked_rank_int = int(s_locked_rank) if s_locked_rank and str(s_locked_rank).isdigit() else None
        add_support(s_sid, s_acct, s_name, s_amt, s_msg, s_sup_id, locked_rank=_locked_rank_int)

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
    if s_stripe_acct and s_stripe_acct.startswith("acct_") and s_name and s_amt > 0:
        try:
            acct_info = stripe.Account.retrieve(s_stripe_acct)
            creator_email = acct_info.get("email", "")
            if creator_email:
                ok, err = send_support_email(creator_email, s_name, s_amt, s_msg, supporter_name=s_sup_name)
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
            f'<a href="{BASE_URL}?page=supporter_dashboard&sid={s_sup_id}" target="_top" '
            f'style="display:inline-block;font-size:13px;font-weight:700;color:#c4b5fd;'
            f'text-decoration:none;background:rgba(139,92,246,0.15);'
            f'border:1px solid rgba(139,92,246,0.4);border-radius:12px;padding:10px 20px;">'
            f'🦸 このIDでアカウント登録する</a></div>',
            unsafe_allow_html=True
        )
    portfolio_url = f"{BASE_URL}?page=portfolio&id={s_sup_id}" if s_sup_id else BASE_URL
    share_text = f"{s_name}にoshipayで応援したよ！\n#oshipay\n{portfolio_url}"
    st.link_button("𝕏 でシェア", f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}", use_container_width=True)

    # ── プロフィールに戻る / 閉じるボタン ──
    _back_url = f"{BASE_URL}?page=support&creator={s_acct}" if s_acct else BASE_URL
    _btn_col1, _btn_col2 = st.columns(2)
    with _btn_col1:
        st.link_button("← プロフィールに戻る", _back_url, use_container_width=True)
    with _btn_col2:
        components.html("""
        <button onclick="window.close()" style="
            width:100%;padding:10px 0;border-radius:8px;border:1px solid rgba(139,92,246,0.4);
            background:rgba(139,92,246,0.12);color:#c4b5fd;font-size:14px;font-weight:700;
            cursor:pointer;font-family:inherit;">
            ✕ 閉じる
        </button>
        """, height=46)

    st.markdown(f'<div style="text-align:center;margin-top:10px;"><a href="{BASE_URL}?page=my_history" target="_top" style="font-size:12px;color:rgba(240,240,245,0.4); text-decoration:underline;">（ブラウザ限定）簡易履歴を見る</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="oshi-footer">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="https://oshipay.me/terms" target="_blank">利用規約</a><a href="https://oshipay.me/privacy" target="_blank">プライバシーポリシー</a><a href="https://oshipay.me/tokusho" target="_blank">特定商取引法</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 応援証明ページ（サポーター向け）──
if page == "my_support":
    s_sid = params.get("sid", "")
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
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
        _sup_id_val = record["supporter_id"]
        st.markdown(
            f'<div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.2);'
            f'border-radius:12px;padding:14px;margin:12px 0;text-align:center;">'
            f'<div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:4px;">サポーターID</div>'
            f'<div style="font-size:16px;font-weight:700;color:#c4b5fd;font-family:monospace;">{_sup_id_val}</div>'
            f'<div style="font-size:10px;color:rgba(240,240,245,0.35);margin-top:4px;">'
            f'<a href="{BASE_URL}?page=supporter_dashboard" target="_top" style="color:#c4b5fd;text-decoration:underline;">'
            f'アカウント登録</a>するとコインが積み重なります</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        if st.button("🔑 サポーターログイン", use_container_width=True, key="sup_login_btn"):
            st.session_state["_sup_prefill_id"] = _sup_id_val
            st.query_params["page"] = "supporter_dashboard"
            st.query_params["sid"]  = _sup_id_val
            st.rerun()
    st.markdown(f'<div style="text-align:center;margin-top:16px;"><a href="{BASE_URL}?page=coin_preview" target="_top" style="font-size:11px;color:rgba(240,240,245,0.3);text-decoration:underline;">🪙 コイン全色プレビューを見る</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="oshi-footer" style="margin-top:12px;">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="https://oshipay.me/terms" target="_blank">利用規約</a><a href="https://oshipay.me/privacy" target="_blank">プライバシーポリシー</a><a href="https://oshipay.me/tokusho" target="_blank">特定商取引法</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 返信ダッシュボードページ（クリエイター向け）──
if page == "reply_view":
    rv_acct = params.get("acct", "")
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
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
        if st.button("🔓 ログイン", type="primary", use_container_width=True):
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
    _rv_col1.link_button("🌐 プロフィールを見る", _microsite_url, use_container_width=True, type="secondary")
    if _rv_col2.button("✏️ プロフィール編集", use_container_width=True, type="secondary"):
        st.session_state["creator_auth"] = rv_acct
        st.query_params["page"] = "dashboard"
        st.query_params["acct"] = rv_acct
        st.rerun()

    supports = get_supports_for_creator(rv_acct)

    # supporter display_name マップを事前取得
    _rv_all_sup_ids = list({s["supporter_id"] for s in supports if s.get("supporter_id")})
    _rv_sup_name_map = get_supporters_map(_rv_all_sup_ids) if _rv_all_sup_ids else {}

    # pending_supports も取得（口座登録済みなら全内容開放）
    _rv_pending = []
    try:
        import datetime as _dt2
        _rv_now = _dt2.datetime.now(_dt2.timezone.utc).isoformat()
        _rv_pr = get_db().table("pending_supports").select("*").eq("creator_acct", rv_acct).eq("status", "pending").gte("expires_at", _rv_now).execute()
        _rv_pending = _rv_pr.data or []
    except Exception:
        _rv_pending = []

    if not supports and not _rv_pending:
        st.markdown("""
        <div style="background:rgba(255,255,255,0.03);border:1px dashed rgba(255,255,255,0.12);
                    border-radius:12px;padding:32px;text-align:center;margin-top:20px;">
            <div style="font-size:48px;margin-bottom:12px;">📭</div>
            <div style="color:rgba(240,240,245,0.5);font-size:14px;">まだ応援が届いていません</div>
        </div>
        """, unsafe_allow_html=True)
        st.stop()

    # ── pending_supports（送金待ち）を先に表示 ──
    if _rv_pending:
        _rv_pending_total = sum(r["amount"] for r in _rv_pending)
        st.markdown(f"""
        <div style="background:rgba(74,222,128,0.07);border:1px solid rgba(74,222,128,0.3);border-radius:14px;padding:16px 20px;margin-bottom:16px;">
            <div style="font-size:13px;color:#4ade80;font-weight:700;margin-bottom:4px;">💰 送金待ち応援（{len(_rv_pending)}件 / 合計 {_rv_pending_total:,}円）</div>
            <div style="font-size:11px;color:rgba(240,240,245,0.5);">ファンに連絡して入金確認後に確定します。72時間以内に振り込みない場合には強制キャンセルとなります。</div>
        </div>
        """, unsafe_allow_html=True)
        import html as _html_mod2
        for _rvp in _rv_pending:
            _rvp_msg  = _html_mod2.escape(str(_rvp.get("message") or "（メッセージなし）"))
            _rvp_amt  = f'{_rvp["amount"]:,}'
            _rvp_date = (_rvp.get("created_at") or "")[:16].replace("T", " ")
            _rvp_exp  = (_rvp.get("expires_at") or "")[:16].replace("T", " ")
            st.markdown(f"""
            <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(74,222,128,0.2);border-radius:14px;padding:16px;margin-bottom:10px;">
                <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                    <div style="font-size:20px;font-weight:900;color:#f97316;">{_rvp_amt}円</div>
                    <span style="font-size:11px;color:#fbbf24;background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.3);border-radius:9999px;padding:3px 10px;">⏳ 送金待ち</span>
                </div>
                <div style="font-size:13px;color:rgba(240,240,245,0.8);margin-bottom:6px;">💬 {_rvp_msg}</div>
                <div style="font-size:11px;color:rgba(240,240,245,0.35);margin-top:4px;">登録日: {_rvp_date}　⚠️ 期限: {_rvp_exp} UTC</div>
            </div>
            """, unsafe_allow_html=True)
        st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)

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
        _rv_sup_id = record.get("supporter_id", "")
        _rv_sup_disp = (_rv_sup_name_map.get(_rv_sup_id) or "").strip() or "匿名"

        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);
                    border-radius:14px;padding:18px;margin-bottom:14px;">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <div style="font-size:22px;font-weight:900;
                            background:linear-gradient(135deg,#8b5cf6,#ec4899);
                            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                    {amt_disp}円
                </div>
                <span style="font-size:11px;font-weight:700;color:{badge_color};
                             background:rgba(255,255,255,0.06);border-radius:9999px;
                             padding:3px 10px;border:1px solid {badge_color}40;">
                    {badge_text}
                </span>
            </div>
            <div style="font-size:14px;font-weight:700;color:#c4b5fd;margin-bottom:8px;">
                👤 {_rv_sup_disp}さん
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

            show_on_profile = st.checkbox(
                "💬 このメッセージをプロフィール画面に表示する",
                value=bool(record.get("show_on_profile", True)),
                key=f"sop_{sid}",
            )

            if st.button("📨 送信する", key=f"send_{sid}", type="primary"):
                ok = set_reply(sid, chosen_emoji, reply_text, show_on_profile=show_on_profile)
                if ok:
                    st.session_state["reply_success_msg"] = "返信を保存しました！"
                    st.rerun()
                else:
                    st.error("保存に失敗しました。")

            # 応援証明リンク
            proof_url = f"{BASE_URL}?page=my_support&sid={sid}"
            st.markdown(f'<div style="margin-top:8px;font-size:12px;color:rgba(240,240,245,0.4);">🔗 <a href="{proof_url}" target="_top" style="color:#8b5cf6;">応援証明ページを確認</a></div>', unsafe_allow_html=True)

    st.markdown(f'<div class="oshi-footer" style="margin-top:28px;">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.stop()

# ── 応援履歴ページ（サポーター向け）──
if page == "my_history":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
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
    st.markdown(f'<div class="oshi-footer" style="margin-top:24px;">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.stop()

# ── キャンセル ──
if page == "cancel":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:80px;margin-bottom:20px;">🤔</div><div class="section-title">キャンセルしました</div>', unsafe_allow_html=True)
    st.stop()

# ── テストページ（開発用）──
if page == "test":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
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
        rv_url = f"{BASE_URL}?page=dashboard&acct={t_acct}"
        st.success(f"追加完了！ `{new_sid[:8]}...`")
        b1, b2 = st.columns(2)
        b1.link_button("🏅 応援証明を確認", my_url, use_container_width=True)
        b2.link_button("💌 クリエイターダッシュボード", rv_url, use_container_width=True)

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
            rv_url  = f"{BASE_URL}?page=dashboard&acct={s['creator_acct']}"
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
                <a href="{rv_url}" target="_top" style="color:#8b5cf6;font-size:12px;">💌 クリエイターDL</a>
            </div>
            """, unsafe_allow_html=True)

        if st.button("🗑️ テストデータを全消去", type="secondary"):
            delete_all_supports()
            st.rerun()

    st.stop()

# ── 公開統計（iframe埋め込み用）──
if page == "stats_embed":
    st.markdown("<style>.stMainBlockContainer,.block-container{max-width:none!important;padding:0!important;margin:0!important;}</style>", unsafe_allow_html=True)
    try:
        _se_creators = get_ranking_creators()
        _se_with     = sum(1 for c in _se_creators if c.get("payout_enabled"))
        _se_without  = len(_se_creators) - _se_with
        _se_supports = get_all_time_ranking()
        _se_total    = sum(int(s.get("amount", 0)) for s in _se_supports)
    except Exception:
        _se_creators, _se_with, _se_without, _se_total = [], 0, 0, 0
    _se_count = len(_se_creators)
    st.markdown(f"""
    <div style="font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
                background:#0f0a1e;padding:20px;min-height:100vh;box-sizing:border-box;">
      <div style="display:grid;grid-template-columns:repeat(2,1fr);gap:12px;max-width:480px;margin:0 auto;">
        <div style="text-align:center;padding:20px 12px;background:rgba(139,92,246,0.12);
                    border:1px solid rgba(139,92,246,0.35);border-radius:14px;">
          <div style="font-size:36px;font-weight:900;color:#e0d7ff;line-height:1;">{_se_count}</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:6px;letter-spacing:0.05em;">登録クリエイター</div>
        </div>
        <div style="text-align:center;padding:20px 12px;background:rgba(16,185,129,0.1);
                    border:1px solid rgba(16,185,129,0.3);border-radius:14px;">
          <div style="font-size:36px;font-weight:900;color:#6ee7b7;line-height:1;">¥{_se_total:,}</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:6px;letter-spacing:0.05em;">応援金合計</div>
        </div>
        <div style="text-align:center;padding:20px 12px;background:rgba(99,102,241,0.1);
                    border:1px solid rgba(99,102,241,0.3);border-radius:14px;">
          <div style="font-size:36px;font-weight:900;color:#a5b4fc;line-height:1;">{_se_with}</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:6px;letter-spacing:0.05em;">受取口座登録済み</div>
        </div>
        <div style="text-align:center;padding:20px 12px;background:rgba(251,191,36,0.08);
                    border:1px solid rgba(251,191,36,0.2);border-radius:14px;">
          <div style="font-size:36px;font-weight:900;color:#fcd34d;line-height:1;">{_se_without}</div>
          <div style="font-size:11px;color:rgba(255,255,255,0.45);margin-top:6px;letter-spacing:0.05em;">口座未登録（見込み）</div>
        </div>
      </div>
      <div style="text-align:center;margin-top:14px;font-size:10px;color:rgba(255,255,255,0.2);">
        リアルタイムデータ · powered by oshipay
      </div>
    </div>
    """, unsafe_allow_html=True)
    st.stop()

# ── ランキング（週間 / 月間 / 全期間）──
if page == "ranking":
    components.html('<script>fetch("https://script.google.com/macros/s/AKfycbznxYkj5ixnK_pHkGR8LUYhEYdvSYpaiF3x4LaZy964wlu068oak1X1uuIiyqCEtGWF/exec?page=oshipay-ranking").catch(()=>{});</script>', height=0)
    now = datetime.datetime.now(datetime.timezone.utc)
    month_label = f"{now.year}年{now.month}月"
    # 週間ラベル計算（水曜00:00 JST 〜 翌火曜23:59 JST）
    _jst = datetime.timezone(datetime.timedelta(hours=9))
    _now_jst = datetime.datetime.now(_jst)
    _days_since_wed = (_now_jst.weekday() - 2) % 7
    _wk_start = (_now_jst - datetime.timedelta(days=_days_since_wed)).replace(hour=0, minute=0, second=0, microsecond=0)
    _wk_end   = _wk_start + datetime.timedelta(days=6)
    week_label = f"{_wk_start.month}/{_wk_start.day}(水)〜{_wk_end.month}/{_wk_end.day}(火)"

    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">🏆 応援ランキング</div>', unsafe_allow_html=True)

    def render_ranking(supports, total_label, base_creators=None):
        # ① プロフィール完成クリエイターをベースに全員ランキング入り
        creator_map = {}
        if base_creators:
            for _bc in base_creators:
                _bid = _bc["acct_id"]
                _bname = _bc.get("display_name") or _bc.get("name") or _bc.get("slug") or _bid
                # payout_enabled=True のみ口座登録済み扱い
                _bhas = bool(_bc.get("payout_enabled"))
                creator_map[_bid] = {
                    "name": _bname, "acct": _bid, "total": 0, "count": 0,
                    "first_at": "", "has_reply": False, "supports": [],
                    "photo_url": _bc.get("photo_url") or "", "has_stripe": _bhas,
                }

        if not supports and not creator_map:
            st.markdown('<div style="text-align:center;padding:60px 20px;color:rgba(255,255,255,0.35);font-size:14px;">まだ応援データがありません 🌱</div>', unsafe_allow_html=True)
            return

        # supports データを creator_map に加算
        for s in supports:
            acct = s["creator_acct"]
            if acct not in creator_map:
                creator_map[acct] = {"name": s["creator_name"], "acct": acct, "total": 0, "count": 0, "first_at": s.get("created_at",""), "has_reply": False, "supports": [], "photo_url": "", "has_stripe": False}
            creator_map[acct]["total"] += s["amount"]
            creator_map[acct]["count"] += 1
            if s.get("created_at","") < creator_map[acct]["first_at"] or not creator_map[acct]["first_at"]:
                creator_map[acct]["first_at"] = s.get("created_at","")
            if s.get("reply_emoji") or s.get("reply_text"):
                creator_map[acct]["has_reply"] = True
            creator_map[acct]["supports"].append(s)

        # base_creators に含まれないクリエイターの情報をDBから補完
        try:
            _base_ids = {r["acct_id"] for r in (base_creators or [])}
            _extra_ids = [c["acct"] for c in creator_map.values() if c["acct"] not in _base_ids]
            if _extra_ids:
                _cr_rows = get_db().table("creators").select("acct_id,display_name,name,slug,photo_url,payout_enabled").in_("acct_id", _extra_ids).execute()
                _cr_name_map = {r["acct_id"]: r for r in (_cr_rows.data or [])}
                for c in creator_map.values():
                    if c["acct"] in _extra_ids:
                        _cr = _cr_name_map.get(c["acct"], {})
                        c["name"] = _cr.get("display_name") or _cr.get("name") or _cr.get("slug") or c["name"]
                        c["photo_url"] = _cr.get("photo_url") or ""
                        c["has_stripe"] = bool(_cr.get("payout_enabled"))
        except Exception:
            pass

        # ② 口座登録済みが上位・未登録が下位（それぞれ amount desc）
        ranked = sorted(creator_map.values(), key=lambda x: (
            not x.get("has_stripe", False),  # 未登録を後ろ
            -x["total"],
            x["first_at"],
            -x["count"],
            not x["has_reply"],
        ))

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
            _no_stripe_badge = (
                '<span style="font-size:10px;padding:2px 7px;border-radius:10px;background:rgba(100,100,100,0.2);'
                'color:rgba(240,240,245,0.4);border:1px solid rgba(255,255,255,0.1);margin-left:6px;white-space:nowrap;">受取口座未登録</span>'
            ) if not creator.get("has_stripe", True) else ""
            card_html = (
                f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:16px 20px;margin-bottom:12px;cursor:pointer;" onclick="window.open(\'{creator_url}\', \'_blank\')">'
                f'<div style="display:flex;align-items:center;gap:10px;margin-bottom:12px;">'
                f'<span style="font-size:22px;min-width:28px;text-align:center;">{medal}</span>'
                f'{_avatar_html}'
                f'<div style="flex:1;min-width:0;"><a href="{creator_url}" target="_blank" style="font-size:16px;font-weight:900;color:#f0f0f5;text-decoration:none;">{creator["name"]}</a>{_no_stripe_badge}</div>'
                f'<span style="font-size:11px;color:rgba(240,240,245,0.4);">{total_label}</span>'
                f'<span style="font-size:18px;font-weight:900;color:#f97316;">{creator["total"]:,}</span>'
                f'</div>'
                f'{sup_rows_html}'
                f'</div>'
            )
            st.markdown(card_html, unsafe_allow_html=True)

    tab_alltime, tab_monthly, tab_weekly, tab_msgs = st.tabs([
        "🌟 全期間", f"📅 月間 ({month_label})", f"📆 週間 ({week_label})", "💬 応援メッセージ"
    ])

    # プロフィール完成クリエイター一覧（全タブ共通）
    try:
        _base_creators = get_ranking_creators()
    except Exception:
        _base_creators = []

    with tab_alltime:
        try:
            render_ranking(get_all_time_ranking(), "全期間合計", base_creators=_base_creators)
        except Exception:
            st.error("現在データベースが起動中です。数分後にページを再読み込みしてください。")
            st.stop()

    with tab_monthly:
        try:
            render_ranking(get_monthly_ranking(), "月間合計", base_creators=_base_creators)
        except Exception:
            st.error("現在データベースが起動中です。数分後にページを再読み込みしてください。")
            st.stop()

    with tab_weekly:
        try:
            render_ranking(get_weekly_ranking(), "週間合計", base_creators=_base_creators)
        except Exception:
            st.error("現在データベースが起動中です。数分後にページを再読み込みしてください。")
            st.stop()

    def _render_msg_ranking(msg_data):
        """応援メッセージランキングリストを描画するヘルパー"""
        if not msg_data:
            st.markdown('<div style="text-align:center;padding:40px 20px;color:rgba(255,255,255,0.35);font-size:14px;">まだ応援メッセージがありません 🌱</div>', unsafe_allow_html=True)
            return
        _m_acct_ids = [d["creator_acct"] for d in msg_data]
        try:
            _m_cr_rows = get_db().table("creators").select("acct_id,display_name,name,slug,photo_url,payout_enabled").in_("acct_id", _m_acct_ids).execute()
            _m_cr_map  = {r["acct_id"]: r for r in (_m_cr_rows.data or [])}
        except Exception:
            _m_cr_map = {}
        _m_medals = ["🥇", "🥈", "🥉"]
        for _mi, _md in enumerate(msg_data):
            _ma    = _md["creator_acct"]
            _mcnt  = _md["msg_count"]
            _mcr   = _m_cr_map.get(_ma, {})
            _mname = _mcr.get("display_name") or _mcr.get("name") or _mcr.get("slug") or _ma
            _mphoto= _mcr.get("photo_url") or ""
            _mmedal= _m_medals[_mi] if _mi < 3 else f"{_mi+1}位"
            _murl  = f"https://oyajibuki.github.io/OshiPay/creator.html?id={_ma}"
            _has_stripe_m = bool(_mcr.get("payout_enabled"))
            _no_stripe_badge_m = (
                '<span style="font-size:10px;color:#94a3b8;background:rgba(148,163,184,0.1);'
                'border:1px solid rgba(148,163,184,0.25);border-radius:9999px;padding:2px 7px;'
                'margin-left:6px;white-space:nowrap;">受取口座未登録</span>'
                if not _has_stripe_m else ""
            )
            _mav = (f'<img src="{_mphoto}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,0.15);flex-shrink:0;">'
                    if _mphoto else
                    '<div style="width:40px;height:40px;border-radius:50%;background:rgba(139,92,246,0.2);border:2px solid rgba(139,92,246,0.3);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;">🎤</div>')
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:14px 18px;margin-bottom:10px;">'
                f'<div style="display:flex;align-items:center;gap:10px;">'
                f'<span style="font-size:22px;min-width:28px;text-align:center;">{_mmedal}</span>'
                f'{_mav}'
                f'<div style="flex:1;min-width:0;">'
                f'<a href="{_murl}" target="_blank" style="font-size:16px;font-weight:900;color:#f0f0f5;text-decoration:none;">{_mname}</a>'
                f'{_no_stripe_badge_m}'
                f'</div>'
                f'<span style="font-size:18px;font-weight:900;color:#c4b5fd;">{_mcnt} 💬</span>'
                f'</div></div>',
                unsafe_allow_html=True
            )

    with tab_msgs:
        try:
            _render_msg_ranking(get_message_ranking_alltime())
        except Exception:
            st.error("現在データベースが起動中です。数分後にページを再読み込みしてください。")
            st.stop()

    # ── 以下は将来表示用（スタンプ・週間・月間ランキング）──
    def _render_stamp_list(stamp_data):
        """スタンプランキングリストを描画するヘルパー（将来表示用）"""
        if not stamp_data:
            st.markdown('<div style="text-align:center;padding:40px 20px;color:rgba(255,255,255,0.35);font-size:14px;">まだスタンプデータがありません 🌱</div>', unsafe_allow_html=True)
            return
        _s_acct_ids = [d["creator_acct"] for d in stamp_data]
        try:
            _s_cr_rows = get_db().table("creators").select("acct_id,display_name,name,slug,photo_url,payout_enabled").in_("acct_id", _s_acct_ids).execute()
            _s_cr_map  = {r["acct_id"]: r for r in (_s_cr_rows.data or [])}
        except Exception:
            _s_cr_map = {}
        _s_medals = ["🥇", "🥈", "🥉"]
        for _si, _sd in enumerate(stamp_data):
            _sa    = _sd["creator_acct"]
            _scnt  = _sd["stamp_count"]
            _scr   = _s_cr_map.get(_sa, {})
            _sname = _scr.get("display_name") or _scr.get("name") or _scr.get("slug") or _sa
            _sphoto= _scr.get("photo_url") or ""
            _smedal= _s_medals[_si] if _si < 3 else f"{_si+1}位"
            _surl  = f"https://oyajibuki.github.io/OshiPay/creator.html?id={_sa}"
            _has_stripe_s = bool(_scr.get("payout_enabled"))
            _no_stripe_badge_s = (
                '<span style="font-size:10px;color:#94a3b8;background:rgba(148,163,184,0.1);'
                'border:1px solid rgba(148,163,184,0.25);border-radius:9999px;padding:2px 7px;'
                'margin-left:6px;white-space:nowrap;">受取口座未登録</span>'
                if not _has_stripe_s else ""
            )
            _sav = (f'<img src="{_sphoto}" style="width:40px;height:40px;border-radius:50%;object-fit:cover;border:2px solid rgba(255,255,255,0.15);flex-shrink:0;">'
                    if _sphoto else
                    '<div style="width:40px;height:40px;border-radius:50%;background:rgba(139,92,246,0.2);border:2px solid rgba(139,92,246,0.3);display:flex;align-items:center;justify-content:center;font-size:18px;flex-shrink:0;">🎤</div>')
            st.markdown(
                f'<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:14px 18px;margin-bottom:10px;">'
                f'<div style="display:flex;align-items:center;gap:10px;">'
                f'<span style="font-size:22px;min-width:28px;text-align:center;">{_smedal}</span>'
                f'{_sav}'
                f'<div style="flex:1;min-width:0;">'
                f'<a href="{_surl}" target="_blank" style="font-size:16px;font-weight:900;color:#f0f0f5;text-decoration:none;">{_sname}</a>'
                f'{_no_stripe_badge_s}'
                f'</div>'
                f'<span style="font-size:18px;font-weight:900;color:#c4b5fd;">{_scnt} 💜</span>'
                f'</div></div>',
                unsafe_allow_html=True
            )

    # フッター（Discord招待）
    footer_html = (
        f'<div style="margin-top:40px;padding:20px 24px 12px;background:rgba(88,101,242,0.08);border:1px solid rgba(88,101,242,0.3);border-radius:16px;text-align:center;">'
        f'<div style="font-size:20px;font-weight:900;color:#818cf8;margin-bottom:6px;">あなたの推しをOshipayに呼ぼう！</div>'
        f'<div style="font-size:12px;color:rgba(240,240,245,0.55);margin-bottom:12px;">Discordでリクエスト募集中！リクエスト多数の推しにはoshipayからも導入相談します</div>'
        f'</div>'
    )
    st.markdown(footer_html, unsafe_allow_html=True)
    _fc1, _fc2 = st.columns(2)
    with _fc1:
        st.link_button("🏠 TOPページ", LP_URL, use_container_width=True)
    with _fc2:
        st.link_button("🟣 Discordで呼ぶ", "https://discord.gg/3k2AjuR8", use_container_width=True)
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
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
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
    col1.link_button("利用規約", "https://oshipay.me/terms", use_container_width=True)
    col2.link_button("プライバシー", "https://oshipay.me/privacy", use_container_width=True)
    col3.link_button("特定商取引法", "https://oshipay.me/tokusho", use_container_width=True)
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
_creator_stripe_acct = ""  # Stripe Connect用アカウントID
_creator_payout_enabled = False  # 口座登録完了フラグ（スライダー上限判定用）
if _creator_param and not support_user:
    try:
        _cr_resp = get_db().table("creators").select(
            "acct_id,display_name,name,photo_url,stripe_acct_id,payout_enabled"
        ).or_(f"slug.eq.{_creator_param},acct_id.eq.{_creator_param}").maybe_single().execute()
        if _cr_resp.data:
            _cr = _cr_resp.data
            support_user  = _cr.get("acct_id", _creator_param)
            connect_acct  = _cr.get("acct_id", _creator_param)
            support_name  = _cr.get("display_name") or _cr.get("name") or _creator_param
            support_photo = _cr.get("photo_url") or ""
            _creator_stripe_acct = _cr.get("stripe_acct_id") or ""
            _creator_payout_enabled = bool(_cr.get("payout_enabled"))
        else:
            support_user = None
    except Exception:
        support_user = None
elif support_user:
    try:
        _cr_resp2 = get_db().table("creators").select("photo_url,stripe_acct_id,payout_enabled").or_(
            f"slug.eq.{support_user},acct_id.eq.{support_user}"
        ).maybe_single().execute()
        support_photo = (_cr_resp2.data or {}).get("photo_url") or ""
        _creator_stripe_acct = (_cr_resp2.data or {}).get("stripe_acct_id") or ""
        _creator_payout_enabled = bool((_cr_resp2.data or {}).get("payout_enabled"))
    except Exception:
        pass

# 実際に Stripe Connect で使うアカウントIDを決定
# 1) stripe_acct_id 列が設定済み → 使う（新方式 usr_）
# 2) acct_ プレフィックス → acct_id そのものが Stripe ID（旧方式）
# 3) usr_ でstripe未登録 → 口座未登録
if _creator_stripe_acct:
    _stripe_connect_acct = _creator_stripe_acct
elif connect_acct and connect_acct.startswith("acct_"):
    _stripe_connect_acct = connect_acct
else:
    _stripe_connect_acct = ""
_creator_has_stripe = bool(_stripe_connect_acct)
# スライダー上限・表示文言は payout_enabled で判定（stripe_acct_idがあっても口座未完了はNG）
_creator_bank_ready = _creator_payout_enabled

if page == "support" and _creator_param and not support_user:
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.error("クリエイターが見つかりませんでした。URLを確認してください。")
    st.link_button("🏠 トップへ戻る", LP_URL, use_container_width=True)
    st.stop()

if page == "support" and support_user:
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    if support_photo:
        st.markdown(f'<div style="width:72px;height:72px;border-radius:50%;margin:0 auto 14px;box-shadow:0 0 30px rgba(139,92,246,0.25);overflow:hidden;border:2px solid rgba(139,92,246,0.3);"><img src="{support_photo}" style="width:100%;height:100%;object-fit:cover;"></div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="support-avatar">{support_icon}</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="support-name">{support_name or "Creator"}</div><div class="support-label">を応援しよう</div>', unsafe_allow_html=True)

    # ── 無料応援メッセージ（1日1通・ログイン必須）──
    _FREE_MSGS = ["応援してます！", "頑張ってください。", "大好きです！", "いつもありがとう！", "元気もらってます！"]
    _msg_sup_auth = st.session_state.get("supporter_auth", {})
    _msg_sup_id   = _msg_sup_auth.get("supporter_id", "")
    # 開発用: ?dev_login=1 でログイン済み状態を模倣（ローカル確認用）
    if not _msg_sup_id and params.get("dev_login") == "1":
        _msg_sup_auth = {"supporter_id": "dev_test_001", "display_name": "テストユーザー"}
        _msg_sup_id   = "dev_test_001"
    try:
        _msg_total_resp = get_db().table("free_messages").select("id", count="exact").eq("creator_acct", connect_acct).execute()
        _msg_total = _msg_total_resp.count or 0
    except Exception:
        _msg_total = 0

    # ── ヘッダー（空白なし・1行で完結）──
    _msg_count_txt = f"累計 {_msg_total} 件 ｜ " if _msg_total > 0 else ""
    st.markdown(
        f'<div style="text-align:center;font-size:13px;font-weight:700;color:rgba(240,240,245,0.75);'
        f'background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);'
        f'border-radius:14px;padding:10px 16px;margin-bottom:10px;">'
        f'💜 {_msg_count_txt}ログインして応援メッセージを送ろう（1日1回）</div>',
        unsafe_allow_html=True,
    )

    if not _msg_sup_id:
        # 未ログイン → SNSログインを促す
        _mc1, _mc2, _mc3 = st.columns(3)
        with _mc1:
            st.link_button("🟢 LINE", _line_auth_url(f"lsp_{connect_acct}"), use_container_width=True)
        with _mc2:
            st.link_button("🔵 Google", _google_auth_url(f"gsp_{connect_acct}"), use_container_width=True)
        with _mc3:
            st.link_button("🟣 Discord", _discord_auth_url(f"dsp_{connect_acct}"), use_container_width=True)
    else:
        # ログイン済み → 今日送信済みか確認
        _jst9 = datetime.timezone(datetime.timedelta(hours=9))
        try:
            _today_jst    = datetime.datetime.now(_jst9).date().isoformat()
            _tomorrow_jst = (datetime.datetime.now(_jst9).date() + datetime.timedelta(days=1)).isoformat()
            _sent_resp = (
                get_db().table("free_messages")
                .select("id,streak_count,message")
                .eq("creator_acct", connect_acct)
                .eq("supporter_id", _msg_sup_id)
                .gte("created_at", f"{_today_jst}T00:00:00+09:00")
                .lt("created_at",  f"{_tomorrow_jst}T00:00:00+09:00")
                .maybe_single().execute()
            )
            _already_sent = bool(_sent_resp.data)
            _my_streak    = (_sent_resp.data or {}).get("streak_count", 1) if _already_sent else 0
            _sent_msg     = (_sent_resp.data or {}).get("message", "") if _already_sent else ""
        except Exception:
            _already_sent = False
            _my_streak    = 0
            _sent_msg     = ""

        if _already_sent:
            _streak_badge = (
                f'<div style="font-size:16px;margin-top:6px;">🔥 {_my_streak}日連続応援中！</div>'
                if _my_streak > 1 else ""
            )
            # _sent_msg が空でも「」が出ないよう条件分岐
            _sent_msg_html = (
                f'<br><span style="font-size:12px;color:rgba(240,240,245,0.45);font-weight:400;">「{_sent_msg}」</span>'
                if _sent_msg else ""
            )
            st.markdown(
                f'<div style="text-align:center;font-size:14px;color:#c4b5fd;font-weight:700;padding:6px 0;">'
                f'✅ 今日の応援送信済み！ありがとうございます{_sent_msg_html}'
                f'{_streak_badge}</div>',
                unsafe_allow_html=True,
            )
        else:
            # ① 応援スタンプ（定型文選択）
            _selected_key = f"selected_phrase_{connect_acct}"
            _selected     = st.session_state.get(_selected_key, "")
            st.markdown('<div style="font-size:11px;color:rgba(240,240,245,0.45);margin-bottom:6px;">① 応援スタンプ</div>', unsafe_allow_html=True)
            for _phrase in _FREE_MSGS:
                _is_sel = (_selected == _phrase)
                _label  = f"✅ {_phrase}" if _is_sel else _phrase
                if st.button(_label, key=f"phrase_sel_{_phrase}", use_container_width=True,
                             type="primary" if _is_sel else "secondary"):
                    st.session_state[_selected_key] = _phrase
                    st.rerun()

            # ② メッセージ入力
            st.markdown('<div style="font-size:11px;color:rgba(240,240,245,0.45);margin-top:10px;margin-bottom:4px;">② メッセージ入力</div>', unsafe_allow_html=True)
            _msg_input = st.text_input(
                "メッセージ",
                value=_selected,
                placeholder="定型文を選ぶか直接入力...",
                key="free_msg_text_input",
                label_visibility="collapsed",
            )

            # ③ 応援ボタン
            _can_submit = bool((_msg_input or "").strip())
            if st.button("💜 応援する", use_container_width=True, type="primary",
                         disabled=not _can_submit, key="free_msg_submit"):
                # streak計算: 昨日送信あり → +1、なければ 1 からリセット
                try:
                    _yesterday_jst = (datetime.datetime.now(_jst9).date() - datetime.timedelta(days=1)).isoformat()
                    _yday_resp = (
                        get_db().table("free_messages")
                        .select("streak_count")
                        .eq("creator_acct", connect_acct)
                        .eq("supporter_id", _msg_sup_id)
                        .gte("created_at", f"{_yesterday_jst}T00:00:00+09:00")
                        .lt("created_at",  f"{_today_jst}T00:00:00+09:00")
                        .maybe_single().execute()
                    )
                    _new_streak = ((_yday_resp.data or {}).get("streak_count") or 0) + 1 if _yday_resp.data else 1
                except Exception:
                    _new_streak = 1
                try:
                    get_db().table("free_messages").insert({
                        "creator_acct": connect_acct,
                        "supporter_id": _msg_sup_id,
                        "message":      _msg_input.strip(),
                        "streak_count": _new_streak,
                    }).execute()
                    if _selected_key in st.session_state:
                        del st.session_state[_selected_key]
                    st.rerun()
                except Exception as _me:
                    st.error(f"送信エラー: {_me}")

    if "amt" not in st.session_state: st.session_state.amt = 100

    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">💸 応援金を送る（有料）</div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:12px;color:rgba(240,240,245,0.45);margin-bottom:12px;">金額を選んでメッセージを添えて応援しよう</div>', unsafe_allow_html=True)

    # ── 口座未登録クリエイターへの注意書き ──
    if not _creator_bank_ready:
        st.markdown("""
        <div style="background:rgba(251,191,36,0.1);border:1px solid rgba(251,191,36,0.4);border-radius:12px;padding:14px 16px;margin-bottom:16px;font-size:12px;line-height:1.7;color:rgba(240,240,245,0.85);">
            ⚠️ <b style="color:#fbbf24;">このクリエイターはまだ受取口座を登録していません</b><br>
            ・設定した金額は現在送金できません。クリエイター側が口座登録完了次第、送金可能となります。<br>
            ・クリエイター側が <b>72時間以内</b> に口座登録を完了できない場合、自動的にキャンセルとなります。<br>
            ・入金可能な状況となり次第ご連絡しますので、メールアドレスの入力をお願いします。<br>
            ・メール送付後、<b>72時間以内</b> に入金が確認できない場合は自動的にキャンセルとなります。
        </div>
        """, unsafe_allow_html=True)

    # 金額スライダー（口座未登録＝payout_enabled未完了は1000円上限）
    if _creator_bank_ready:
        slider_options = (
            list(range(100, 1000, 100)) +
            list(range(1000, 10000, 500)) +
            list(range(10000, 100001, 5000))  # 上限10万円（マネーロンダリング対策）
        )
    else:
        slider_options = list(range(100, 1100, 100))  # 100〜1000円

    current_amt = int(st.session_state.amt)
    if current_amt not in slider_options:
        current_amt = min(slider_options, key=lambda x: abs(x - current_amt))

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

    # ── SNS ログイン（応援ページ）──
    _sup_auth = st.session_state.get("supporter_auth", {})
    if _sup_auth.get("supporter_id"):
        _sauth_name = _sup_auth.get("display_name") or "サポーター"
        st.markdown(
            f'<div style="background:rgba(139,92,246,0.12);border:1px solid rgba(139,92,246,0.4);'
            f'border-radius:14px;padding:14px 16px;text-align:center;margin-bottom:16px;">'
            f'✅ <b>{_sauth_name}</b> さんですね！</div>',
            unsafe_allow_html=True,
        )
        if st.button("別のアカウントでログイン", key="sup_sns_logout"):
            del st.session_state["supporter_auth"]
            st.rerun()
    else:
        st.markdown(
            '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);'
            'border-radius:14px;padding:14px 16px;margin-bottom:4px;">'
            '<div style="text-align:center;font-size:12px;color:rgba(240,240,245,0.6);margin-bottom:10px;">'
            '🔑 SNSアカウントでかんたんログイン</div>',
            unsafe_allow_html=True,
        )
        _scol1, _scol2, _scol3 = st.columns(3)
        with _scol1:
            st.link_button("🟢 LINE", _line_auth_url(f"lsp_{connect_acct}"), use_container_width=True)
        with _scol2:
            st.link_button("🔵 Google", _google_auth_url(f"gsp_{connect_acct}"), use_container_width=True)
        with _scol3:
            st.link_button("🟣 Discord", _discord_auth_url(f"dsp_{connect_acct}"), use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)
        st.markdown(
            '<div style="text-align:center;font-size:11px;color:rgba(240,240,245,0.35);'
            'margin:4px 0 12px;">または以下にメールアドレスを入力</div>',
            unsafe_allow_html=True,
        )

    st.markdown('<div class="section-subtitle" style="text-align:left;margin-bottom:4px;">📧 メールアドレス（必須）</div><div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:8px;">応援証明書・サポーターIDをお届けします。アカウント登録にも使用します。</div>', unsafe_allow_html=True)
    _default_email = st.session_state.get("supporter_auth", {}).get("email", "")
    support_email = st.text_input("メールアドレス", value=_default_email, placeholder="you@example.com", label_visibility="collapsed", key="support_email_input")

    st.markdown('<div class="section-subtitle" style="text-align:left;margin-bottom:4px;margin-top:12px;">🎫 サポーターID（任意）</div><div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:8px;">お持ちの方は入力すると応援履歴が自動で紐づきます。</div>', unsafe_allow_html=True)
    _default_sup_id = st.session_state.get("supporter_auth", {}).get("supporter_id", "")
    opt_sup_id = st.text_input("サポーターID", value=_default_sup_id, placeholder="sup_xxxx", label_visibility="collapsed", key="opt_sup_id_input")

    st.markdown('<div class="section-subtitle" style="text-align:left;margin-bottom:4px;margin-top:12px;">👤 お名前（任意）</div><div style="font-size:11px;color:rgba(240,240,245,0.5);margin-bottom:8px;">入力するとランキングにお名前が表示されます</div>', unsafe_allow_html=True)
    _default_name = st.session_state.get("supporter_auth", {}).get("display_name", "")
    sup_display_name = st.text_input("お名前", value=_default_name, placeholder="例: たろう", label_visibility="collapsed")

    is_disabled = st.session_state.amt < 100
    if is_disabled:
        st.info("💡 応援は100円から受け付けています。")

    # ── 最終確認 ──
    st.markdown(f"""
    <div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.1);border-radius:12px;padding:16px;margin-top:20px;margin-bottom:20px;">
        <div style="font-size:13px;color:#f0f0f5;font-weight:700;margin-bottom:10px;border-bottom:1px solid rgba(255,255,255,0.1);padding-bottom:5px;">最終確認</div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
            <span style="font-size:12px;color:rgba(240,240,245,0.6);">支払予定額（税込）</span>
            <span style="font-size:14px;color:#f97316;font-weight:700;">{int(st.session_state.amt):,}円</span>
        </div>
        <div style="display:flex;justify-content:space-between;margin-bottom:6px;">
            <span style="font-size:12px;color:rgba(240,240,245,0.6);">支払時期</span>
            <span style="font-size:12px;color:#f0f0f5;">{"口座登録完了後にご連絡" if not _creator_bank_ready else "決済手続き完了時"}</span>
        </div>
        <div style="margin-top:10px;padding-top:10px;border-top:1px dashed rgba(255,255,255,0.1);">
            <div style="font-size:11px;color:rgba(240,240,245,0.5);line-height:1.4;">
                {"※クリエイターが72時間以内に口座登録しない場合、自動キャンセルとなります。" if not _creator_bank_ready else "※デジタルコンテンツおよび投げ銭の性質上、決済手続き完了後のキャンセル・返金・返品には一切応じられません。"}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)

    if _creator_bank_ready:
        # ── 口座登録済み（payout_enabled=True）：通常 Stripe フロー ──
        if st.button("💰 応援金を送る！", disabled=is_disabled, type="primary", use_container_width=True):
            # メール必須チェック
            if not support_email or "@" not in support_email:
                st.error("📧 メールアドレスを入力してください。応援証明書をお届けするために必要です。")
                st.stop()
            amt = st.session_state.amt
            support_id = str(uuid.uuid4())
            # sup_idが入力されていればDB確認して優先使用、なければメアドから取得/作成
            try:
                _input_sid = opt_sup_id.strip() if opt_sup_id and opt_sup_id.strip().startswith("sup_") else ""
                if _input_sid:
                    _sid_chk = get_db().table("supporters").select("supporter_id").eq("supporter_id", _input_sid).maybe_single().execute()
                    if _sid_chk.data:
                        final_sup_id = _input_sid
                        # メアドを紐付け（未設定の場合のみ）
                        get_db().table("supporters").update({"email": support_email.strip().lower()}).eq("supporter_id", final_sup_id).is_("email", "null").execute()
                    else:
                        st.error(f"サポーターID `{_input_sid}` はDBに存在しません。空欄にするか正しいIDを入力してください。")
                        st.stop()
                else:
                    final_sup_id, _is_new_sup = get_or_create_supporter_by_email(support_email, sup_display_name)
            except st.StopException:
                raise
            except Exception as _se:
                st.error(f"サポーターID取得エラー: {_se}")
                st.stop()
            _email_enc = urllib.parse.quote(support_email.strip().lower())
            try:
                checkout_params = {
                    "payment_method_types": ["card"], "mode": "payment",
                    "line_items": [{"price_data": {"currency": "jpy", "product_data": {"name": f"{support_name}への応援"}, "unit_amount": amt}, "quantity": 1}],
                    "success_url": f"{BASE_URL}?page=success&s_name={urllib.parse.quote(support_name)}&s_amt={amt}&s_acct={connect_acct}&s_stripe_acct={_stripe_connect_acct}&s_msg={urllib.parse.quote(msg or '')}&s_sid={support_id}&s_sup_id={final_sup_id}&s_sup_name={urllib.parse.quote(sup_display_name or '')}&s_email={_email_enc}&s_session={{CHECKOUT_SESSION_ID}}",
                    "cancel_url": f"{BASE_URL}?page=cancel",
                    "metadata": {"support_id": support_id, "supporter_id": final_sup_id, "supporter_email": support_email.strip().lower()}
                }
                checkout_params["payment_intent_data"] = {"application_fee_amount": int(amt * 0.1)}
                session = stripe.checkout.Session.create(**checkout_params, stripe_account=_stripe_connect_acct)
                st.markdown(f'<script>window.top.location.href = "{session.url}";</script>', unsafe_allow_html=True)
                st.link_button("💳 決済ページへ", session.url)
            except Exception as e:
                st.error(e)
    else:
        # ── 口座未登録：pending_supports に保存（Stripe不使用）──
        if st.button("💰 応援金を送る！", disabled=is_disabled, type="primary", use_container_width=True):
            if not support_email or "@" not in support_email:
                st.error("📧 メールアドレスを入力してください。口座登録完了時にご連絡します。")
                st.stop()
            try:
                _pend_email_lc = support_email.strip().lower()
                _input_sid_p = opt_sup_id.strip() if opt_sup_id and opt_sup_id.strip().startswith("sup_") else ""
                if _input_sid_p:
                    _sid_chk_p = get_db().table("supporters").select("supporter_id").eq("supporter_id", _input_sid_p).maybe_single().execute()
                    if _sid_chk_p.data:
                        _pend_sup_id = _input_sid_p
                        get_db().table("supporters").update({"email": _pend_email_lc}).eq("supporter_id", _pend_sup_id).is_("email", "null").execute()
                    else:
                        st.error(f"サポーターID `{_input_sid_p}` はDBに存在しません。")
                        st.stop()
                else:
                    _pend_sup_id, _ = get_or_create_supporter_by_email(_pend_email_lc, sup_display_name)
                # このクリエイターへの通算予約番号を計算（キャンセル済み含む全件）
                try:
                    _res_cnt = get_db().table("pending_supports").select("id", count="exact").eq("creator_acct", connect_acct).execute()
                    _res_no = (_res_cnt.count or 0) + 1
                except Exception:
                    _res_no = 1
                _pend_row = {
                    "creator_acct": connect_acct,
                    "amount": int(st.session_state.amt),
                    "message": msg or "",
                    "contact_info": "",
                    "supporter_id": _pend_sup_id,
                    "reservation_no": _res_no,
                }
                try:
                    _pend_row["supporter_email"] = _pend_email_lc
                except Exception:
                    pass
                try:
                    get_db().table("pending_supports").insert(_pend_row).execute()
                except Exception as _pe_inner:
                    _pend_row.pop("supporter_email", None)
                    get_db().table("pending_supports").insert(_pend_row).execute()
                # ── サポーターへ仮予約確認メール ──
                try:
                    send_pending_reservation_supporter_email(_pend_email_lc, support_name, int(st.session_state.amt), _res_no, display_name=sup_display_name)
                except Exception:
                    pass
                # ── クリエイターへ仮予約通知メール ──
                try:
                    _notif_cr = get_db().table("creators").select("email,display_name").eq("acct_id", connect_acct).maybe_single().execute()
                    _notif_email = (_notif_cr.data or {}).get("email", "")
                    _notif_name  = (_notif_cr.data or {}).get("display_name", support_name)
                    if _notif_email:
                        _dashboard_url = f"{BASE_URL}?page=dashboard&acct={connect_acct}"
                        _pend_exp_jst = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=72)).astimezone(datetime.timezone(datetime.timedelta(hours=9)))
                        _pend_exp_str = _pend_exp_jst.strftime("%Y/%m/%d %H:%M（JST）")
                        send_pending_reservation_creator_email(_notif_email, _notif_name, int(st.session_state.amt), msg or "", _dashboard_url, _pend_exp_str, supporter_name=sup_display_name)
                except Exception:
                    pass
                st.markdown(f"""
                <div style="background:rgba(139,92,246,0.15);border:1px solid rgba(139,92,246,0.4);border-radius:14px;padding:20px;text-align:center;margin-top:12px;">
                    <div style="font-size:13px;color:rgba(240,240,245,0.6);margin-bottom:4px;">応援予約を受け付けました 🎫</div>
                    <div style="font-size:38px;font-weight:900;color:#c4b5fd;">予約 #{_res_no}番</div>
                    <div style="font-size:13px;color:rgba(240,240,245,0.65);margin-top:8px;">
                        クリエイターが口座登録を完了次第、お支払いURLをメールでお送りします。<br>
                        <span style="color:#fbbf24;font-weight:700;">72時間以内にお支払いください。</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                st.balloons()
            except Exception as _pe:
                st.error(f"エラー: {_pe}")

    st.markdown(f'<div class="oshi-footer">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="https://oshipay.me/terms" target="_blank">利用規約</a><a href="https://oshipay.me/privacy" target="_blank">プライバシーポリシー</a><a href="https://oshipay.me/tokusho" target="_blank">特定商取引法</a></div>', unsafe_allow_html=True)

# ── サポーター公開ポートフォリオ ──
elif page == "portfolio":
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 600px !important; margin: 0 auto; }</style>", unsafe_allow_html=True)
    p_id = params.get("id", "")
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
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
    
    # サポーターログインボタン（ID補完済み）
    if st.button("🔑 サポーターログイン", use_container_width=True, key="portfolio_sup_login"):
        st.session_state["_sup_prefill_id"] = p_id
        st.query_params["page"] = "supporter_dashboard"
        st.query_params["sid"]  = p_id
        st.rerun()

    share_text = f"私のoshipay応援実績はこちら！総額 {total_amount:,}\n#oshipay\n{BASE_URL}?page=portfolio&id={p_id}"
    st.link_button("𝕏 で公開する", f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}", use_container_width=True)
    st.link_button("あなたもoshipayを始めよう", f"{BASE_URL}?page=lp", use_container_width=True)
    st.stop()

# ── サポーター用ダッシュボード ──
elif page == "supporter_dashboard":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">サポーター・ダッシュボード</div>', unsafe_allow_html=True)
    

    # ── Google アカウント紐づけ確認画面 ──
    if "_g_link_info" in st.session_state and "supporter_auth" not in st.session_state:
        _li = st.session_state["_g_link_info"]
        _candidates = _li.get("candidates", [])
        st.markdown(f"""
        <div style="background:rgba(66,133,244,0.12); border:1px solid rgba(66,133,244,0.35); border-radius:14px; padding:24px; margin-bottom:20px; text-align:center;">
          <div style="font-size:28px; margin-bottom:10px;">🔗</div>
          <div style="font-weight:700; color:#f0f0f5; font-size:16px; margin-bottom:8px;">同じメールアドレスのアカウントが見つかりました</div>
          <div style="font-size:13px; color:rgba(240,240,245,0.7); margin-bottom:4px;">{_li['email']}</div>
          <div style="font-size:12px; color:rgba(240,240,245,0.5); margin-top:6px;">どのアカウントにGoogleログインを紐づけますか？</div>
        </div>
        """, unsafe_allow_html=True)

        # 候補リストをラジオボタンで選択
        _radio_options = [f"{c['supporter_id']}　{c['display_name']}" for c in _candidates]
        _radio_options.append("➕ 新しいアカウントとして続ける")
        _selected = st.radio("紐づけるアカウントを選択", _radio_options, key="g_link_radio")

        # 選択したアカウントにIDとパスワードで本人確認
        _selected_idx = _radio_options.index(_selected) if _selected in _radio_options else -1
        if _selected_idx < len(_candidates):
            _target_sid = _candidates[_selected_idx]["supporter_id"]
            st.caption(f"選択中: `{_target_sid}` — パスワードまたはサポーターIDで本人確認してください")
            _lk_pw = st.text_input("パスワード（または空欄でIDのみ確認）", type="password", key="g_link_pw")
            _lk1, _lk2 = st.columns(2)
            with _lk1:
                if st.button("✅ このアカウントに紐づける", use_container_width=True, type="primary", key="g_link_yes"):
                    # パスワードチェック（入力された場合のみ）
                    _pw_ok = True
                    if _lk_pw:
                        _sa_chk = get_db().table("supporter_accounts").select("password_hash").eq("supporter_id", _target_sid).limit(1).execute()
                        if _sa_chk.data and _sa_chk.data[0].get("password_hash"):
                            _pw_ok = _sa_chk.data[0]["password_hash"] == hash_password(_lk_pw)
                    if _pw_ok:
                        _sub_field = "discord_sub" if _li.get("provider") == "discord" else "google_sub"
                        # supporters に sub を保存（一元管理）
                        get_db().table("supporters").update({_sub_field: _li["sub"]}).eq("supporter_id", _target_sid).execute()
                        # supporter_accounts にも同期
                        _sa_exists = get_db().table("supporter_accounts").select("supporter_id").eq("supporter_id", _target_sid).limit(1).execute()
                        if _sa_exists.data:
                            get_db().table("supporter_accounts").update({_sub_field: _li["sub"]}).eq("supporter_id", _target_sid).execute()
                        else:
                            get_db().table("supporter_accounts").insert({
                                "supporter_id": _target_sid, "email": _li["email"], _sub_field: _li["sub"]
                            }).execute()
                        _sn2 = get_db().table("supporters").select("display_name").eq("supporter_id", _target_sid).limit(1).execute()
                        _d2  = (_sn2.data[0]["display_name"] if _sn2.data else None) or _li["name"]
                        st.session_state["supporter_auth"] = {"supporter_id": _target_sid, "display_name": _d2, "email": _li["email"]}
                        del st.session_state["_g_link_info"]
                        st.rerun()
                    else:
                        st.error("パスワードが違います。")
            with _lk2:
                if st.button("キャンセル", use_container_width=True, key="g_link_no"):
                    del st.session_state["_g_link_info"]
                    st.session_state.pop("_g_done", None)
                    st.rerun()
        else:
            # 新規アカウントとして続ける
            if st.button("➕ 新しいアカウントを作成", use_container_width=True, type="primary", key="g_link_new"):
                _new_sid = "sup_" + uuid.uuid4().hex[:12]
                get_db().table("supporter_accounts").insert({
                    "supporter_id": _new_sid, "email": _li["email"] + f"+g{uuid.uuid4().hex[:4]}", "google_sub": _li["sub"]
                }).execute()
                try:
                    get_db().table("supporters").upsert({
                        "supporter_id": _new_sid, "display_name": _li["name"], "email": _li["email"],
                    }).execute()
                except Exception:
                    pass
                st.session_state["supporter_auth"] = {"supporter_id": _new_sid, "display_name": _li["name"], "email": _li["email"]}
                st.session_state["_g_new_name"] = _li["name"]
                del st.session_state["_g_link_info"]
                st.rerun()
        st.stop()

    if "supporter_auth" not in st.session_state:
        _prefill_sid = st.session_state.pop("_sup_prefill_id", None) or params.get("sid", "")

        # ── IDが渡された場合はDBをチェックして最適なフォームを表示 ──
        _sid_db_row = None
        _sid_has_email = False
        if _prefill_sid:
            try:
                _sid_chk = get_db().table("supporters").select("supporter_id,display_name,email,password_hash").eq("supporter_id", _prefill_sid).maybe_single().execute()
                if _sid_chk.data:
                    _sid_db_row = _sid_chk.data
                    _sid_has_email = bool(_sid_chk.data.get("email"))
            except Exception:
                pass

        # ── フォームのモード決定 ──
        # A : IDあり＋メール登録済み＋PW設定済み → パスワードのみ
        # A2: IDあり＋メール登録済み＋PW未設定  → Stripe初回ユーザ → OTP+PW設定
        # B : IDあり＋メール未登録              → ブロック（Stripe経由でのみ登録可）
        # C : IDなし                            → タブ形式（新規登録優先）

        if _prefill_sid and _sid_db_row and _sid_has_email:
            _a_has_pw = bool(_sid_db_row.get("password_hash"))

            if _a_has_pw:
                # ── モードA: パスワードのみ ──
                st.success(f"✅ サポーターID `{_prefill_sid}` が確認できました。パスワードを入力してください。")
                a_pass = st.text_input("パスワード", type="password", key="a_pass")
                if st.button("ログイン", use_container_width=True, type="primary"):
                    if _sid_db_row.get("password_hash") == hash_password(a_pass):
                        _disp = _sid_db_row.get("display_name") or _sid_db_row["email"].split("@")[0]
                        st.session_state["supporter_auth"] = {
                            "supporter_id": _prefill_sid,
                            "display_name": _disp,
                            "email": _sid_db_row["email"]
                        }
                        st.rerun()
                    else:
                        st.error("パスワードが違います。")
                with st.expander("🔓 パスワードを忘れた"):
                    if st.button("仮パスワードを発行", key="a_forgot"):
                        _temp = uuid.uuid4().hex[:8]
                        get_db().table("supporters").update({"password_hash": hash_password(_temp)}).eq("supporter_id", _prefill_sid).execute()
                        try:
                            get_db().table("supporter_accounts").update({"password_hash": hash_password(_temp)}).eq("supporter_id", _prefill_sid).execute()
                        except Exception:
                            pass
                        st.success(f"仮パスワード: `{_temp}`")

            else:
                # ── モードA2: Stripe経由初回ユーザ（メールあり・PW未設定）──
                _a2_email = _sid_db_row["email"]
                st.info(f"🎉 サポーターID `{_prefill_sid}` が確認できました！パスワードを設定して登録を完了してください。")
                st.caption(f"登録メールアドレス: {_a2_email[:3]}***（変更不可）")
                if not st.session_state.get("_reg_a2_otp_sent"):
                    a2_name = st.text_input("表示名（任意・公開されます）", key="a2_name", placeholder="例: たろう")
                    a2_pass = st.text_input("パスワード", type="password", key="a2_pass")
                    if st.button("確認コードを送信", use_container_width=True, type="primary", key="a2_send"):
                        if a2_pass:
                            import random, time as _time
                            _otp = f"{random.randint(0, 999999):06d}"
                            _ok, _err = send_registration_otp_email(_a2_email, _otp)
                            if _ok:
                                st.session_state["_reg_a2_name"]     = a2_name.strip() or _a2_email.split("@")[0]
                                st.session_state["_reg_a2_pass"]     = a2_pass
                                st.session_state["_reg_a2_otp"]      = _otp
                                st.session_state["_reg_a2_otp_time"] = _time.time()
                                st.session_state["_reg_a2_otp_sent"] = True
                                st.rerun()
                            else:
                                st.error(f"メール送信失敗: {_err}")
                        else:
                            st.warning("パスワードを入力してください。")
                else:
                    import time as _time
                    _a2_elapsed = _time.time() - st.session_state.get("_reg_a2_otp_time", 0)
                    if _a2_elapsed > 300:
                        st.error("⏱️ 有効期限（5分）が切れました。もう一度やり直してください。")
                        for _k in ["_reg_a2_name","_reg_a2_pass","_reg_a2_otp","_reg_a2_otp_time","_reg_a2_otp_sent"]:
                            st.session_state.pop(_k, None)
                        st.rerun()
                    st.success(f"📧 {_a2_email[:3]}*** に確認コードを送信しました。（残り約 {max(0, 300-int(_a2_elapsed))} 秒）")
                    a2_otp_input = st.text_input("6桁の確認コード", key="a2_otp_input", placeholder="123456", max_chars=6)
                    _ac1, _ac2 = st.columns(2)
                    with _ac1:
                        if st.button("登録を完了する", use_container_width=True, type="primary", key="a2_reg_done"):
                            if a2_otp_input.strip() == st.session_state.get("_reg_a2_otp"):
                                _disp = st.session_state["_reg_a2_name"]
                                _pw   = st.session_state["_reg_a2_pass"]
                                get_db().table("supporters").update({
                                    "display_name": _disp, "password_hash": hash_password(_pw)
                                }).eq("supporter_id", _prefill_sid).execute()
                                try:
                                    get_db().table("supporter_accounts").upsert({
                                        "supporter_id": _prefill_sid, "email": _a2_email, "password_hash": hash_password(_pw)
                                    }).execute()
                                except Exception:
                                    pass
                                for _k in ["_reg_a2_name","_reg_a2_pass","_reg_a2_otp","_reg_a2_otp_time","_reg_a2_otp_sent"]:
                                    st.session_state.pop(_k, None)
                                st.session_state["supporter_auth"] = {"supporter_id": _prefill_sid, "display_name": _disp, "email": _a2_email}
                                send_welcome_email(_a2_email, _disp, _prefill_sid)
                                st.rerun()
                            else:
                                st.error("❌ コードが一致しません。")
                    with _ac2:
                        if st.button("キャンセル", key="a2_cancel"):
                            for _k in ["_reg_a2_name","_reg_a2_pass","_reg_a2_otp","_reg_a2_otp_time","_reg_a2_otp_sent"]:
                                st.session_state.pop(_k, None)
                            st.rerun()

        elif _prefill_sid and _sid_db_row and not _sid_has_email:
            # ── モードB: IDは確認済み・メール未登録 → ブロック ──
            st.info(f"サポーターID `{_prefill_sid}` が確認できました。")
            st.warning("⚠️ このIDにはメールアドレスが登録されていません。\nQRコードからお支払いいただくと、お支払い時のメールアドレスで自動的にアカウントが発行されます。")
            st.caption("Apple Pay・Google Pay・クレジットカードでお支払いいただくと、そのメールアドレスが自動的に登録されます。")

        else:
            # ── モードC: IDなし or 不明 → タブ（新規登録優先）──
            st.info("応援チケットの確認・応援履歴の管理ができます。")

            # ── Googleでログインボタン ──
            if LINE_CLIENT_ID:
                _render_line_button(_line_auth_url("l_sup"))
            if GOOGLE_CLIENT_ID:
                _render_google_button(_google_auth_url("g_sup"))
                if DISCORD_CLIENT_ID:
                    _render_discord_button(_discord_auth_url("d_sup"))
            if LINE_CLIENT_ID or GOOGLE_CLIENT_ID:
                st.markdown('<div style="text-align:center; color:rgba(255,255,255,0.35); font-size:12px; margin:4px 0 12px;">── または メール・パスワードで ──</div>', unsafe_allow_html=True)

            tab_register, tab_login, tab_forgot = st.tabs(["✨ 新規登録", "🔑 ログイン", "🔓 パスワードを忘れた"])

            with tab_register:
                st.caption("メールアドレスとパスワードだけで登録できます")
                if not st.session_state.get("_reg_c_otp_sent"):
                    r_sid   = st.text_input("サポーターID（お持ちの方のみ）", key="r_sid",
                                            value=_prefill_sid or "",
                                            placeholder="sup_xxxx （なければ空欄でOK）")
                    r_email = st.text_input("メールアドレス（必須）", key="r_new_email", placeholder="you@example.com")
                    r_name  = st.text_input("表示名（任意・公開されます）", key="r_new_name", placeholder="例: たろう")
                    r_pass  = st.text_input("パスワード", type="password", key="r_new_pass")
                    if st.button("確認コードを送信", type="primary", use_container_width=True):
                        if r_email and r_pass:
                            _email_lc = r_email.strip().lower()
                            _existing_sa = get_db().table("supporter_accounts").select("supporter_id").eq("email", _email_lc).limit(1).execute()
                            if _existing_sa.data:
                                st.error("このメールアドレスは既に登録済みです。ログインしてください。")
                            else:
                                import random, time as _time
                                _otp = f"{random.randint(0, 999999):06d}"
                                _ok, _err = send_registration_otp_email(_email_lc, _otp)
                                if _ok:
                                    _use_sid = r_sid.strip() if r_sid.strip().startswith("sup_") else "sup_" + uuid.uuid4().hex[:12]
                                    st.session_state["_reg_c_sid"]      = _use_sid
                                    st.session_state["_reg_c_email"]    = _email_lc
                                    st.session_state["_reg_c_name"]     = r_name.strip() or _email_lc.split("@")[0]
                                    st.session_state["_reg_c_pass"]     = r_pass
                                    st.session_state["_reg_c_otp"]      = _otp
                                    st.session_state["_reg_c_otp_time"] = _time.time()
                                    st.session_state["_reg_c_otp_sent"] = True
                                    st.rerun()
                                else:
                                    st.error(f"メール送信失敗: {_err}")
                        else:
                            st.warning("メールアドレスとパスワードを入力してください。")
                else:
                    import time as _time
                    _c_elapsed = _time.time() - st.session_state.get("_reg_c_otp_time", 0)
                    if _c_elapsed > 300:
                        st.error("⏱️ 有効期限（5分）が切れました。もう一度やり直してください。")
                        for _k in ["_reg_c_sid","_reg_c_email","_reg_c_name","_reg_c_pass","_reg_c_otp","_reg_c_otp_time","_reg_c_otp_sent"]:
                            st.session_state.pop(_k, None)
                        st.rerun()
                    _c_email = st.session_state.get("_reg_c_email", "")
                    st.success(f"📧 {_c_email[:3]}*** に確認コードを送信しました。（残り約 {max(0, 300-int(_c_elapsed))} 秒）")
                    c_otp_input = st.text_input("6桁の確認コード", key="c_otp_input", placeholder="123456", max_chars=6)
                    _cc1, _cc2 = st.columns(2)
                    with _cc1:
                        if st.button("アカウントを作成", type="primary", use_container_width=True, key="c_reg_done"):
                            if c_otp_input.strip() == st.session_state.get("_reg_c_otp"):
                                _use_sid    = st.session_state["_reg_c_sid"]
                                _email_lc   = st.session_state["_reg_c_email"]
                                _disp_name  = st.session_state["_reg_c_name"]
                                _r_pass     = st.session_state["_reg_c_pass"]
                                try:
                                    get_db().table("supporter_accounts").insert({
                                        "supporter_id": _use_sid, "email": _email_lc, "password_hash": hash_password(_r_pass)
                                    }).execute()
                                    try:
                                        get_db().table("supporters").upsert({
                                            "supporter_id": _use_sid, "display_name": _disp_name,
                                            "email": _email_lc, "password_hash": hash_password(_r_pass)
                                        }).execute()
                                    except Exception:
                                        pass
                                    for _k in ["_reg_c_sid","_reg_c_email","_reg_c_name","_reg_c_pass","_reg_c_otp","_reg_c_otp_time","_reg_c_otp_sent"]:
                                        st.session_state.pop(_k, None)
                                    st.session_state["supporter_auth"] = {"supporter_id": _use_sid, "display_name": _disp_name, "email": _email_lc}
                                    send_welcome_email(_email_lc, _disp_name, _use_sid)
                                    st.rerun()
                                except Exception as _re:
                                    st.error(f"登録エラー: {_re}")
                            else:
                                st.error("❌ コードが一致しません。")
                    with _cc2:
                        if st.button("キャンセル", key="c_reg_cancel"):
                            for _k in ["_reg_c_sid","_reg_c_email","_reg_c_name","_reg_c_pass","_reg_c_otp","_reg_c_otp_time","_reg_c_otp_sent"]:
                                st.session_state.pop(_k, None)
                            st.rerun()

            with tab_login:
                st.caption("メールアドレス または サポーターID でログインできます")
                l_id   = st.text_input("メールアドレス または サポーターID", key="l_id",
                                       value=_prefill_sid or "",
                                       placeholder="you@example.com または sup_xxxx")
                l_pass = st.text_input("パスワード", type="password", key="l_pass")
                if st.button("ログイン", use_container_width=True, type="primary"):
                    if "@" in l_id:
                        _sa = get_db().table("supporter_accounts").select("*").eq("email", l_id.strip().lower()).limit(1).execute()
                        if _sa.data and _sa.data[0].get("password_hash") == hash_password(l_pass):
                            _sa_row = _sa.data[0]
                            _sn = get_db().table("supporters").select("display_name").eq("supporter_id", _sa_row["supporter_id"]).limit(1).execute()
                            _disp = (_sn.data[0]["display_name"] if _sn.data else None) or _sa_row["email"].split("@")[0]
                            st.session_state["supporter_auth"] = {"supporter_id": _sa_row["supporter_id"], "display_name": _disp, "email": _sa_row["email"]}
                            st.rerun()
                        elif _sa.data:
                            st.error("パスワードが違います。")
                        else:
                            st.error("アカウントが見つかりません。")
                    else:
                        _sr = get_db().table("supporters").select("*").eq("supporter_id", l_id.strip()).execute()
                        if not _sr.data:
                            st.error("アカウントが見つかりません。")
                        elif _sr.data[0].get("email"):
                            if _sr.data[0].get("password_hash") == hash_password(l_pass):
                                st.session_state["supporter_auth"] = _sr.data[0]
                                st.rerun()
                            else:
                                st.error("パスワードが違います。")
                        else:
                            st.warning("このIDはまだメールアドレスが未登録です。「新規登録」タブからIDを入力して登録してください。")

            with tab_forgot:
                st.caption("登録したメールアドレスを入力してください")
                f_email = st.text_input("メールアドレス", key="f_input", placeholder="you@example.com")
                if st.button("仮パスワードを発行", use_container_width=True):
                    if f_email and "@" in f_email:
                        _sa_f = get_db().table("supporter_accounts").select("*").eq("email", f_email.strip().lower()).limit(1).execute()
                        if _sa_f.data:
                            _temp = uuid.uuid4().hex[:8]
                            get_db().table("supporter_accounts").update({"password_hash": hash_password(_temp)}).eq("email", f_email.strip().lower()).execute()
                            try:
                                get_db().table("supporters").update({"password_hash": hash_password(_temp)}).eq("supporter_id", _sa_f.data[0]["supporter_id"]).execute()
                            except Exception:
                                pass
                            st.success(f"仮パスワード: `{_temp}`")
                        else:
                            st.error("このメールアドレスは登録されていません。")
                    else:
                        st.warning("メールアドレスを入力してください。")
        st.stop()
        
    sup_user = st.session_state["supporter_auth"]

    # ── 新規Googleアカウント: 表示名確認 ──
    if "_g_new_name" in st.session_state:
        _default_gname = st.session_state["_g_new_name"]
        st.markdown("""
        <div style="background:rgba(66,133,244,0.12); border:1px solid rgba(66,133,244,0.35); border-radius:14px; padding:20px; margin-bottom:20px; text-align:center;">
          <div style="font-size:22px; margin-bottom:8px;">🎉</div>
          <div style="font-weight:700; color:#f0f0f5; font-size:15px; margin-bottom:4px;">Googleアカウントで登録完了！</div>
          <div style="font-size:12px; color:rgba(240,240,245,0.6);">表示名を確認・変更できます</div>
        </div>
        """, unsafe_allow_html=True)
        _gn_input = st.text_input("表示名（公開されます）", value=_default_gname, key="g_name_input")
        if st.button("この名前で始める", type="primary", use_container_width=True, key="g_name_confirm"):
            _final_name = _gn_input.strip() or _default_gname
            try:
                get_db().table("supporters").update({"display_name": _final_name}).eq("supporter_id", sup_user["supporter_id"]).execute()
            except Exception:
                pass
            st.session_state["supporter_auth"]["display_name"] = _final_name
            sup_user["display_name"] = _final_name
            del st.session_state["_g_new_name"]
            st.rerun()
        st.stop()

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
    
    # ── 予約チケット（口座未登録クリエイターへの応援）──────────────
    _sup_email = sup_user.get("email", "")
    if _sup_email:
        try:
            import datetime as _dt_t
            _t_now = _dt_t.datetime.now(_dt_t.timezone.utc).isoformat()
            _sup_id_for_tickets = sup_user.get("supporter_id", "")
            # supporter_id で取得
            _t1 = get_db().table("pending_supports").select("*").eq("supporter_id", _sup_id_for_tickets).gte("expires_at", _t_now).execute().data or [] if _sup_id_for_tickets else []
            # supporter_email で取得（重複除去）
            _t2 = []
            try:
                _t2 = get_db().table("pending_supports").select("*").eq("supporter_email", _sup_email).gte("expires_at", _t_now).execute().data or []
            except Exception:
                pass
            _seen_ids = set()
            _all_raw = []
            for _t in (_t1 + _t2):
                if _t["id"] not in _seen_ids:
                    _seen_ids.add(_t["id"])
                    _all_raw.append(_t)
            _active_tickets = [t for t in _all_raw if t.get("status") == "pending"]
            if _active_tickets:
                st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
                st.markdown(f'<div class="header" style="font-size:16px;">🎫 予約チケット（{len(_active_tickets)}件）</div>', unsafe_allow_html=True)
                st.markdown('<div style="font-size:12px;color:rgba(255,255,255,0.5);margin-bottom:16px;">クリエイターが口座登録完了後にご連絡します。72時間以内に入金確認できない場合は自動キャンセル。</div>', unsafe_allow_html=True)
                for _t in _active_tickets:
                    _t_date = (_t.get("created_at") or "")[:10]
                    _t_exp  = (_t.get("expires_at") or "")[:16].replace("T", " ")
                    try:
                        _t_cr = get_db().table("creators").select("display_name,slug").eq("acct_id", _t["creator_acct"]).maybe_single().execute()
                        _t_cr_name = (_t_cr.data or {}).get("display_name") or _t["creator_acct"]
                    except Exception:
                        _t_cr_name = _t["creator_acct"]
                    import html as _html_t
                    _t_msg = _html_t.escape(str(_t.get("message") or "（メッセージなし）"))
                    st.markdown(f"""
                    <div style="background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.35);border-radius:14px;padding:16px;margin-bottom:12px;">
                        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
                            <div style="font-size:18px;font-weight:900;color:#f97316;">{_t["amount"]:,}円</div>
                            <span style="font-size:11px;color:#fbbf24;border:1px solid rgba(251,191,36,0.4);border-radius:9999px;padding:3px 10px;">🎫 予約中</span>
                        </div>
                        <div style="font-size:13px;color:#c4b5fd;font-weight:700;margin-bottom:4px;">{_t_cr_name} への応援</div>
                        <div style="font-size:12px;color:rgba(240,240,245,0.7);margin-bottom:4px;">💬 {_t_msg}</div>
                        <div style="font-size:11px;color:rgba(240,240,245,0.4);">登録日: {_t_date}　⚠️ 期限: {_t_exp} UTC</div>
                    </div>
                    """, unsafe_allow_html=True)
        except Exception:
            pass

    # ── 年輪コイン ──────────────────────────────────────
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="header" style="font-size:16px;">🪙 あなたの応援コイン</div>', unsafe_allow_html=True)
    st.markdown('<div style="font-size:12px;color:rgba(255,255,255,0.5);margin-bottom:16px;">応援するたびに、コインに刻印が刻まれていきます。</div>', unsafe_allow_html=True)

    def _coin_level(total):
        if total >= 100000: return "🌈", "レインボー"
        elif total >= 30000: return "💎", "ダイヤモンド"
        elif total >= 10000: return "🥇", "ゴールド"
        elif total >= 3000:  return "🥈", "シルバー"
        else:                return "🪙", "ブロンズ"

    try:
        _my_supports = get_db().table("supports").select(
            "creator_acct,creator_name,amount,message,created_at,reply_emoji,reply_text"
        ).eq("supporter_id", sup_user["supporter_id"]).order("created_at", desc=False).execute()

        _coin_map = {}
        for s in (_my_supports.data or []):
            acct = s["creator_acct"]
            if acct not in _coin_map:
                _coin_map[acct] = {"name": s["creator_name"], "total": 0, "count": 0, "records": []}
            _coin_map[acct]["total"] += s["amount"]
            _coin_map[acct]["count"] += 1
            _coin_map[acct]["records"].append(s)

        if _coin_map:
            # クリエイター情報を上書き
            _cr_info = get_db().table("creators").select("acct_id,display_name,name,photo_url,slug").in_(
                "acct_id", list(_coin_map.keys())
            ).execute()
            for r in (_cr_info.data or []):
                if r["acct_id"] in _coin_map:
                    _coin_map[r["acct_id"]]["display_name"] = r.get("display_name") or r.get("name") or r["acct_id"]
                    _coin_map[r["acct_id"]]["photo_url"]    = r.get("photo_url") or ""
                    _coin_map[r["acct_id"]]["slug"]         = r.get("slug") or r["acct_id"]

            for acct, data in _coin_map.items():
                coin_emoji, coin_name = _coin_level(data["total"])
                creator_name = data.get("display_name", data["name"])
                photo_url    = data.get("photo_url", "")
                # ラベルは短く・1行に収まるよう
                label = f"{coin_emoji} {creator_name}　{data['count']}回応援　｜　ランク: {coin_name}"
                with st.expander(label):
                    # アイコン + 累計を先頭に表示
                    _ic1, _ic2 = st.columns([1, 5])
                    with _ic1:
                        if photo_url:
                            st.markdown(
                                f'<img src="{photo_url}" style="width:48px;height:48px;border-radius:50%;object-fit:cover;">',
                                unsafe_allow_html=True
                            )
                        else:
                            st.markdown(
                                f'<div style="width:48px;height:48px;border-radius:50%;background:rgba(139,92,246,0.3);display:flex;align-items:center;justify-content:center;font-size:22px;">{coin_emoji}</div>',
                                unsafe_allow_html=True
                            )
                    with _ic2:
                        st.markdown(
                            f'<div style="font-weight:700;font-size:15px;color:#f0f0f5;">{creator_name}</div>'
                            f'<div style="font-size:12px;color:rgba(255,255,255,0.5);">累計 ¥{data["total"]:,}　｜　{coin_name}</div>',
                            unsafe_allow_html=True
                        )
                    st.markdown('<hr style="border:0;border-top:1px solid rgba(255,255,255,0.08);margin:10px 0;">', unsafe_allow_html=True)
                    for i, rec in enumerate(data["records"]):
                        replied = "✉️ 返信あり" if rec.get("reply_emoji") or rec.get("reply_text") else "📭 未返信"
                        date_str = rec["created_at"][:10]
                        st.markdown(f"**第{i+1}刻印** — {date_str}　｜　¥{rec['amount']:,}　｜　{replied}")
                        if rec.get("message"):
                            st.caption(f"💬 メッセージ: {rec['message']}")
                        if rec.get("reply_emoji") or rec.get("reply_text"):
                            st.caption(f"↩️ 返信: {rec.get('reply_emoji','')} {rec.get('reply_text','')}")
                        if i < len(data["records"]) - 1:
                            st.markdown('<hr style="border:0;border-top:1px solid rgba(255,255,255,0.08);margin:8px 0;">', unsafe_allow_html=True)
        else:
            st.info("まだ応援コインがありません。応援するとここにコインが刻まれます🪙")
    except Exception as e:
        st.warning(f"コインの読み込みに失敗しました: {e}")

    # ── シェア ──────────────────────────────────────────
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="header" style="font-size:16px;">📊 応援実績をシェアする</div>', unsafe_allow_html=True)
    portfolio_url = f"{BASE_URL}?page=portfolio&id={sup_user['supporter_id']}"
    st.link_button("🌐 応援実績ページを見る（公開用）", portfolio_url, use_container_width=True)
    st.code(portfolio_url, language="text")

    # ── ② クリエーターになる ──────────────────────────────
    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="header" style="font-size:16px;">🎨 クリエーターとして活動する</div>', unsafe_allow_html=True)
    try:
        _sup_row = get_db().table("supporters").select("creator_acct_id").eq("supporter_id", sup_user["supporter_id"]).maybe_single().execute()
        _linked_creator = (_sup_row.data or {}).get("creator_acct_id")
    except Exception:
        _linked_creator = None

    if _linked_creator:
        st.success(f"✅ クリエーターID `{_linked_creator}` と連携済みです")
        if st.button("🎨 クリエーターダッシュボードへ切り替え", use_container_width=True, key="switch_creator"):
            st.session_state["creator_auth"] = _linked_creator
            st.query_params["page"] = "dashboard"
            st.query_params["acct"] = _linked_creator
            st.rerun()
    else:
        st.markdown('<div style="font-size:13px;color:rgba(240,240,245,0.6);margin-bottom:12px;">応援するだけでなく、自分もクリエーターとして活動できます。クリエーターIDを発行して応援を受け取りましょう。</div>', unsafe_allow_html=True)
        if st.button("🎨 クリエーターになる（無料）", use_container_width=True, type="primary", key="become_creator"):
            try:
                # DBから最新のsub情報を取得（session_stateにはsub系は保存していないため）
                _sup_full = get_db().table("supporters").select("display_name,email,google_sub,discord_sub,line_sub").eq("supporter_id", sup_user["supporter_id"]).maybe_single().execute()
                _sup_data = _sup_full.data or {}
                _c_name  = _sup_data.get("display_name") or sup_user.get("display_name") or "クリエーター"
                _c_email = _sup_data.get("email") or sup_user.get("email") or ""
                _c_gsub  = _sup_data.get("google_sub") or ""
                _c_dsub  = _sup_data.get("discord_sub") or ""
                _c_lsub  = _sup_data.get("line_sub") or ""
                _use_acct_id = None

                # 各OAuthのsubが一致するクリエーターがいれば既存を使う（重複作成防止）
                for _sub_col, _sub_val in [("google_sub", _c_gsub), ("discord_sub", _c_dsub), ("line_sub", _c_lsub)]:
                    if _sub_val and not _use_acct_id:
                        _ex = get_db().table("creators").select("acct_id").eq(_sub_col, _sub_val).limit(1).execute()
                        if _ex.data:
                            _use_acct_id = _ex.data[0]["acct_id"]

                if not _use_acct_id:
                    _use_acct_id = "usr_" + uuid.uuid4().hex[:16]
                    _ins = {
                        "acct_id": _use_acct_id, "display_name": _c_name, "name": _c_name,
                        "email": _c_email, "password_hash": "",
                        "supporter_id": sup_user["supporter_id"],
                        "profile_done": False, "payout_enabled": False,
                    }
                    if _c_gsub: _ins["google_sub"] = _c_gsub
                    if _c_dsub: _ins["discord_sub"] = _c_dsub
                    if _c_lsub: _ins["line_sub"]    = _c_lsub
                    get_db().table("creators").insert(_ins).execute()

                get_db().table("supporters").update({"creator_acct_id": _use_acct_id}).eq("supporter_id", sup_user["supporter_id"]).execute()
                st.success(f"✅ クリエーターID `{_use_acct_id}` を発行しました！")
                st.session_state["creator_auth"] = _use_acct_id
                st.query_params["page"] = "dashboard"
                st.query_params["acct"] = _use_acct_id
                st.rerun()
            except Exception as _ce:
                st.error(f"クリエーター作成エラー: {_ce}")

    st.markdown('<div class="oshi-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="header" style="font-size:16px;">⚙️ アカウント設定</div>', unsafe_allow_html=True)

    # OAuth判定 + creator_acct_id 取得（一度だけ）
    _sup_acct_row = get_db().table("supporters").select("creator_acct_id,google_sub,discord_sub,line_sub").eq("supporter_id", sup_user["supporter_id"]).maybe_single().execute()
    _sup_is_oauth   = bool((_sup_acct_row.data or {}).get("google_sub") or (_sup_acct_row.data or {}).get("discord_sub") or (_sup_acct_row.data or {}).get("line_sub"))
    _mn_creator_acct = (_sup_acct_row.data or {}).get("creator_acct_id")  # NULLならNone

    with st.expander("✏️ 表示名を変更する"):
        _cur_name = sup_user.get("display_name", "")
        mn_new  = st.text_input("新しい表示名", value=_cur_name, key="mn_new")
        mn_sync = st.checkbox("クリエーター名も同じにする", key="mn_sync") if _mn_creator_acct else False
        if st.button("表示名を更新", key="mn_btn"):
            if mn_new.strip():
                get_db().table("supporters").update({"display_name": mn_new.strip()}).eq("supporter_id", sup_user["supporter_id"]).execute()
                st.session_state["supporter_auth"]["display_name"] = mn_new.strip()
                if mn_sync and _mn_creator_acct:
                    get_db().table("creators").update({"display_name": mn_new.strip()}).eq("acct_id", _mn_creator_acct).execute()
                st.success("表示名を更新しました！")
                st.rerun()
            else:
                st.warning("表示名を入力してください。")

    if _sup_is_oauth:
        st.caption("💡 LINE / Google / Discord でログイン中のため、メールアドレス・パスワードの変更はできません。")
    else:
     with st.expander("📧 メールアドレスを変更する"):
        _cur_email = sup_user.get("email", "")
        me_new = st.text_input("新しいメールアドレス", value=_cur_email, key="me_new")
        me_pass = st.text_input("現在のパスワード（確認）", type="password", key="me_pass")
        if st.button("メールアドレスを更新", key="me_btn"):
            if me_new.strip() and "@" in me_new:
                _chk = get_db().table("supporters").select("password_hash").eq("supporter_id", sup_user["supporter_id"]).execute()
                if _chk.data and _chk.data[0].get("password_hash") == hash_password(me_pass):
                    _new_email_lc = me_new.strip().lower()
                    _dup = get_db().table("supporter_accounts").select("supporter_id").eq("email", _new_email_lc).limit(1).execute()
                    if _dup.data and _dup.data[0]["supporter_id"] != sup_user["supporter_id"]:
                        st.error("このメールアドレスは既に使用されています。")
                    else:
                        get_db().table("supporters").update({"email": _new_email_lc}).eq("supporter_id", sup_user["supporter_id"]).execute()
                        try:
                            get_db().table("supporter_accounts").update({"email": _new_email_lc}).eq("supporter_id", sup_user["supporter_id"]).execute()
                        except Exception:
                            pass
                        # 紐づきクリエーターに強制同期（_mn_creator_acct を流用）
                        if _mn_creator_acct:
                            try:
                                get_db().table("creators").update({"email": _new_email_lc}).eq("acct_id", _mn_creator_acct).execute()
                            except Exception:
                                pass
                        st.session_state["supporter_auth"]["email"] = _new_email_lc
                        st.success("メールアドレスを更新しました！")
                        st.rerun()
                else:
                    st.error("パスワードが違います。")
            else:
                st.warning("正しいメールアドレスを入力してください。")

    if not _sup_is_oauth:
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
                        try:
                            get_db().table("supporter_accounts").update({"password_hash": hash_password(cp_new)}).eq("supporter_id", sup_user["supporter_id"]).execute()
                        except Exception:
                            pass
                        # 紐づきクリエーターに強制同期（_mn_creator_acct を流用）
                        if _mn_creator_acct:
                            try:
                                get_db().table("creators").update({"password_hash": hash_password(cp_new)}).eq("acct_id", _mn_creator_acct).execute()
                            except Exception:
                                pass
                        st.success("パスワードを更新しました！")
                    else:
                        st.error("現在のパスワードが違います。")
            else:
                st.warning("全ての項目を入力してください。")
    # ── ① サポーターIDマージ（OTP認証付き）────────────────────────────
    with st.expander("🔀 別のサポーターIDをマージする"):
        st.caption("2つのIDを1つに統合します。マージ元のIDとコイン・履歴がすべてこのIDに引き継がれます。")

        if not st.session_state.get("_mg_otp_sent"):
            # ── ステップ1: ID入力 ──
            mg_other = st.text_input("マージしたいサポーターID（統合元）", key="mg_other", placeholder="sup_xxxx")
            if st.button("IDを確認してコードを送信", key="mg_check"):
                if mg_other.strip() == sup_user["supporter_id"]:
                    st.error("自分自身のIDは入力できません。")
                elif mg_other.strip():
                    _mg_row = get_db().table("supporters").select("supporter_id,display_name,email").eq("supporter_id", mg_other.strip()).maybe_single().execute()
                    if not _mg_row.data:
                        st.error("そのサポーターIDは見つかりません。")
                    elif not _mg_row.data.get("email"):
                        st.error("⚠️ このIDにはメールアドレスが登録されていないため、マージできません。")
                    else:
                        import random, time as _time
                        _otp = f"{random.randint(0, 999999):06d}"
                        _ok, _err = send_merge_otp_email(_mg_row.data["email"], _otp)
                        if _ok:
                            _mg_cnt = get_db().table("supports").select("support_id", count="exact").eq("supporter_id", mg_other.strip()).execute()
                            _my_cnt = get_db().table("supports").select("support_id", count="exact").eq("supporter_id", sup_user["supporter_id"]).execute()
                            st.session_state["_mg_confirmed"] = mg_other.strip()
                            st.session_state["_mg_name"] = _mg_row.data.get("display_name") or "名前なし"
                            st.session_state["_mg_cnt_src"] = _mg_cnt.count or 0
                            st.session_state["_mg_cnt_dst"] = _my_cnt.count or 0
                            st.session_state["_mg_otp"] = _otp
                            st.session_state["_mg_otp_time"] = _time.time()
                            st.session_state["_mg_otp_sent"] = True
                            st.session_state["_mg_email_hint"] = _mg_row.data["email"][:3] + "***"
                            st.rerun()
                        else:
                            st.error(f"メール送信に失敗しました: {_err}")
        else:
            # ── ステップ2: OTP入力 ──
            import time as _time
            _elapsed = _time.time() - st.session_state.get("_mg_otp_time", 0)
            if _elapsed > 300:
                st.error("⏱️ コードの有効期限（5分）が切れました。もう一度やり直してください。")
                for _k in ["_mg_confirmed","_mg_otp","_mg_otp_time","_mg_otp_sent","_mg_email_hint","_mg_name","_mg_cnt_src","_mg_cnt_dst"]:
                    st.session_state.pop(_k, None)
                st.rerun()

            _hint = st.session_state.get("_mg_email_hint", "")
            _src_id = st.session_state.get("_mg_confirmed", "")
            _src_name = st.session_state.get("_mg_name", "")
            _cnt_src = st.session_state.get("_mg_cnt_src", 0)
            _cnt_dst = st.session_state.get("_mg_cnt_dst", 0)
            st.info(f"""
**マージ元:** `{_src_id}` ({_src_name}) — 応援 {_cnt_src} 件
**マージ先（このID）:** `{sup_user['supporter_id']}` — 応援 {_cnt_dst} 件
→ 合計 {_cnt_src + _cnt_dst} 件になります
            """)
            st.success(f"📧 `{_src_id}` に登録されたメールアドレス（{_hint}）に6桁の確認コードを送信しました。")
            st.caption(f"⏱️ 有効期限: 5分（残り約 {max(0, 300 - int(_elapsed))} 秒）")
            mg_otp_input = st.text_input("6桁の確認コードを入力", key="mg_otp_input", placeholder="123456", max_chars=6)
            st.warning("⚠️ マージすると元のIDは削除されます。この操作は取り消せません。")
            _col1, _col2 = st.columns(2)
            with _col1:
                if st.button("✅ マージを実行する", key="mg_exec", type="primary"):
                    if mg_otp_input.strip() == st.session_state.get("_mg_otp"):
                        _src = st.session_state["_mg_confirmed"]
                        try:
                            get_db().table("supports").update({"supporter_id": sup_user["supporter_id"]}).eq("supporter_id", _src).execute()
                            try:
                                get_db().table("pending_supports").update({"supporter_id": sup_user["supporter_id"]}).eq("supporter_id", _src).execute()
                            except Exception:
                                pass
                            get_db().table("supporters").delete().eq("supporter_id", _src).execute()
                            try:
                                get_db().table("supporter_accounts").delete().eq("supporter_id", _src).execute()
                            except Exception:
                                pass
                            for _k in ["_mg_confirmed","_mg_otp","_mg_otp_time","_mg_otp_sent","_mg_email_hint","_mg_name","_mg_cnt_src","_mg_cnt_dst"]:
                                st.session_state.pop(_k, None)
                            st.success(f"✅ `{_src}` のデータをマージしました！")
                            st.rerun()
                        except Exception as _me:
                            st.error(f"マージエラー: {_me}")
                    else:
                        st.error("❌ コードが一致しません。もう一度確認してください。")
            with _col2:
                if st.button("キャンセル", key="mg_cancel"):
                    for _k in ["_mg_confirmed","_mg_otp","_mg_otp_time","_mg_otp_sent","_mg_email_hint","_mg_name","_mg_cnt_src","_mg_cnt_dst"]:
                        st.session_state.pop(_k, None)
                    st.rerun()

    if st.button("🚪 ログアウト", type="secondary"):
        del st.session_state["supporter_auth"]
        st.rerun()
    st.stop()

else: # Dashboard
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">QRコードを発行</div>', unsafe_allow_html=True)
    # アカウントIDの特定
    acct_id = connect_acct or params.get("acct")
    # acct_id / slug / usr_ いずれでもOK → 実際の acct_id に解決
    if acct_id and not acct_id.startswith("acct_"):
        try:
            _slug_res = get_db().table("creators").select("acct_id").or_(
                f"acct_id.eq.{acct_id},slug.eq.{acct_id}"
            ).limit(1).execute()
            if _slug_res.data:
                acct_id = _slug_res.data[0]["acct_id"]
        except Exception:
            pass

    if not acct_id:
        if not params.get("fresh"):
            # ① localStorage からアカウントIDを自動復元
            components.html(f"""<script>
            (function(){{
              try {{
                var saved = localStorage.getItem('oshipay_acct');
                if (saved && (saved.startsWith('acct_') || saved.startsWith('usr_'))) {{
                  window.parent.location.href = '{BASE_URL}?page=dashboard&acct=' + encodeURIComponent(saved);
                }}
              }} catch(e) {{}}
            }})();
            </script>""", height=0)
        st.markdown('<div class="header">応援用QRコードを作成・復元</div>', unsafe_allow_html=True)
        st.write("新しく応援（決済）を受け取るための設定を行うか、以前作成したアカウントを復元します。")

        # ── Googleアカウントで紐づけ選択（複数候補） ──
        if st.session_state.get("_gc_link_info"):
            _gcli = st.session_state["_gc_link_info"]
            _gcli_sub_field = "discord_sub" if _gcli.get("provider") == "discord" else "google_sub"
            _gcli_provider_name = "Discord" if _gcli.get("provider") == "discord" else "Google"
            st.markdown(f"""
            <div style="background:rgba(66,133,244,0.1);border:1px solid rgba(66,133,244,0.35);
                        border-radius:12px;padding:16px;margin-bottom:12px;">
              <div style="font-weight:700;color:#93c5fd;margin-bottom:4px;">{_gcli_provider_name}アカウントで確認</div>
              <div style="font-size:12px;color:rgba(240,240,245,0.6);">
                <b>{_gcli['email']}</b> はすでに複数のアカウントで使用されています。<br>
                どのアカウントに{_gcli_provider_name}ログインを紐づけますか？
              </div>
            </div>
            """, unsafe_allow_html=True)
            for _gc_cand in _gcli["candidates"]:
                _btn_label = f"✅ {_gc_cand['display_name']} ({_gc_cand['acct_id']})"
                if st.button(_btn_label, key=f"gc_link_{_gc_cand['acct_id']}", use_container_width=True):
                    get_db().table("creators").update({_gcli_sub_field: _gcli["sub"]}).eq("acct_id", _gc_cand["acct_id"]).execute()
                    st.session_state["creator_auth"] = _gc_cand["acct_id"]
                    del st.session_state["_gc_link_info"]
                    st.query_params["acct"] = _gc_cand["acct_id"]
                    st.rerun()
            if st.button("➕ 新規アカウントとして登録する", use_container_width=True):
                _gc_new_id = "usr_" + uuid.uuid4().hex[:16]
                get_db().table("creators").insert({
                    "acct_id": _gc_new_id, "email": _gcli["email"] + f"+g{uuid.uuid4().hex[:4]}",
                    _gcli_sub_field: _gcli["sub"], "display_name": _gcli["name"], "password_hash": "",
                }).execute()
                st.session_state["creator_auth"] = _gc_new_id
                del st.session_state["_gc_link_info"]
                st.query_params["acct"] = _gc_new_id
                st.rerun()
            st.stop()

        # ── みなし同意文言 ──
        st.markdown("""
        <div style="font-size:11px;color:rgba(240,240,245,0.45);text-align:center;margin-bottom:10px;line-height:1.6;">
        登録またはログインすることで、<a href="https://oshipay.me/terms" target="_blank" style="color:rgba(180,180,255,0.7);">利用規約</a>・<a href="https://oshipay.me/privacy" target="_blank" style="color:rgba(180,180,255,0.7);">プライバシーポリシー</a>に同意したものとみなします。<br>
        ※13歳未満の方はご利用いただけません。18歳未満の方が受取機能を利用する場合は親権者の同意が必要です。
        </div>
        """, unsafe_allow_html=True)

        # ── ソーシャルログインボタン（LINE → Google → Discord）──
        if LINE_CLIENT_ID:
            _render_line_button(_line_auth_url("l_creator"))
        if GOOGLE_CLIENT_ID:
            _render_google_button(_google_auth_url("g_creator"))
            if DISCORD_CLIENT_ID:
                _render_discord_button(_discord_auth_url("d_creator"))
        if LINE_CLIENT_ID or GOOGLE_CLIENT_ID:
            st.markdown('<div style="text-align:center;color:rgba(255,255,255,0.35);font-size:12px;margin:4px 0 12px;">── または ID・パスワードで ──</div>', unsafe_allow_html=True)

        # ?tab=new のときは新規作成をデフォルト、それ以外は既存アカウントをデフォルト
        if st.query_params.get("tab") == "new":
            tab_new, tab_recover, tab_forgot_c = st.tabs(["✨ 新規作成", "🔑 既存アカウント", "🔓 パスワードを忘れた"])
        else:
            tab_recover, tab_new, tab_forgot_c = st.tabs(["🔑 既存アカウント", "✨ 新規作成", "🔓 パスワードを忘れた"])

        with tab_new:
            # 「1回だけ・一生使えるQR」訴求
            st.markdown("""
            <div style="background:rgba(139,92,246,0.12);border:1px solid rgba(139,92,246,0.3);border-radius:12px;padding:14px 16px;margin-bottom:12px;text-align:center;">
                <div style="font-size:15px;font-weight:700;color:#c4b5fd;">✨ 1回の設定で一生使えるQRコード</div>
                <div style="font-size:11px;color:rgba(240,240,245,0.6);margin-top:4px;">無料で始められます。収益化は後からでもOK！</div>
            </div>
            """, unsafe_allow_html=True)

            new_email = st.text_input("メールアドレス（必須）", key="new_email", placeholder="example@gmail.com")
            st.caption("🔐 パスワード条件: 8文字以上・英字＋数字必須・同じ文字の3連続禁止（例: Oshi1234）")
            new_pass = st.text_input("管理用パスワードを作成", type="password", key="new_pass")

            _pass_ok = False
            if new_pass:
                _pass_ok, _pass_err = validate_password(new_pass)
                if not _pass_ok:
                    st.error(f"⚠️ {_pass_err}")
                else:
                    st.success("✅ パスワードOK")

            # 作成中フラグ（連打防止）
            _reg_creating = st.session_state.get("_reg_creating", False)

            _btn_disabled = _reg_creating or not (new_email and _pass_ok)
            if st.button("✨ 応援ページを作成する（無料）", type="primary",
                         disabled=_btn_disabled, use_container_width=True):
                st.session_state["_reg_creating"] = True
                with st.spinner("応援ページを作成しています..."):
                    try:
                        _email_count = get_db().table("creators").select("acct_id").eq("email", new_email.strip().lower()).execute()
                        if len(_email_count.data or []) >= 10:
                            st.session_state["_reg_creating"] = False
                            st.error("このメールアドレスはすでに10アカウントに使用されています。別のメールアドレスをお使いください。")
                            st.stop()
                        creator_id = "usr_" + uuid.uuid4().hex[:16]
                        _reg_ok, _reg_err = register_creator(creator_id, new_pass, email=new_email)
                        if not _reg_ok:
                            st.session_state["_reg_creating"] = False
                            st.error(f"登録エラー: {_reg_err}")
                            st.stop()
                        send_acct_id_email(new_email, creator_id)
                    except Exception as _e:
                        st.session_state["_reg_creating"] = False
                        st.error(f"エラー: {_e}")
                        st.stop()
                # 作成完了 → ダッシュボードへ遷移
                st.session_state["_reg_creating"] = False
                st.session_state["creator_auth"] = creator_id
                st.success("✅ 作成完了！ダッシュボードへ移動します...")
                st.query_params.update({"page": "dashboard", "acct": creator_id})
                st.rerun()

        with tab_recover:
            # ── 既存アカウント復元フォーム ──
            st.markdown("""
            <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);
                        border-radius:14px;padding:16px 20px;margin-bottom:4px;">
                <div style="font-size:13px;font-weight:700;color:rgba(240,240,245,0.85);margin-bottom:4px;">
                    🔑 既にアカウントをお持ちの方
                </div>
                <div style="font-size:12px;color:rgba(240,240,245,0.5);">
                    ユーザーID（slug）・<code>usr_</code>・<code>acct_</code> どれでもログインできます
                </div>
            </div>
            """, unsafe_allow_html=True)
            recover_input = st.text_input("ユーザーID または アカウントID", placeholder="例: nana  /  usr_xxxx  /  acct_xxxx", label_visibility="collapsed")
            recover_pass = st.text_input("パスワード", type="password", placeholder="パスワードを入力")
            if st.button("✅ このアカウントで開く", use_container_width=True):
                rid = recover_input.strip()
                if rid and len(rid) >= 2 and recover_pass:
                    # acct_id OR slug どちらでも検索
                    try:
                        _r = get_db().table("creators").select("acct_id,password_hash").or_(
                            f"acct_id.eq.{rid},slug.eq.{rid}"
                        ).limit(1).execute()
                    except Exception as _e:
                        st.error(f"DB接続エラー: {_e}")
                        _r = None
                    if _r and _r.data:
                        real_id = _r.data[0]["acct_id"]
                        if verify_creator(real_id, recover_pass):
                            st.query_params["acct"] = real_id
                            st.session_state["creator_auth"] = real_id
                            st.rerun()
                        else:
                            st.error("パスワードが間違っています。")
                    else:
                        st.error("アカウントが見つかりません。IDを確認してください。")
                else:
                    st.error("IDとパスワードを入力してください。")

        with tab_forgot_c:
            st.markdown('<div style="font-size:12px;color:rgba(255,255,255,0.6);margin-bottom:12px;">登録時のメールアドレスで本人確認し、仮パスワードを発行します。<br>ユーザーID（slug）・usr_・acct_ どれでも入力できます。</div>', unsafe_allow_html=True)
            fc_acct  = st.text_input("ユーザーID または アカウントID", key="fc_acct", placeholder="例: nana  /  usr_xxxx  /  acct_xxxx")
            fc_email = st.text_input("登録メールアドレス", key="fc_email", placeholder="example@email.com")
            if st.button("仮パスワードを発行", key="fc_btn", use_container_width=True):
                if fc_acct and fc_email:
                    # acct_id OR slug で検索して real acct_id を取得
                    try:
                        _fc_r = get_db().table("creators").select("acct_id,email").or_(
                            f"acct_id.eq.{fc_acct.strip()},slug.eq.{fc_acct.strip()}"
                        ).limit(1).execute()
                        _fc_row = _fc_r.data[0] if _fc_r.data else None
                    except Exception:
                        _fc_row = None

                    if not _fc_row:
                        st.error("アカウントが見つかりません。")
                    else:
                        _fc_real_id = _fc_row["acct_id"]
                        _fc_db_email = _fc_row.get("email", "")
                        if _fc_real_id.startswith("acct_") and not _fc_db_email:
                            # 旧Stripeアカウント: Stripe APIでメール照合
                            try:
                                acct_info = stripe.Account.retrieve(_fc_real_id)
                                _fc_db_email = acct_info.get("email", "")
                            except Exception:
                                pass
                        if _fc_db_email and _fc_db_email.lower() == fc_email.strip().lower():
                            temp_pass = uuid.uuid4().hex[:8]
                            get_db().table("creators").update({"password_hash": hash_password(temp_pass)}).eq("acct_id", _fc_real_id).execute()
                            st.success("本人確認完了！ログイン後にパスワードを変更してください。")
                            st.info(f"🔑 仮パスワード: `{temp_pass}`")
                        else:
                            st.error("メールアドレスが一致しません。")
                else:
                    st.warning("IDとメールアドレスを入力してください。")
    else:
        # 認証チェック
        if st.session_state.get("creator_auth") != acct_id:
            st.warning("このダッシュボードを開くにはパスワードが必要です。")
            if LINE_CLIENT_ID:
                _render_line_button(_line_auth_url("l_creator"), label="LINEアカウントでログイン")
            if GOOGLE_CLIENT_ID:
                _render_google_button(_google_auth_url("g_creator"), label="Googleアカウントでログイン")
                if DISCORD_CLIENT_ID:
                    _render_discord_button(_discord_auth_url("d_creator"), label="Discordアカウントでログイン")
            if LINE_CLIENT_ID or GOOGLE_CLIENT_ID:
                st.markdown('<div style="text-align:center;color:rgba(255,255,255,0.35);font-size:12px;margin:4px 0 10px;">── または パスワードで ──</div>', unsafe_allow_html=True)
            auth_pass = st.text_input("パスワードを入力", type="password", key="auth_pass")
            if st.button("🔓 ログイン", type="primary"):
                try:
                    resp = get_db().table("creators").select("*").eq("acct_id", acct_id).execute()
                except Exception:
                    st.error("現在データベースが起動中です。数分後にページを再読み込みしてください。")
                    st.stop()
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

        _icon_list = list(ICON_OPTIONS.keys())

        # ── プロフィールテキスト（先に取得してdisplay_nameをデフォルト値に使う）──
        try:
            _cr = get_db().table("creators").select("bio,genre,slug,photo_url,display_name,sns_links,profile_done,stripe_acct_id,email,google_sub,discord_sub,line_sub").eq("acct_id", acct_id).maybe_single().execute()
            _cr_data = _cr.data or {}
        except Exception:
            _cr_data = {}

        # ── スタンプ数・推定換算・収益化ボタン ──
        try:
            _my_stamp_resp = get_db().table("stamps").select("id", count="exact").eq("creator_acct", acct_id).execute()
            _my_stamp_count = _my_stamp_resp.count or 0
        except Exception:
            _my_stamp_count = 0
        _est_yen    = _my_stamp_count * 100

        # ── Stripeの完了状態をリアルタイムで確認 ──
        # stripe_acct_idがDBにあっても、Stripe側でonboardingが完了していなければ未登録扱い
        _raw_stripe_acct = _cr_data.get("stripe_acct_id") or (acct_id if acct_id.startswith("acct_") else "")
        _stripe_payouts_ok = False
        _stripe_incomplete = False  # stripe_acct_idはあるがonboarding未完了
        if _raw_stripe_acct:
            _st_status = check_account_status(_raw_stripe_acct)
            if _st_status:
                _stripe_payouts_ok = _st_status.get("payouts_enabled", False)
                _stripe_incomplete = not _stripe_payouts_ok  # acctはあるが未完了
                # 完了確認できたらDBのpayout_enabledを更新
                if _stripe_payouts_ok:
                    _prev_payout = _cr_data.get("payout_enabled", False)
                    try:
                        get_db().table("creators").update({"payout_enabled": True}).eq("acct_id", acct_id).execute()
                    except Exception:
                        pass
                    # ── 初めてpayout_enabledになった瞬間: pending全件に支払いURLメール送信 ──
                    if not _prev_payout:
                        try:
                            # ── locked_rank を確定（既存support数 + 予約順で固定）──
                            _exist_cnt = len(get_db().table("supports").select("id").eq("creator_acct", acct_id).execute().data or [])
                            _pend_for_rank = get_db().table("pending_supports").select("id,reservation_no").eq("creator_acct", acct_id).eq("status", "pending").order("reservation_no").execute().data or []
                            for _ri, _rp in enumerate(_pend_for_rank):
                                try:
                                    get_db().table("pending_supports").update({"locked_rank": _exist_cnt + _ri + 1}).eq("id", _rp["id"]).execute()
                                except Exception:
                                    pass
                            _pend_notify = get_db().table("pending_supports").select("*").eq("creator_acct", acct_id).eq("status", "pending").execute()
                            _pend_list = _pend_notify.data or []
                            _sent_count = 0
                            _creator_display = _cr_data.get("display_name") or _cr_data.get("name") or acct_id
                            # supporter display_name をバッチ取得
                            _pn_sup_ids = [_pn.get("supporter_id") for _pn in _pend_list if _pn.get("supporter_id")]
                            _pn_sup_map = get_supporters_map(_pn_sup_ids) if _pn_sup_ids else {}
                            for _pn in _pend_list:
                                _pn_email = _pn.get("supporter_email", "")
                                if not _pn_email:
                                    continue
                                _pn_pid = str(_pn.get("id", ""))
                                _pay_url = f"{BASE_URL}?page=pay_pending&pid={_pn_pid}&email={urllib.parse.quote(_pn_email)}"
                                # 有効期限を JST で整形
                                _exp_at = _pn.get("expires_at", "")
                                try:
                                    _exp_dt = datetime.datetime.fromisoformat(_exp_at.replace("Z", "+00:00"))
                                    _exp_jst = _exp_dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
                                    _exp_str = _exp_jst.strftime("%Y/%m/%d %H:%M（JST）")
                                except Exception:
                                    _exp_str = "72時間以内"
                                _pn_disp_name = _pn_sup_map.get(_pn.get("supporter_id", ""), "") or ""
                                send_pending_payment_url_email(_pn_email, _creator_display, _pn["amount"], _pay_url, _exp_str, display_name=_pn_disp_name)
                                _sent_count += 1
                            if _sent_count > 0:
                                st.toast(f"📧 {_sent_count}名のサポーターに支払いURLを送信しました", icon="✅")
                        except Exception:
                            pass
            else:
                _stripe_incomplete = True  # 取得失敗＝未完了扱い
        _has_stripe = _stripe_payouts_ok

        # ── pending_supports 集計（登録済み・未登録ともに取得）──
        _pending_total = 0
        _pending_rows  = []
        try:
            import datetime as _dt
            _now_iso = _dt.datetime.now(_dt.timezone.utc).isoformat()
            _pr = get_db().table("pending_supports").select("amount,message,contact_info,created_at").eq("creator_acct", acct_id).eq("status", "pending").gte("expires_at", _now_iso).execute()
            _pending_rows  = _pr.data or []
            _pending_total = sum(r["amount"] for r in _pending_rows)
        except Exception:
            pass
        _pending_msg_count = sum(1 for r in _pending_rows if r.get("message"))

        # ① スタンプカード：登録済みは「受取設定済み」表示
        if _has_stripe:
            st.markdown(f"""
            <div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:14px;padding:16px 20px;margin-bottom:16px;text-align:center;">
                <div style="font-size:12px;color:rgba(240,240,245,0.5);margin-bottom:4px;">💜 あなたへの応援スタンプ</div>
                <div style="font-size:28px;font-weight:900;color:#c4b5fd;">{_my_stamp_count} スタンプ</div>
                <div style="font-size:13px;color:#4ade80;font-weight:700;margin-top:6px;">✅ 受取設定済み</div>
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"""
            <div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);border-radius:14px;padding:16px 20px;margin-bottom:16px;text-align:center;">
                <div style="font-size:12px;color:rgba(240,240,245,0.5);margin-bottom:4px;">💜 あなたへの応援スタンプ</div>
                <div style="font-size:28px;font-weight:900;color:#c4b5fd;">{_my_stamp_count} スタンプ</div>
                <div style="font-size:13px;color:rgba(240,240,245,0.6);margin-top:4px;">
                    受け取り設定をすると 推定
                    <span style="color:#f97316;font-weight:700;">{_est_yen:,}円</span> が受け取れます
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ② pending 送金希望：未登録→金額のみ / 登録済み→金額＋メッセージ全開放
        if _pending_total > 0:
            if not _has_stripe:
                st.markdown(f"""
                <div style="background:rgba(251,191,36,0.08);border:1px solid rgba(251,191,36,0.35);border-radius:14px;padding:16px 20px;margin-bottom:16px;">
                    <div style="font-size:12px;color:#fbbf24;font-weight:700;margin-bottom:8px;">💰 送金希望が届いています</div>
                    <div style="font-size:24px;font-weight:900;color:#f97316;margin-bottom:6px;">{_pending_total:,}円 相当</div>
                    <div style="font-size:11px;color:rgba(240,240,245,0.5);line-height:1.6;">
                        ※確約ではありません。口座登録完了後にファンへ連絡し、入金確認後に確定します。<br>
                        ⚠️ 72時間以内に口座登録が確認できない場合、リセットされます。
                    </div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:rgba(74,222,128,0.08);border:1px solid rgba(74,222,128,0.35);border-radius:14px;padding:16px 20px;margin-bottom:16px;">
                    <div style="font-size:12px;color:#4ade80;font-weight:700;margin-bottom:8px;">💰 送金希望（口座登録済み・確認待ち）</div>
                    <div style="font-size:24px;font-weight:900;color:#f97316;margin-bottom:6px;">{_pending_total:,}円</div>
                    <div style="font-size:11px;color:rgba(240,240,245,0.5);">ファンに連絡して入金確認後に確定します。72時間以内に振り込みない場合には強制キャンセルとなります。</div>
                </div>
                """, unsafe_allow_html=True)

        if _pending_msg_count > 0:
            if not _has_stripe:
                st.markdown(f"""
                <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.3);border-radius:14px;padding:14px 18px;margin-bottom:16px;">
                    <div style="font-size:13px;color:#c4b5fd;font-weight:700;">💌 応援メッセージが {_pending_msg_count} 件届いています</div>
                    <div style="font-size:11px;color:rgba(240,240,245,0.45);margin-top:6px;">※内容は口座登録完了後に全開放されます。</div>
                </div>
                """, unsafe_allow_html=True)
            else:
                # 口座登録済み → 全内容を表示
                st.markdown(f'<div style="font-size:13px;color:#c4b5fd;font-weight:700;margin-bottom:10px;">💌 応援メッセージ（{_pending_msg_count}件）</div>', unsafe_allow_html=True)
                import html as _html_mod
                for _pmr in _pending_rows:
                    if _pmr.get("message"):
                        _safe_msg = _html_mod.escape(str(_pmr["message"]))
                        _safe_amt = f'{_pmr["amount"]:,}'
                        st.markdown(f"""
                        <div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.25);border-radius:12px;padding:12px 14px;margin-bottom:8px;">
                            <div style="font-size:13px;color:#f0f0f5;line-height:1.6;">{_safe_msg}</div>
                            <div style="font-size:11px;color:rgba(240,240,245,0.4);margin-top:6px;">💰 {_safe_amt}円</div>
                        </div>
                        """, unsafe_allow_html=True)

        # ── Stripe リダイレクト（フォーム送信 target="_top" で確実に同タブ遷移）──
        if "_stripe_link_url" in st.session_state:
            _pending_stripe_url = st.session_state.pop("_stripe_link_url")
            st.components.v1.html(f"""
            <html><body style="margin:0;padding:0;background:transparent;">
            <form id="sf" action="{_pending_stripe_url}" method="GET" target="_top"
                  style="margin:0;padding:0;display:block;">
              <button type="submit"
                style="width:100%;background:linear-gradient(135deg,#8b5cf6,#6d28d9);
                       color:white;border:none;border-radius:12px;padding:16px;
                       font-size:16px;font-weight:900;cursor:pointer;box-sizing:border-box;">
                🏦 Stripeで受け取り設定する →
              </button>
            </form>
            <script>setTimeout(function(){{document.getElementById('sf').submit();}},150);</script>
            </body></html>
            """, height=64, scrolling=False)
            st.stop()

        if not _has_stripe:
            if _stripe_incomplete:
                # stripe_acct_idはあるがonboarding未完了→続きへ誘導
                try:
                    _resume_link = create_account_link(_raw_stripe_acct, creator_acct_id=acct_id)
                except Exception:
                    _resume_link = None
                st.markdown("""
                <div style="background:rgba(249,115,22,0.12);border:2px solid rgba(249,115,22,0.55);border-radius:16px;padding:20px;margin-bottom:16px;text-align:center;">
                    <div style="font-size:15px;font-weight:900;color:#f97316;margin-bottom:6px;">⚠️ Stripeの口座登録が途中です</div>
                    <div style="font-size:12px;color:rgba(240,240,245,0.7);line-height:1.8;">
                        銀行口座の登録が完了していません。<br>
                        応援金を受け取るには、Stripeの手続きを最後まで完了してください。
                    </div>
                </div>
                """, unsafe_allow_html=True)
                if _resume_link:
                    st.link_button("👉 Stripeの登録を続けて完了する", _resume_link, type="primary", use_container_width=True)
                st.caption("登録完了後、このページを再読み込みすると状態が更新されます。")
            else:
                # stripe_acct_id自体がない→完全な新規
                st.markdown("""
                <div style="background:rgba(249,115,22,0.1);border:1px solid rgba(249,115,22,0.4);border-radius:16px;padding:20px;margin-bottom:16px;text-align:center;">
                    <div style="font-size:15px;font-weight:900;color:#f97316;margin-bottom:6px;">💰 受取口座を登録して応援を受け取ろう</div>
                    <div style="font-size:12px;color:rgba(240,240,245,0.6);line-height:1.6;">
                        Stripeアカウントを作成すると、ファンからの応援金を受け取れます。<br>
                        登録済みのメールアドレスで自動入力されます。<br>
                        <span style="color:#f97316;font-weight:bold;">⚠️ 受取機能は18歳以上の方のみご利用いただけます。</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
            if not _stripe_incomplete and st.button("💰 受け取りを有効にする（収益化する）", type="primary", key="monetize_btn", use_container_width=True):
                try:
                    _cr_email = _cr_data.get("email") or ""
                    _new_stripe_kwargs = {
                        "type": "express", "country": "JP",
                        "capabilities": {"card_payments": {"requested": True}, "transfers": {"requested": True}},
                        "business_type": "individual",
                        "business_profile": {"mcc": "7922", "product_description": "oshipay - 投げ銭サービス", "url": BASE_URL},
                    }
                    if _cr_email:
                        _new_stripe_kwargs["email"] = _cr_email
                    _new_stripe_acct = stripe.Account.create(**_new_stripe_kwargs)
                    get_db().table("creators").update({"stripe_acct_id": _new_stripe_acct.id}).eq("acct_id", acct_id).execute()
                    _link_url = create_account_link(_new_stripe_acct.id, creator_acct_id=acct_id)
                    # session_state に保存して rerun → 次フレームで確実にリダイレクト
                    st.session_state["_stripe_link_url"] = _link_url
                    st.rerun()
                except Exception as _se:
                    st.error(f"エラー: {_se}")

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

        # ── プロフィール写真（一番上・丸枠センター）──
        _current_photo = _cr_data.get("photo_url") or ""
        if _current_photo:
            import time as _time
            _photo_cb = f"{_current_photo}?v={int(_time.time())}"
            st.markdown(f"""
            <div style="display:flex;justify-content:center;margin-bottom:16px;">
                <img src="{_photo_cb}" style="width:96px;height:96px;border-radius:50%;object-fit:cover;border:3px solid rgba(139,92,246,0.5);">
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div style="display:flex;justify-content:center;margin-bottom:16px;">
                <div style="width:96px;height:96px;border-radius:50%;background:rgba(139,92,246,0.15);border:3px dashed rgba(139,92,246,0.4);display:flex;align-items:center;justify-content:center;font-size:32px;">👤</div>
            </div>
            """, unsafe_allow_html=True)
        uploaded_photo = st.file_uploader("📷 プロフィール写真を選ぶ（任意・自動圧縮）", type=["jpg", "jpeg", "png"], key=f"photo_{acct_id}")
        if uploaded_photo:
            import base64 as _b64
            _raw_b64 = _b64.b64encode(uploaded_photo.read()).decode()
            _mime = "image/jpeg" if uploaded_photo.name.lower().endswith((".jpg",".jpeg")) else "image/png"
            _supa_url  = st.secrets["SUPABASE_URL"].rstrip("/")
            _supa_key  = st.secrets["SUPABASE_KEY"]
            _storage_path = f"creators/{acct_id}.jpg"
            _cropper_html = f"""
            <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.css"/>
            <script src="https://cdnjs.cloudflare.com/ajax/libs/cropperjs/1.6.1/cropper.min.js"></script>
            <style>
              body{{margin:0;background:#0a0a0f;}}
              #crop-wrap{{display:flex;flex-direction:column;align-items:center;gap:10px;padding:10px;box-sizing:border-box;}}
              #crop-container{{width:280px;height:280px;overflow:hidden;border-radius:12px;background:#111;}}
              #crop-container img{{max-width:100%;}}
              .rot-row{{display:flex;gap:8px;width:280px;}}
              .rot-btn{{flex:1;background:#374151;color:#fff;border:none;border-radius:8px;padding:8px 0;font-size:13px;font-weight:700;cursor:pointer;}}
              .rot-btn:hover{{background:#4b5563;}}
              .mid-row{{display:flex;align-items:center;gap:12px;width:280px;}}
              #preview-circle{{width:96px;height:96px;border-radius:50%;overflow:hidden;border:3px solid rgba(139,92,246,0.6);flex-shrink:0;}}
              #auto-status{{flex:1;font-size:11px;font-weight:600;color:rgba(240,240,245,0.5);text-align:center;}}
              #auto-status.saving{{color:#fbbf24;}}
              #auto-status.saved{{color:#6ee7b7;}}
              #auto-status.err{{color:#f87171;}}
              .hint{{color:rgba(240,240,245,0.4);font-size:10px;text-align:center;}}
            </style>
            <div id="crop-wrap">
              <div class="hint">✋ ドラッグ移動 / スクロール拡大縮小 / 回転ボタンで回転</div>
              <div id="crop-container"><img id="crop-img" src="data:{_mime};base64,{_raw_b64}"/></div>
              <div class="rot-row">
                <button class="rot-btn" onclick="cropper.rotate(-90)">↺ 左回転</button>
                <button class="rot-btn" onclick="cropper.rotate(90)">↻ 右回転</button>
              </div>
              <div class="mid-row">
                <div id="preview-circle"></div>
                <div id="auto-status">← 位置を調整してください</div>
              </div>
            </div>
            <script>
              const img = document.getElementById('crop-img');
              const cropper = new Cropper(img, {{
                aspectRatio: 1,
                viewMode: 1,
                dragMode: 'move',
                autoCropArea: 0.8,
                cropBoxResizable: false,
                cropBoxMovable: false,
                preview: '#preview-circle',
              }});

              let saveTimer = null;
              let lastSaveOk = false;

              img.addEventListener('cropend', scheduleSave);
              img.addEventListener('zoom',    scheduleSave);

              function scheduleSave() {{
                clearTimeout(saveTimer);
                const el = document.getElementById('auto-status');
                el.className = 'saving';
                el.textContent = '🔄 調整中...';
                lastSaveOk = false;
                saveTimer = setTimeout(autoSave, 1200);
              }}

              async function autoSave() {{
                const el = document.getElementById('auto-status');
                el.className = 'saving';
                el.textContent = '⏳ 保存中...';
                try {{
                  const canvas = cropper.getCroppedCanvas({{width:200, height:200}});
                  const blob   = await new Promise(resolve => canvas.toBlob(resolve, 'image/jpeg', 0.85));

                  const uploadRes = await fetch(
                    '{_supa_url}/storage/v1/object/creator-photos/{_storage_path}',
                    {{
                      method: 'POST',
                      headers: {{
                        'Authorization': 'Bearer {_supa_key}',
                        'apikey':        '{_supa_key}',
                        'Content-Type':  'image/jpeg',
                        'x-upsert':      'true',
                      }},
                      body: blob,
                    }}
                  );
                  if (!uploadRes.ok) {{
                    const t = await uploadRes.text();
                    throw new Error(t);
                  }}

                  const photoUrl = '{_supa_url}/storage/v1/object/public/creator-photos/{_storage_path}';
                  const dbRes = await fetch(
                    '{_supa_url}/rest/v1/creators?acct_id=eq.{acct_id}',
                    {{
                      method: 'PATCH',
                      headers: {{
                        'Authorization': 'Bearer {_supa_key}',
                        'apikey':        '{_supa_key}',
                        'Content-Type':  'application/json',
                        'Prefer':        'return=minimal',
                      }},
                      body: JSON.stringify({{photo_url: photoUrl}}),
                    }}
                  );
                  if (!dbRes.ok) {{
                    const t = await dbRes.text();
                    throw new Error(t);
                  }}

                  el.className = 'saved';
                  el.textContent = '✅ 保存OK！下のボタンで確定';
                  lastSaveOk = true;
                }} catch(e) {{
                  el.className = 'err';
                  el.textContent = '❌ ' + e.message;
                  lastSaveOk = false;
                }}
              }}
            </script>
            """
            st.components.v1.html(_cropper_html, height=490, scrolling=False)

        # ── アイコン確定ボタン（uploaded_photo の外に配置・常に表示）──
        if st.button("✅ アイコンを確定する", key=f"confirm_icon_{acct_id}", use_container_width=True):
            st.session_state[f"icon_confirmed_{acct_id}"] = True
            st.rerun()
        if st.session_state.get(f"icon_confirmed_{acct_id}"):
            st.success("✅ アイコンを確定しました！続けて「プロフィールを保存」を押してください。")

        name = st.text_input("表示名", value=_def_name)
        icon = st.selectbox("アイコン", _icon_list, index=_def_icon_idx, key=f"icon_{acct_id}")

        bio = st.text_area("自己紹介（bio）", value=_cr_data.get("bio") or "", max_chars=500, key=f"bio_{acct_id}",
                           help="最大500文字。電話番号・メール・LINE IDは入力不可")
        st.caption(f"{len(_cr_data.get('bio') or '')}/500文字")

        # ── SNSリンク（折りたたみ）──
        _sns_raw = _cr_data.get("sns_links") or {}
        if isinstance(_sns_raw, str):
            try:
                _sns_raw = json.loads(_sns_raw)
            except Exception:
                _sns_raw = {}
        with st.expander("🔗 SNSリンクを設定する（任意）"):
            _sns_x    = st.text_input("X（旧Twitter）",       value=_sns_raw.get("x", ""),         placeholder="https://x.com/username",           key=f"sns_x_{acct_id}")
            _sns_ig   = st.text_input("Instagram",             value=_sns_raw.get("instagram", ""), placeholder="https://instagram.com/username",    key=f"sns_ig_{acct_id}")
            _sns_yt   = st.text_input("YouTube",               value=_sns_raw.get("youtube", ""),   placeholder="https://youtube.com/@username",     key=f"sns_yt_{acct_id}",
                                     help="💡 URLの形式: @ハンドル名・channel/UCxxx・c/名前 のいずれか可\n日本語チャンネル名の場合はブラウザのURL欄からそのままコピー&ペーストしてください")
            _sns_tt   = st.text_input("TikTok",                value=_sns_raw.get("tiktok", ""),    placeholder="https://tiktok.com/@username",      key=f"sns_tt_{acct_id}")
            _sns_note = st.text_input("note",                  value=_sns_raw.get("note", ""),      placeholder="https://note.com/username",         key=f"sns_note_{acct_id}")
            _sns_fb   = st.text_input("Facebook",              value=_sns_raw.get("facebook", ""),  placeholder="https://facebook.com/username",     key=f"sns_fb_{acct_id}")
            _sns_line = st.text_input("LINE（公式アカウント）", value=_sns_raw.get("line", ""),      placeholder="https://line.me/R/ti/p/@username",  key=f"sns_line_{acct_id}")

        slug = st.text_input("ユーザーID（プロフィールURL用）", value=_cr_data.get("slug") or "", key=f"slug_{acct_id}",
                             help="例: asagiri → oshipay.me/u/asagiri（3〜20文字・英数字・ハイフンのみ）\n※ログイン時のIDとして使用・QRコードに表示されるURLの末尾になります")

        # creator_acct_id で紐づきサポーターを検索
        _cr_save_sup_id = None
        try:
            _crs1 = get_db().table("supporters").select("supporter_id").eq("creator_acct_id", acct_id).limit(1).execute()
            if _crs1.data:
                _cr_save_sup_id = _crs1.data[0]["supporter_id"]
        except Exception:
            pass
        cr_name_sync = st.checkbox("サポーター名も同じにする", key=f"cr_name_sync_{acct_id}") if _cr_save_sup_id else False

        if st.button("💾 プロフィールを保存", type="primary", key=f"save_profile_{acct_id}"):
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
            # SNSリンク バリデーション
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
                    "profile_done": True,
                }).eq("acct_id", acct_id).execute()
                if cr_name_sync and _cr_save_sup_id and name:
                    get_db().table("supporters").update({"display_name": name}).eq("supporter_id", _cr_save_sup_id).execute()
                st.success("プロフィールを保存しました！")
                st.session_state[f"profile_saved_{acct_id}"] = True
                _saved_slug = slug.lower() if slug else acct_id
                _ms_preview_url = f"https://oyajibuki.github.io/OshiPay/creator.html?id={_saved_slug}"
                st.link_button("🌐 プロフィールを確認する", _ms_preview_url, use_container_width=True)

        # ── QRコード発行ボタン（保存後のみ表示）──
        _profile_ready = st.session_state.get(f"profile_saved_{acct_id}") or _cr_data.get("profile_done")
        if _profile_ready:
            if st.button("✨ QRコードを発行する", type="primary", use_container_width=True, key="qr_gen_btn"):
                _final_id = slug.lower() if slug else acct_id
                support_url = f"{QR_BASE}/u/{_final_id}"
                st.session_state.qr_url = support_url
                st.session_state.qr_just_generated = True
                st.session_state[f"creator_name_{acct_id}"] = name
                st.session_state[f"creator_icon_{acct_id}"] = icon
        else:
            st.info("💾 プロフィールを保存すると、QRコードを発行できます。")

        # 返信ダッシュボードへのリンク（同一セッション内遷移でパスワード省略）
        if st.button("💌 応援メッセージ・返信ダッシュボードを開く", use_container_width=True, key="reply_dash_btn"):
            st.session_state["creator_auth"] = acct_id
            st.session_state["reply_auth"]   = acct_id
            st.query_params["page"] = "reply_view"
            st.query_params["acct"] = acct_id
            st.rerun()

        # ── カレンダーにイベントを登録する ──
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:20px 0;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:rgba(240,240,245,0.85);margin-bottom:8px;">📅 推しカレンダーに予定を登録する</div>', unsafe_allow_html=True)
        with st.expander("➕ イベントを登録する"):
            _dash_ev_name = _cr_data.get("display_name") or _cr_data.get("name") or acct_id
            _dash_ev_photo = _cr_data.get("photo_url") or ""
            _dash_cat  = st.selectbox("カテゴリ *", ["ゲーム・同人", "配信・実況", "コンカフェ", "ライブ・路上"], key="dash_cal_cat")
            _dash_type = st.selectbox("イベント種別 *", ["リリース", "配信", "初配信", "出勤", "ライブ", "ストリート", "その他"], key="dash_cal_type")
            _dash_date = st.date_input("リリース日/配信日/出勤日/開催日 *", min_value=datetime.date.today(), key="dash_cal_date")
            _dash_use_time = st.checkbox("時刻を指定する", value=True, key="dash_cal_use_time")
            _dash_time = _dash_time_end = None
            if _dash_use_time:
                _dt_c1, _dt_c2 = st.columns(2)
                _dash_time     = _dt_c1.time_input("開始時刻", value=datetime.time(18, 0), key="dash_cal_time")
                _dash_time_end = _dt_c2.time_input("終了時刻（任意）", value=datetime.time(18, 0), key="dash_cal_time_end")
            _dash_loc  = st.text_input("場所/プラットフォーム/ゲーム名", placeholder="例：渋谷○○ / YouTube Live", key="dash_cal_loc")
            _dash_url  = st.text_input("関連URL（任意）", placeholder="例：https://youtube.com/live/xxxx", key="dash_cal_url")
            _dash_desc = st.text_area("告知メッセージ（任意）", placeholder="例：初配信です！ぜひ見に来てね！", max_chars=200, key="dash_cal_desc")
            if st.button("📅 カレンダーに登録する", use_container_width=True, key="dash_cal_submit"):
                _jst_tz_d = datetime.timezone(datetime.timedelta(hours=9))
                if _dash_use_time and _dash_time:
                    _dash_ev_dt = datetime.datetime(
                        _dash_date.year, _dash_date.month, _dash_date.day,
                        _dash_time.hour, _dash_time.minute, tzinfo=_jst_tz_d,
                    )
                    _dash_ev_dt_end = None
                    if _dash_time_end and _dash_time_end != _dash_time:
                        _dash_ev_dt_end = datetime.datetime(
                            _dash_date.year, _dash_date.month, _dash_date.day,
                            _dash_time_end.hour, _dash_time_end.minute, tzinfo=_jst_tz_d,
                        )
                else:
                    _dash_ev_dt     = datetime.datetime(_dash_date.year, _dash_date.month, _dash_date.day, 0, 0, tzinfo=_jst_tz_d)
                    _dash_ev_dt_end = None
                _dash_desc_combined = _dash_desc.strip()
                if _dash_url.strip():
                    _dash_desc_combined = (_dash_desc_combined + "\n" + _dash_url.strip()).strip()
                _dash_ins = {
                    "creator_acct":      acct_id,
                    "temp_display_name": _dash_ev_name,
                    "temp_photo_url":    _dash_ev_photo or None,
                    "status":            "verified",
                    "category":          _dash_cat,
                    "event_type":        _dash_type,
                    "event_date":        _dash_ev_dt.isoformat(),
                    "location":          _dash_loc.strip() or None,
                    "description":       _dash_desc_combined or None,
                }
                if _dash_ev_dt_end:
                    _dash_ins["event_date_end"] = _dash_ev_dt_end.isoformat()
                try:
                    _dash_ins_res = get_db().table("calendar_events").insert(_dash_ins).execute()
                    if _dash_ins_res.data:
                        st.success("🎉 カレンダーに登録しました！")
                        st.link_button("📅 カレンダーを確認する", "?page=calendar", use_container_width=True)
                    else:
                        st.error("登録に失敗しました。もう一度お試しください。")
                except Exception as _e_dash_ins:
                    st.error(f"エラーが発生しました: {_e_dash_ins}")

        # OAuth判定
        _cr_is_oauth = bool(_cr_data.get("google_sub") or _cr_data.get("discord_sub") or _cr_data.get("line_sub"))

        # パスワード変更
        if _cr_is_oauth:
            st.caption("💡 LINE / Google / Discord でログイン中のため、メールアドレス・パスワードの変更はできません。")
        if not _cr_is_oauth:
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
                            # 紐づきサポーターに強制同期
                            try:
                                _cc_lsup = get_db().table("supporters").select("supporter_id").eq("creator_acct_id", acct_id).limit(1).execute()
                                _cc_lsup_id = (_cc_lsup.data or [{}])[0].get("supporter_id") if _cc_lsup.data else None
                                if _cc_lsup_id:
                                    get_db().table("supporters").update({"password_hash": hash_password(cc_new)}).eq("supporter_id", _cc_lsup_id).execute()
                                    get_db().table("supporter_accounts").update({"password_hash": hash_password(cc_new)}).eq("supporter_id", _cc_lsup_id).execute()
                            except Exception:
                                pass
                            st.success("パスワードを更新しました！")
                        else:
                            st.error("現在のパスワードが違います。")
                else:
                    st.warning("全ての項目を入力してください。")

        # メールアドレス変更
        if not _cr_is_oauth:
         with st.expander("📧 メールアドレスを変更する"):
            _cur_email = _cr_data.get("email") or ""
            if _cur_email:
                _masked = _cur_email[:2] + "****" + _cur_email[_cur_email.find("@"):]
                st.caption(f"現在: {_masked}")
            em_new   = st.text_input("新しいメールアドレス", placeholder="new@example.com", key="em_new")
            em_pass  = st.text_input("現在のパスワード（確認用）", type="password", key="em_pass")
            if st.button("メールアドレスを更新", key="em_btn"):
                if not em_new or not em_pass:
                    st.warning("全ての項目を入力してください。")
                elif "@" not in em_new or "." not in em_new.split("@")[-1]:
                    st.error("メールアドレスの形式が正しくありません。")
                else:
                    _em_chk = get_db().table("creators").select("password_hash").eq("acct_id", acct_id).execute()
                    if _em_chk.data and _em_chk.data[0]["password_hash"] == hash_password(em_pass):
                        _em_lc = em_new.strip().lower()
                        _em_dup = get_db().table("creators").select("acct_id").eq("email", _em_lc).neq("acct_id", acct_id).execute()
                        if len(_em_dup.data or []) >= 10:
                            st.error("このメールアドレスはすでに10アカウントに使用されています。別のメールアドレスをお使いください。")
                        else:
                            get_db().table("creators").update({"email": _em_lc}).eq("acct_id", acct_id).execute()
                            # 紐づきサポーターに強制同期
                            try:
                                _em_lsup = get_db().table("supporters").select("supporter_id").eq("creator_acct_id", acct_id).limit(1).execute()
                                _em_lsup_id = (_em_lsup.data or [{}])[0].get("supporter_id") if _em_lsup.data else None
                                if _em_lsup_id:
                                    get_db().table("supporters").update({"email": _em_lc}).eq("supporter_id", _em_lsup_id).execute()
                                    get_db().table("supporter_accounts").update({"email": _em_lc}).eq("supporter_id", _em_lsup_id).execute()
                            except Exception:
                                pass
                            st.success("✅ メールアドレスを更新しました！")
                            st.rerun()
                    else:
                        st.error("パスワードが違います。")

        # ── サポーターとして活動する ──
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:20px 0;">', unsafe_allow_html=True)
        st.markdown('<div style="font-size:15px;font-weight:700;color:rgba(240,240,245,0.85);margin-bottom:8px;">💜 サポーターとして応援する</div>', unsafe_allow_html=True)
        try:
            _cr_full = get_db().table("creators").select("google_sub,discord_sub,line_sub,email").eq("acct_id", acct_id).maybe_single().execute()
            _cr_gsub  = (_cr_full.data or {}).get("google_sub")  or ""
            _cr_dsub  = (_cr_full.data or {}).get("discord_sub") or ""
            _cr_lsub  = (_cr_full.data or {}).get("line_sub")    or ""
            _cr_email = (_cr_full.data or {}).get("email")        or ""
        except Exception:
            _cr_gsub = _cr_dsub = _cr_lsub = _cr_email = ""

        # 既存サポーターアカウントを検索（creator_acct_id で紐づけ済み / sub一致 / email 一致）
        _linked_sup_id = None
        try:
            _ls1 = get_db().table("supporters").select("supporter_id").eq("creator_acct_id", acct_id).limit(1).execute()
            if _ls1.data:
                _linked_sup_id = _ls1.data[0]["supporter_id"]
            else:
                # google_sub / discord_sub / line_sub の順に検索
                for _sub_col, _sub_val in [("google_sub", _cr_gsub), ("discord_sub", _cr_dsub), ("line_sub", _cr_lsub)]:
                    if _sub_val and not _linked_sup_id:
                        _ls2 = get_db().table("supporters").select("supporter_id").eq(_sub_col, _sub_val).limit(1).execute()
                        if _ls2.data:
                            _linked_sup_id = _ls2.data[0]["supporter_id"]
                            get_db().table("supporters").update({"creator_acct_id": acct_id}).eq("supporter_id", _linked_sup_id).execute()
        except Exception:
            pass

        if _linked_sup_id:
            st.success(f"✅ サポーターID `{_linked_sup_id}` と連携済みです")
            if st.button("💜 サポーターダッシュボードへ切り替え", use_container_width=True, key="switch_to_supporter"):
                _sup_row2 = get_db().table("supporters").select("supporter_id,display_name,email").eq("supporter_id", _linked_sup_id).maybe_single().execute()
                _sd = _sup_row2.data or {}
                st.session_state["supporter_auth"] = {
                    "supporter_id": _sd.get("supporter_id", _linked_sup_id),
                    "display_name": _sd.get("display_name", ""),
                    "email": _sd.get("email", ""),
                }
                st.query_params["page"] = "supporter_dashboard"
                st.rerun()
        else:
            st.markdown('<div style="font-size:13px;color:rgba(240,240,245,0.6);margin-bottom:10px;">クリエーターとして活動しながら、他のクリエーターを応援することもできます。</div>', unsafe_allow_html=True)
            if st.button("💜 サポーターになる（無料）", use_container_width=True, key="become_supporter"):
                try:
                    _new_sup_id = None
                    # google_sub / discord_sub / line_sub で既存サポーターを検索
                    for _sub_col, _sub_val in [("google_sub", _cr_gsub), ("discord_sub", _cr_dsub), ("line_sub", _cr_lsub)]:
                        if _sub_val and not _new_sup_id:
                            _bs1 = get_db().table("supporters").select("supporter_id,display_name,email").eq(_sub_col, _sub_val).limit(1).execute()
                            if _bs1.data:
                                _new_sup_id = _bs1.data[0]["supporter_id"]
                    # email で既存サポーターを検索（1件のみ自動紐づけ）
                    if not _new_sup_id and _cr_email:
                        _bs2 = get_db().table("supporters").select("supporter_id,display_name,email").eq("email", _cr_email).execute()
                        if len(_bs2.data or []) == 1:
                            _new_sup_id = _bs2.data[0]["supporter_id"]
                        elif len(_bs2.data or []) > 1:
                            st.session_state["_cr_to_sup_candidates"] = [
                                {"supporter_id": r["supporter_id"], "display_name": r.get("display_name") or r["supporter_id"]}
                                for r in _bs2.data
                            ]
                            st.session_state["_cr_to_sup_acct"] = acct_id
                            st.rerun()
                    # 新規作成
                    if not _new_sup_id:
                        _new_sup_id = "sup_" + uuid.uuid4().hex[:12]
                        _sup_ins = {
                            "supporter_id": _new_sup_id,
                            "display_name": _cr_data.get("display_name") or "サポーター",
                            "email": _cr_email,
                        }
                        if _cr_gsub: _sup_ins["google_sub"]  = _cr_gsub
                        if _cr_dsub: _sup_ins["discord_sub"] = _cr_dsub
                        if _cr_lsub: _sup_ins["line_sub"]    = _cr_lsub
                        get_db().table("supporters").insert(_sup_ins).execute()
                        if _cr_email:
                            _sa_ins = {"supporter_id": _new_sup_id, "email": _cr_email}
                            if _cr_gsub: _sa_ins["google_sub"]  = _cr_gsub
                            if _cr_dsub: _sa_ins["discord_sub"] = _cr_dsub
                            if _cr_lsub: _sa_ins["line_sub"]    = _cr_lsub
                            get_db().table("supporter_accounts").insert(_sa_ins).execute()
                    # creator_acct_id を紐づけ
                    get_db().table("supporters").update({"creator_acct_id": acct_id}).eq("supporter_id", _new_sup_id).execute()
                    _sup_row3 = get_db().table("supporters").select("supporter_id,display_name,email").eq("supporter_id", _new_sup_id).maybe_single().execute()
                    _sd3 = _sup_row3.data or {}
                    st.session_state["supporter_auth"] = {
                        "supporter_id": _sd3.get("supporter_id", _new_sup_id),
                        "display_name": _sd3.get("display_name", ""),
                        "email": _sd3.get("email", ""),
                    }
                    st.query_params["page"] = "supporter_dashboard"
                    st.rerun()
                except Exception as _se:
                    st.error(f"サポーター作成エラー: {_se}")

        # サポーター候補が複数の場合の選択UI
        if st.session_state.get("_cr_to_sup_candidates"):
            _cands = st.session_state["_cr_to_sup_candidates"]
            st.markdown('<div style="font-size:13px;color:#93c5fd;margin-bottom:8px;">既存のサポーターアカウントが複数あります。どれを使いますか？</div>', unsafe_allow_html=True)
            for _sc in _cands:
                if st.button(f"✅ {_sc['display_name']} ({_sc['supporter_id']})", key=f"sel_sup_{_sc['supporter_id']}", use_container_width=True):
                    _sel_id = _sc["supporter_id"]
                    get_db().table("supporters").update({"creator_acct_id": acct_id}).eq("supporter_id", _sel_id).execute()
                    _sup_row4 = get_db().table("supporters").select("supporter_id,display_name,email").eq("supporter_id", _sel_id).maybe_single().execute()
                    _sd4 = _sup_row4.data or {}
                    st.session_state["supporter_auth"] = {
                        "supporter_id": _sd4.get("supporter_id", _sel_id),
                        "display_name": _sd4.get("display_name", ""),
                        "email": _sd4.get("email", ""),
                    }
                    del st.session_state["_cr_to_sup_candidates"]
                    st.query_params["page"] = "supporter_dashboard"
                    st.rerun()

        # 連携解除ボタン
        if st.button("🚫 連携解除", type="secondary", key="disconnect_btn"):
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
            reply_dash_url = f"{BASE_URL}?page=dashboard&acct={acct_id}"
            info_txt = f"クリエイターID: {acct_id}\n応援URL: {st.session_state.qr_url}\nダッシュボード: {reply_dash_url}"
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
            # ── メール送信 ──
            st.markdown('<div style="margin-top:14px;font-size:0.82rem;color:rgba(255,255,255,0.6);">📧 QRと情報をメールで送信</div>', unsafe_allow_html=True)
            _qr_ecol1, _qr_ecol2 = st.columns([3, 1])
            _qr_email_to = _qr_ecol1.text_input("qr_email_label", placeholder="送信先メールアドレス", key="qr_send_email", label_visibility="collapsed")
            if _qr_ecol2.button("送信", use_container_width=True, key="qr_email_send_btn"):
                if _qr_email_to:
                    _qr_ok, _qr_err = send_qr_email(_qr_email_to, acct_id, st.session_state.qr_url, qr_bytes)
                    if _qr_ok:
                        st.success("✅ QRコードをメールで送信しました！")
                    else:
                        st.error(f"送信失敗: {_qr_err}")
                else:
                    st.warning("メールアドレスを入力してください。")
    # ── クリエーターログアウト ──
    if acct_id and st.session_state.get("creator_auth") == acct_id:
        st.markdown('<hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:24px 0 12px;">', unsafe_allow_html=True)
        if st.button("🚪 ログアウト", type="secondary", use_container_width=True, key="creator_logout_btn"):
            st.session_state.pop("creator_auth", None)
            st.query_params.clear()
            st.query_params["page"] = "dashboard"
            st.rerun()
    st.markdown(f'<div class="oshi-footer">Powered by <a href="https://oshipay.me/index.html">oshipay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="https://oshipay.me/terms" target="_blank">利用規約</a><a href="https://oshipay.me/privacy" target="_blank">プライバシーポリシー</a><a href="https://oshipay.me/tokusho" target="_blank">特定商取引法</a></div>', unsafe_allow_html=True)

# ================================================================
# 📅 推しカレンダー機能
# ================================================================

_CAL_CATEGORIES  = ["ゲーム・同人", "配信・実況", "コンカフェ", "ライブ・路上"]
_CAL_EVENT_TYPES = ["リリース", "配信", "初配信", "出勤", "ライブ", "ストリート", "その他"]
_CAL_AGENT_CODE  = "oshipay2025"
_CAL_WEEKDAY_JP  = ["月", "火", "水", "木", "金", "土", "日"]
_CAL_CAT_COLORS  = {
    "ゲーム・同人": "#8b5cf6",
    "配信・実況":   "#3b82f6",
    "コンカフェ":   "#ec4899",
    "ライブ・路上": "#f97316",
}
_CAL_TYPE_COLORS = {
    "リリース":   ("rgba(139,92,246,0.25)",  "#c4b5fd"),
    "配信":       ("rgba(59,130,246,0.25)",  "#93c5fd"),
    "初配信":     ("rgba(34,197,94,0.25)",   "#86efac"),
    "出勤":       ("rgba(236,72,153,0.25)",  "#f9a8d4"),
    "ライブ":     ("rgba(249,115,22,0.25)",  "#fdba74"),
    "ストリート": ("rgba(249,115,22,0.25)",  "#fdba74"),
    "その他":     ("rgba(255,255,255,0.1)",  "rgba(240,240,245,0.7)"),
}
_CAL_CAT_EMOJI = {
    "ゲーム・同人": "🎮",
    "配信・実況":   "📺",
    "コンカフェ":   "☕",
    "ライブ・路上": "🎸",
}


def _cal_get_events(month_filter="all", cat_filter="all"):
    _jst = datetime.timezone(datetime.timedelta(hours=9))
    _now = datetime.datetime.now(_jst)
    q = get_db().table("calendar_events").select("*").eq("is_deleted", False)
    if month_filter and month_filter != "all":
        try:
            m = int(month_filter)
            y = _now.year
            if m < _now.month:
                y += 1
            s = datetime.datetime(y, m, 1, tzinfo=_jst)
            e = datetime.datetime(y + (1 if m == 12 else 0), 1 if m == 12 else m + 1, 1, tzinfo=_jst)
            q = q.gte("event_date", s.isoformat()).lt("event_date", e.isoformat())
        except Exception:
            pass
    if cat_filter and cat_filter != "all":
        q = q.eq("category", cat_filter)
    return q.order("event_date").execute().data or []


def _cal_get_creators_map(acct_ids):
    if not acct_ids:
        return {}
    res = get_db().table("creators").select(
        "acct_id,display_name,photo_url,slug,payout_enabled"
    ).in_("acct_id", list(set(acct_ids))).execute()
    return {r["acct_id"]: r for r in (res.data or [])}


def _cal_format_date(ev_date_str, ev_date_end_str=None):
    _jst = datetime.timezone(datetime.timedelta(hours=9))
    _now = datetime.datetime.now(_jst)
    try:
        dt     = datetime.datetime.fromisoformat(ev_date_str.replace("Z", "+00:00"))
        dt_jst = dt.astimezone(_jst)
        wd     = _CAL_WEEKDAY_JP[dt_jst.weekday()]
        d_part = "本日" if dt_jst.date() == _now.date() else f"{dt_jst.month}/{dt_jst.day}({wd})"
        t_part = dt_jst.strftime("%H:%M")
        if ev_date_end_str:
            try:
                dt_e     = datetime.datetime.fromisoformat(ev_date_end_str.replace("Z", "+00:00"))
                dt_e_jst = dt_e.astimezone(_jst)
                return f"{d_part}\u3000{t_part} - {dt_e_jst.strftime('%H:%M')}"
            except Exception:
                pass
        return f"{d_part}\u3000{t_part}\u301c"
    except Exception:
        return str(ev_date_str)[:10] if ev_date_str else ""


def _cal_create_claim_token(event_id: str):
    try:
        res = get_db().table("claim_tokens").insert({"event_id": event_id}).execute()
        return res.data[0]["token"] if res.data else None
    except Exception:
        return None


# ── カレンダー投稿モーダル（@st.dialog） ────────────────────────────
@st.dialog("カレンダーに予定を追加")
def _cal_post_modal():
    st.markdown(
        '<div style="font-size:12px;color:rgba(240,240,245,0.4);text-align:center;margin-bottom:20px;">'
        '投稿方法を選んでください</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);'
        'border-radius:14px;padding:20px;margin-bottom:16px;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="font-size:18px;">🛡️</span>'
        '<span style="font-size:15px;font-weight:800;color:#f0f0f5;">クリエイターご本人ですか？</span>'
        '</div>'
        '<div style="font-size:12px;color:rgba(240,240,245,0.5);margin-bottom:16px;line-height:1.6;">'
        'アカウントを作成し、口座（Stripe）を連携すると、カレンダーに自分の予定を登録して直接投げ銭を受け取れるようになります。'
        '</div>'
        '<div style="display:flex;gap:10px;">'
        '<a href="?page=dashboard&tab=new" style="flex:1;text-align:center;padding:11px;border-radius:10px;'
        'background:linear-gradient(135deg,#8b5cf6,#ec4899);color:white;font-size:13px;font-weight:700;text-decoration:none;">'
        '1分でアカウント作成</a>'
        '<a href="?page=dashboard" style="flex:1;text-align:center;padding:11px;border-radius:10px;'
        'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);'
        'color:#f0f0f5;font-size:13px;font-weight:700;text-decoration:none;">ログイン</a>'
        '</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="display:flex;align-items:center;gap:10px;margin:16px 0;">'
        '<div style="flex:1;height:1px;background:rgba(255,255,255,0.08);"></div>'
        '<span style="font-size:12px;color:rgba(240,240,245,0.35);">または</span>'
        '<div style="flex:1;height:1px;background:rgba(255,255,255,0.08);"></div>'
        '</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="background:rgba(249,115,22,0.05);border:1px solid rgba(249,115,22,0.2);'
        'border-radius:14px;padding:20px;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="font-size:16px;">ℹ️</span>'
        '<span style="font-size:14px;font-weight:800;color:rgba(240,240,245,0.85);">'
        '【運営・代理店専用】代理で仮登録する</span></div>'
        '<div style="font-size:12px;color:rgba(240,240,245,0.45);margin-bottom:16px;line-height:1.6;">'
        'クリエイターに代わってイベント情報を「仮掲載」します。ファンからの応援リクエストを集め、営業時のアプローチに活用できます。'
        '</div>'
        '<a href="?page=calendar_agent" style="display:block;text-align:center;padding:11px;border-radius:10px;'
        'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);'
        'color:#f0f0f5;font-size:13px;font-weight:700;text-decoration:none;">'
        '代理登録フォームを開く</a></div>',
        unsafe_allow_html=True,
    )


# ── カレンダー一覧ページ ──────────────────────────────────────────
if page == "calendar":
    _jst_tz  = datetime.timezone(datetime.timedelta(hours=9))
    _now_jst = datetime.datetime.now(_jst_tz)
    cal_month = params.get("cal_month", "all")
    cal_cat   = params.get("cal_cat",   "all")

    _req_ev_id = params.get("request", "")
    if _req_ev_id:
        try:
            _r = get_db().table("calendar_events").select("request_count").eq("id", _req_ev_id).execute()
            if _r.data:
                _new_cnt = (_r.data[0].get("request_count") or 0) + 1
                get_db().table("calendar_events").update({"request_count": _new_cnt}).eq("id", _req_ev_id).execute()
        except Exception:
            pass
        st.query_params.update({"page": "calendar", "cal_month": cal_month, "cal_cat": cal_cat})
        st.rerun()

    st.markdown(
        '<div style="padding:16px 4px 12px;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">'
        '<span style="font-size:22px;font-weight:900;color:#f0f0f5;">推しカレンダー</span>'
        '<span style="font-size:20px;">📅</span>'
        '</div>'
        '<div style="font-size:13px;color:rgba(240,240,245,0.45);">ゲームのリリース、配信、出勤、ライブ情報！</div>'
        '</div>',
        unsafe_allow_html=True,
    )

    _m_opts = [("all", "すべて")]
    for _i in range(3):
        _m = (_now_jst.month - 1 + _i) % 12 + 1
        _m_opts.append((str(_m), f"{_m}月"))
    _m_html = '<div style="display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;">'
    for _mv, _ml in _m_opts:
        _act = cal_month == _mv
        _m_html += (
            f'<a href="?page=calendar&cal_month={_mv}&cal_cat={cal_cat}" '
            f'style="text-decoration:none;padding:6px 18px;border-radius:20px;font-size:13px;'
            f'font-weight:{"800" if _act else "600"};'
            f'background:{"rgba(139,92,246,0.2)" if _act else "rgba(255,255,255,0.05)"};'
            f'border:{"1px solid rgba(139,92,246,0.6)" if _act else "1px solid rgba(255,255,255,0.1)"};'
            f'color:{"#c4b5fd" if _act else "rgba(240,240,245,0.6)"};">{_ml}</a>'
        )
    _m_html += '</div>'
    st.markdown(_m_html, unsafe_allow_html=True)

    _c_opts = [
        ("all",        "🔥 すべて"),
        ("ゲーム・同人", "🎮 ゲーム・同人"),
        ("配信・実況",   "📺 配信・実況"),
        ("コンカフェ",   "☕ コンカフェ"),
        ("ライブ・路上", "🎸 ライブ・路上"),
    ]
    _c_html = '<div style="display:flex;gap:6px;margin-bottom:20px;flex-wrap:wrap;">'
    for _cv, _cl in _c_opts:
        _act = cal_cat == _cv
        _c_html += (
            f'<a href="?page=calendar&cal_month={cal_month}&cal_cat={_cv}" '
            f'style="text-decoration:none;padding:7px 14px;border-radius:20px;font-size:13px;'
            f'font-weight:{"700" if _act else "500"};'
            f'background:{"rgba(255,255,255,0.1)" if _act else "transparent"};'
            f'border:{"1px solid rgba(255,255,255,0.3)" if _act else "1px solid rgba(255,255,255,0.1)"};'
            f'color:{"#f0f0f5" if _act else "rgba(240,240,245,0.5)"};">{_cl}</a>'
        )
    _c_html += '</div>'
    st.markdown(_c_html, unsafe_allow_html=True)

    _events      = _cal_get_events(cal_month, cal_cat)
    _acct_ids    = [e["creator_acct"] for e in _events if e.get("creator_acct")]
    _creator_map = _cal_get_creators_map(_acct_ids)

    if not _events:
        st.markdown(
            '<div style="text-align:center;padding:60px 0;color:rgba(240,240,245,0.35);font-size:14px;">'
            '📭 この期間のイベントはまだありません</div>',
            unsafe_allow_html=True,
        )

    for _ev in _events:
        _cat      = _ev.get("category", "ライブ・路上")
        _bcol     = _CAL_CAT_COLORS.get(_cat, "#8b5cf6")
        _status   = _ev.get("status", "unverified")
        _ev_id    = _ev.get("id", "")
        _ev_type  = _ev.get("event_type", "その他")
        _type_bg, _type_col = _CAL_TYPE_COLORS.get(_ev_type, _CAL_TYPE_COLORS["その他"])
        _c_data   = _creator_map.get(_ev.get("creator_acct", ""), {})
        _verified = _status == "verified" and bool(_c_data)
        _dname    = (_c_data.get("display_name") or _ev.get("temp_display_name", "???")) if _verified else _ev.get("temp_display_name", "???")
        _photo    = (_c_data.get("photo_url") or _ev.get("temp_photo_url", ""))          if _verified else _ev.get("temp_photo_url", "")
        _slug     = _c_data.get("slug", "")
        _c_url    = f"?page=support&acct={_slug}" if (_verified and _slug) else "#"

        if _photo:
            _avatar = (
                f'<img src="{_photo}" style="width:48px;height:48px;border-radius:50%;'
                f'object-fit:cover;flex-shrink:0;border:2px solid rgba(255,255,255,0.1);">'
            )
        else:
            _emoji  = _CAL_CAT_EMOJI.get(_cat, "🎤")
            _avatar = (
                f'<div style="width:48px;height:48px;border-radius:50%;background:rgba(255,255,255,0.07);'
                f'border:2px solid rgba(255,255,255,0.1);display:flex;align-items:center;'
                f'justify-content:center;font-size:22px;flex-shrink:0;">{_emoji}</div>'
            )

        _vbadge = (
            '<span style="font-size:11px;color:#60a5fa;background:rgba(59,130,246,0.15);'
            'border:1px solid rgba(59,130,246,0.3);border-radius:20px;padding:1px 8px;">✓ 認証済み</span>'
            if _verified else
            '<span style="font-size:11px;color:rgba(240,240,245,0.4);background:rgba(255,255,255,0.05);'
            'border:1px solid rgba(255,255,255,0.1);border-radius:20px;padding:1px 8px;">仮登録</span>'
        )

        _date_str = _cal_format_date(_ev.get("event_date", ""), _ev.get("event_date_end"))
        _loc      = _ev.get("location", "")
        _loc_html = (
            f'<span style="display:inline-flex;align-items:center;gap:4px;font-size:12px;'
            f'color:rgba(240,240,245,0.55);background:rgba(255,255,255,0.05);'
            f'border:1px solid rgba(255,255,255,0.08);border-radius:6px;padding:3px 10px;'
            f'white-space:nowrap;">📍 {_loc}</span>'
        ) if _loc else ""

        _req_cnt = _ev.get("request_count", 0)
        if _verified:
            _abtn = (
                f'<a href="{_c_url}" style="display:inline-flex;align-items:center;gap:5px;'
                f'padding:8px 18px;border-radius:20px;'
                f'background:linear-gradient(135deg,#8b5cf6,#ec4899);color:white;'
                f'font-size:13px;font-weight:700;text-decoration:none;white-space:nowrap;">💖 応援・支援する</a>'
            )
        else:
            _req_label = "📡 OshiPay開始をリクエスト" + (f" ({_req_cnt})" if _req_cnt > 0 else "")
            _abtn = (
                f'<a href="?page=calendar&cal_month={cal_month}&cal_cat={cal_cat}&request={_ev_id}" '
                f'style="display:inline-flex;align-items:center;gap:5px;padding:8px 16px;'
                f'border-radius:20px;background:rgba(249,115,22,0.12);'
                f'border:1px solid rgba(249,115,22,0.4);color:#fb923c;'
                f'font-size:13px;font-weight:700;text-decoration:none;white-space:nowrap;">{_req_label}</a>'
            )

        _desc      = _ev.get("description", "")
        _desc_html = (
            f'<div style="font-size:13px;color:rgba(240,240,245,0.65);line-height:1.6;margin:6px 0 0;">{_desc}</div>'
        ) if _desc else ""

        st.markdown(
            f'<div style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.07);'
            f'border-left:3px solid {_bcol};border-radius:12px;padding:14px 16px;margin-bottom:10px;">'
            f'<div style="display:flex;gap:12px;align-items:flex-start;">'
            f'{_avatar}'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:5px;flex-wrap:wrap;">'
            f'<span style="font-size:11px;padding:2px 8px;border-radius:20px;background:{_type_bg};color:{_type_col};font-weight:700;">{_ev_type}</span>'
            f'<span style="font-size:12px;color:rgba(240,240,245,0.45);">📅 {_date_str}</span>'
            f'</div>'
            f'<div style="display:flex;align-items:center;gap:6px;margin-bottom:2px;flex-wrap:wrap;">'
            f'<a href="{_c_url}" style="font-size:15px;font-weight:900;color:#f0f0f5;text-decoration:none;">{_dname}</a>'
            f'{_vbadge}'
            f'</div>'
            f'{_desc_html}'
            f'<div style="display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-top:10px;">'
            f'{_loc_html}'
            f'{_abtn}'
            f'</div>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    # FABボタン（モーダルダイアログを開く）
    st.markdown(
        '<style>'
        'div[data-testid="stButton"].fab-cal > button {'
        '  position:fixed !important; bottom:24px !important; right:24px !important;'
        '  z-index:9999 !important;'
        '  background:linear-gradient(135deg,#8b5cf6,#ec4899) !important;'
        '  color:white !important; border-radius:28px !important;'
        '  padding:13px 20px !important; font-size:14px !important;'
        '  font-weight:700 !important; border:none !important; width:auto !important;'
        '  box-shadow:0 4px 20px rgba(139,92,246,0.4) !important;'
        '  cursor:pointer !important;'
        '}'
        '</style>',
        unsafe_allow_html=True,
    )
    st.markdown('<div class="fab-cal">', unsafe_allow_html=True)
    if st.button("➕ 予定を投稿する", key="fab_cal_post"):
        _cal_post_modal()
    st.markdown('</div>', unsafe_allow_html=True)
    st.stop()


# ── 投稿分岐モーダルページ ──────────────────────────────────────────
if page == "calendar_post":
    st.markdown(
        '<div style="max-width:480px;margin:40px auto 0;background:rgba(30,30,45,0.98);'
        'border:1px solid rgba(255,255,255,0.1);border-radius:20px;padding:32px 28px;'
        'box-shadow:0 20px 60px rgba(0,0,0,0.6);">'
        '<div style="font-size:18px;font-weight:900;color:#f0f0f5;margin-bottom:6px;text-align:center;">'
        'カレンダーに予定を追加</div>'
        '<div style="font-size:12px;color:rgba(240,240,245,0.4);text-align:center;margin-bottom:28px;">'
        '投稿方法を選んでください</div>'
        '<div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.1);'
        'border-radius:14px;padding:20px;margin-bottom:16px;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="font-size:18px;">🛡️</span>'
        '<span style="font-size:15px;font-weight:800;color:#f0f0f5;">クリエイターご本人ですか？</span>'
        '</div>'
        '<div style="font-size:12px;color:rgba(240,240,245,0.5);margin-bottom:16px;line-height:1.6;">'
        'アカウントを作成し、口座（Stripe）を連携すると、カレンダーに自分の予定を登録して直接投げ銭を受け取れるようになります。'
        '</div>'
        '<div style="display:flex;gap:10px;">'
        '<a href="?page=dashboard&tab=new" style="flex:1;text-align:center;padding:11px;border-radius:10px;'
        'background:linear-gradient(135deg,#8b5cf6,#ec4899);color:white;font-size:13px;font-weight:700;text-decoration:none;">'
        '1分でアカウント作成</a>'
        '<a href="?page=dashboard" style="flex:1;text-align:center;padding:11px;border-radius:10px;'
        'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);'
        'color:#f0f0f5;font-size:13px;font-weight:700;text-decoration:none;">ログイン</a>'
        '</div></div>'
        '<div style="display:flex;align-items:center;gap:10px;margin:16px 0;">'
        '<div style="flex:1;height:1px;background:rgba(255,255,255,0.08);"></div>'
        '<span style="font-size:12px;color:rgba(240,240,245,0.35);">または</span>'
        '<div style="flex:1;height:1px;background:rgba(255,255,255,0.08);"></div>'
        '</div>'
        '<div style="background:rgba(249,115,22,0.05);border:1px solid rgba(249,115,22,0.2);'
        'border-radius:14px;padding:20px;">'
        '<div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">'
        '<span style="font-size:16px;">ℹ️</span>'
        '<span style="font-size:14px;font-weight:800;color:rgba(240,240,245,0.85);">'
        '【運営・代理店専用】代理で仮登録する</span></div>'
        '<div style="font-size:12px;color:rgba(240,240,245,0.45);margin-bottom:16px;line-height:1.6;">'
        'クリエイターに代わってイベント情報を「仮掲載」します。ファンからの応援リクエストを集め、営業時のアプローチに活用できます。'
        '</div>'
        '<a href="?page=calendar_agent" style="display:block;text-align:center;padding:11px;border-radius:10px;'
        'background:rgba(255,255,255,0.07);border:1px solid rgba(255,255,255,0.15);'
        'color:#f0f0f5;font-size:13px;font-weight:700;text-decoration:none;">'
        '代理登録フォームを開く</a></div>'
        '<div style="text-align:center;margin-top:20px;">'
        '<a href="?page=calendar" style="font-size:12px;color:rgba(240,240,245,0.35);text-decoration:none;">'
        '← カレンダーに戻る</a></div></div>',
        unsafe_allow_html=True,
    )


# ── 代理登録フォームページ ──────────────────────────────────────────
if page == "calendar_agent":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">【代理店専用】イベント仮登録</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">クリエイターのイベントを代理で仮登録します</div>', unsafe_allow_html=True)

    if "agent_auth_ok"   not in st.session_state: st.session_state["agent_auth_ok"]   = False
    if "agent_submitted" not in st.session_state: st.session_state["agent_submitted"] = False
    if "agent_claim_url" not in st.session_state: st.session_state["agent_claim_url"] = ""

    if not st.session_state["agent_auth_ok"]:
        with st.form("agent_code_form"):
            _code_in = st.text_input("代理店コード", type="password", placeholder="コードを入力してください")
            if st.form_submit_button("認証する", use_container_width=True):
                if _code_in.strip() == _CAL_AGENT_CODE:
                    st.session_state["agent_auth_ok"] = True
                    st.rerun()
                else:
                    st.error("コードが正しくありません。")

    elif not st.session_state["agent_submitted"]:
        st.success("✅ 認証済み。イベント情報を入力してください。")

        # アイコン画像アップロード（フォーム外で先に処理）
        st.markdown("**クリエイター情報**")
        _f_name  = st.text_input("クリエイター名 *", placeholder="例：路上シンガーYUKI")
        _f_cat   = st.selectbox("カテゴリ *", _CAL_CATEGORIES)

        st.markdown("アイコン画像（任意）")
        _f_icon_file = st.file_uploader("JPG / PNG / WEBP", type=["jpg","jpeg","png","webp"], key="agent_icon_upload")
        _f_photo_url = ""
        if _f_icon_file is not None:
            try:
                _supa_url  = st.secrets["SUPABASE_URL"].rstrip("/")
                _supa_key  = st.secrets["SUPABASE_KEY"]
                import uuid as _uuid_mod
                _icon_path = f"agent_icons/{_uuid_mod.uuid4().hex}.{_f_icon_file.name.rsplit('.',1)[-1].lower()}"
                _icon_bytes = _f_icon_file.read()
                import urllib.request as _urlreq
                _upload_req = _urlreq.Request(
                    f"{_supa_url}/storage/v1/object/creator-photos/{_icon_path}",
                    data=_icon_bytes,
                    headers={
                        "apikey":        _supa_key,
                        "Authorization": f"Bearer {_supa_key}",
                        "Content-Type":  _f_icon_file.type or "image/jpeg",
                        "x-upsert":      "true",
                    },
                    method="POST",
                )
                with _urlreq.urlopen(_upload_req) as _r:
                    if _r.status in (200, 201):
                        _f_photo_url = f"{_supa_url}/storage/v1/object/public/creator-photos/{_icon_path}"
                        st.image(_f_photo_url, width=80)
                        st.caption("✅ アイコン画像をアップロードしました")
                    else:
                        st.warning("画像のアップロードに失敗しました。URLは空になります。")
            except Exception as _e_icon:
                st.warning(f"画像アップロードエラー: {_e_icon}")

        st.markdown("---")
        st.markdown("**イベント情報**")

        with st.form("agent_event_form"):
            _f_type  = st.selectbox("イベント種別 *", _CAL_EVENT_TYPES)
            _f_date  = st.date_input("リリース日/配信日/出勤日/開催日 *", min_value=datetime.date.today())

            _use_time = st.checkbox("時刻を指定する", value=True)
            _f_time = _f_time_end = None
            if _use_time:
                _t_col1, _t_col2 = st.columns(2)
                _f_time     = _t_col1.time_input("開始時刻", value=datetime.time(18, 0))
                _f_time_end = _t_col2.time_input("終了時刻（任意）", value=datetime.time(18, 0))

            _f_loc  = st.text_input("場所/プラットフォーム/ゲーム名", placeholder="例：秋葉原○○店 / YouTube Live / Minecraft")
            _f_url  = st.text_input("関連URL（任意）", placeholder="例：https://youtube.com/live/xxxx")
            _f_desc = st.text_area("告知メッセージ（任意）", placeholder="例：初配信です！ぜひ見に来てね！", max_chars=200)

            if st.form_submit_button("🚀 仮登録する", use_container_width=True):
                if not _f_name.strip():
                    st.error("クリエイター名は必須です。")
                else:
                    _jst_tz2 = datetime.timezone(datetime.timedelta(hours=9))
                    if _use_time and _f_time:
                        _ev_dt = datetime.datetime(
                            _f_date.year, _f_date.month, _f_date.day,
                            _f_time.hour, _f_time.minute, tzinfo=_jst_tz2,
                        )
                        _ev_dt_end = None
                        if _f_time_end and _f_time_end != _f_time:
                            _ev_dt_end = datetime.datetime(
                                _f_date.year, _f_date.month, _f_date.day,
                                _f_time_end.hour, _f_time_end.minute, tzinfo=_jst_tz2,
                            )
                    else:
                        _ev_dt     = datetime.datetime(_f_date.year, _f_date.month, _f_date.day, 0, 0, tzinfo=_jst_tz2)
                        _ev_dt_end = None

                    # URLがあれば説明に追記
                    _desc_combined = _f_desc.strip()
                    if _f_url.strip():
                        _desc_combined = (_desc_combined + "\n" + _f_url.strip()).strip()

                    _ins = {
                        "temp_display_name": _f_name.strip(),
                        "temp_photo_url":    _f_photo_url or None,
                        "status":            "unverified",
                        "category":          _f_cat,
                        "event_type":        _f_type,
                        "event_date":        _ev_dt.isoformat(),
                        "location":          _f_loc.strip() or None,
                        "description":       _desc_combined or None,
                        "agent_code":        _CAL_AGENT_CODE,
                    }
                    if _ev_dt_end:
                        _ins["event_date_end"] = _ev_dt_end.isoformat()
                    try:
                        _ins_res = get_db().table("calendar_events").insert(_ins).execute()
                        if _ins_res.data:
                            _new_ev_id = _ins_res.data[0]["id"]
                            _tok       = _cal_create_claim_token(_new_ev_id)
                            if _tok:
                                st.session_state["agent_claim_url"] = f"https://oshipay.streamlit.app/?page=calendar_claim&token={_tok}"
                            st.session_state["agent_submitted"] = True
                            st.rerun()
                        else:
                            st.error("登録に失敗しました。もう一度お試しください。")
                    except Exception as _e_ins:
                        st.error(f"エラーが発生しました: {_e_ins}")

    else:
        st.success("🎉 イベントをカレンダーに仮登録しました！")
        _claim_url = st.session_state.get("agent_claim_url", "")
        if _claim_url:
            st.markdown(
                '<div style="background:rgba(139,92,246,0.1);border:1px solid rgba(139,92,246,0.3);'
                'border-radius:14px;padding:20px;margin:16px 0;">'
                '<div style="font-size:14px;font-weight:800;color:#c4b5fd;margin-bottom:8px;">'
                '🔗 クリエイター引き継ぎURL（Claim URL）</div>'
                '<div style="font-size:12px;color:rgba(240,240,245,0.6);line-height:1.6;">'
                'このURLをクリエイターの公式DMに送ってください。<br>'
                'クリエイターがURLを開いてアカウント登録すると、仮登録データが本人のアカウントに紐付きます。'
                '</div></div>',
                unsafe_allow_html=True,
            )
            st.code(_claim_url)
            if st.button("📋 URLをコピー", use_container_width=True):
                components.html(
                    f'<script>navigator.clipboard.writeText("{_claim_url}").catch(function(){{}});</script>',
                    height=0,
                )
                st.toast("✅ クリップボードにコピーしました！")

        _btn_c1, _btn_c2 = st.columns(2)
        if _btn_c1.button("📅 カレンダーを見る", use_container_width=True):
            st.session_state["agent_submitted"] = False
            st.session_state["agent_claim_url"] = ""
            st.query_params["page"] = "calendar"
            st.rerun()
        if _btn_c2.button("➕ 続けて登録する", use_container_width=True, type="secondary"):
            st.session_state["agent_submitted"] = False
            st.session_state["agent_claim_url"] = ""
            st.rerun()

    st.markdown(
        '<div style="text-align:center;margin-top:16px;">'
        '<a href="?page=calendar" style="font-size:12px;color:rgba(240,240,245,0.35);text-decoration:none;">'
        '← カレンダーに戻る</a></div>',
        unsafe_allow_html=True,
    )


# ── Claim 引き継ぎページ ──────────────────────────────────────────
if page == "calendar_claim":
    st.markdown('<div class="oshi-logo"><span class="text">oshipay</span></div>', unsafe_allow_html=True)

    _tok_param = params.get("token", "")
    if not _tok_param:
        st.error("無効なURLです。")
        st.link_button("📅 カレンダーを見る", "?page=calendar", use_container_width=True)
        st.stop()

    try:
        _tok_res  = get_db().table("claim_tokens").select("*").eq("token", _tok_param).limit(1).execute()
        _tok_data = (_tok_res.data or [None])[0]
    except Exception:
        _tok_data = None

    if not _tok_data:
        st.error("このURLは無効です。")
        st.link_button("📅 カレンダーを見る", "?page=calendar", use_container_width=True)
        st.stop()

    if _tok_data.get("is_used"):
        st.info("✅ このイベントはすでに引き継ぎ済みです。")
        st.link_button("📅 カレンダーを見る", "?page=calendar", use_container_width=True)
        st.stop()

    _exp_str = _tok_data.get("expires_at", "")
    if _exp_str:
        try:
            _exp_dt = datetime.datetime.fromisoformat(_exp_str.replace("Z", "+00:00"))
            if datetime.datetime.now(datetime.timezone.utc) > _exp_dt:
                st.error("このURLは有効期限切れです。運営にご連絡ください。")
                st.link_button("📅 カレンダーを見る", "?page=calendar", use_container_width=True)
                st.stop()
        except Exception:
            pass

    _claim_ev_id = _tok_data.get("event_id", "")
    try:
        _ev_res  = get_db().table("calendar_events").select("*").eq("id", _claim_ev_id).limit(1).execute()
        _ev_data = (_ev_res.data or [None])[0]
    except Exception:
        _ev_data = None

    if not _ev_data:
        st.error("対象イベントが見つかりません。")
        st.link_button("📅 カレンダーを見る", "?page=calendar", use_container_width=True)
        st.stop()

    _temp_name = _ev_data.get("temp_display_name", "???")
    _ev_type3  = _ev_data.get("event_type", "")
    _ev_date3  = _cal_format_date(_ev_data.get("event_date", ""))

    st.markdown(
        f'<div style="background:rgba(139,92,246,0.08);border:1px solid rgba(139,92,246,0.2);'
        f'border-radius:16px;padding:20px;margin:12px 0;">'
        f'<div style="font-size:16px;font-weight:900;color:#f0f0f5;margin-bottom:4px;">'
        f'「{_temp_name}」のイベント</div>'
        f'<div style="font-size:13px;color:rgba(240,240,245,0.6);">{_ev_type3} ・ {_ev_date3}</div>'
        f'<div style="font-size:12px;color:rgba(240,240,245,0.45);margin-top:8px;">'
        f'このイベントはあなたのものですか？</div></div>',
        unsafe_allow_html=True,
    )

    st.markdown("**このイベントを引き継いで、OshiPayアカウントと連携しましょう！**")

    _logged_in_acct = st.session_state.get("creator_auth", "")
    if _logged_in_acct:
        _c_inf = get_db().table("creators").select("display_name").eq("acct_id", _logged_in_acct).limit(1).execute()
        _c_nm  = _c_inf.data[0].get("display_name", _logged_in_acct) if _c_inf.data else _logged_in_acct
        st.info(f"ログイン中： **{_c_nm}** としてこのイベントを引き継ぎます。")
        if st.button("✅ このアカウントで引き継ぐ", use_container_width=True):
            try:
                get_db().table("calendar_events").update({
                    "creator_acct": _logged_in_acct,
                    "status": "verified",
                }).eq("id", _claim_ev_id).execute()
                get_db().table("claim_tokens").update({"is_used": True}).eq("token", _tok_param).execute()
                st.success("🎉 引き継ぎ完了！イベントがあなたのアカウントに紐付きました。")
                st.balloons()
                st.link_button("📅 カレンダーを見る", "?page=calendar", use_container_width=True)
            except Exception as _e_claim:
                st.error(f"引き継ぎ中にエラーが発生しました: {_e_claim}")
    else:
        st.session_state["pending_claim_token"] = _tok_param
        st.session_state["pending_claim_ev_id"] = _claim_ev_id
        _cl1, _cl2 = st.columns(2)
        _cl1.link_button("📝 新規アカウント作成", "?page=dashboard&tab=new", use_container_width=True)
        _cl2.link_button("🔑 ログイン",           "?page=dashboard",         use_container_width=True)
        st.markdown(
            '<div style="font-size:12px;color:rgba(240,240,245,0.4);text-align:center;margin-top:8px;">'
            'ログイン後、このURLを再度開いて引き継ぎを完了してください。</div>',
            unsafe_allow_html=True,
        )

    st.markdown(
        '<div style="text-align:center;margin-top:20px;">'
        '<a href="?page=calendar" style="font-size:12px;color:rgba(240,240,245,0.35);text-decoration:none;">'
        '← カレンダーに戻る</a></div>',
        unsafe_allow_html=True,
    )
