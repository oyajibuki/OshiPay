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
    buf = io.BytesIO(); qr_img.save(buf, format="PNG"); qr_bytes = buf.getvalue(); b64 = base64.b64encode(qr_bytes).decode()
    return b64, qr_bytes

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# スタイル & UIパーツ
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
.oshi-tagline { text-align: center; font-size: 13px; color: rgba(240,240,245,0.35); margin-bottom: 28px; }
.section-title { font-size: 20px; font-weight: 700; text-align: center; color: #f0f0f5; margin-bottom: 6px; }
.section-subtitle { font-size: 13px; color: rgba(240,240,245,0.6); text-align: center; margin-bottom: 24px; }
.support-avatar { width: 72px; height: 72px; border-radius: 50%; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); display: flex; align-items: center; justify-content: center; font-size: 32px; margin: 0 auto 14px; box-shadow: 0 0 30px rgba(139,92,246,0.3); }
.support-name { font-size: 22px; font-weight: 800; text-align: center; color: #f0f0f5; }
.support-label { font-size: 13px; color: rgba(240,240,245,0.6); text-align: center; margin-bottom: 20px; }
.selected-amount-display { text-align: center; font-size: 36px; font-weight: 900; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316); -webkit-background-clip: text; -webkit-text-fill-color: transparent; margin: 10px 0; }
.stButton > button { width: 100%; background: linear-gradient(135deg, #8b5cf6, #ec4899, #f97316) !important; color: white !important; border: none !important; border-radius: 9999px !important; padding: 16px !important; font-weight: 700 !important; }
.oshi-footer { text-align: center; margin-top: 24px; font-size: 11px; color: rgba(240,240,245,0.35); }
.oshi-footer a { color: #8b5cf6; text-decoration: none; }
.legal-links a { font-size: 10px; color: rgba(240,240,245,0.3); text-decoration: none; margin: 0 5px; }
.oshi-divider { height: 1px; background: rgba(255,255,255,0.08); margin: 20px 0; }
.qr-frame { background: white; padding: 16px; border-radius: 20px; display: inline-block; margin: 0 auto; }
</style>
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
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: none !important; padding: 0 !important; margin: 0 !important; }</style>", unsafe_allow_html=True)
elif IS_LEGAL_PAGE:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 800px !important; margin: 0 auto; }</style>", unsafe_allow_html=True)
else:
    st.markdown("<style>.stMainBlockContainer, .block-container { max-width: 460px !important; margin: 0 auto; }</style>", unsafe_allow_html=True)

# ── 外部HTMLファイルの表示 ──
LEGAL_MAP = {
    "terms": "role/index.html",
    "privacy": "role/index2.html",
    "legal": "role/index3.html"
}

if page in LEGAL_MAP:
    html_content = read_html_file(LEGAL_MAP[page])
    # スクロール位置リセット用JSを注入
    html_content = inject_top_scroll_script(html_content)
    components.html(html_content, height=2000, scrolling=True)
    st.stop()

# ── ランディングページ ──
if page == "lp":
    lp_html = read_html_file("oshipay-lp/index.html")
    st.markdown("""
    <style>
    /* デフォルト (PC) の高さ */
    iframe { height: 3300px !important; border: none; }

    /* モバイル用の高さ調整 (幅768px以下) */
    @media (max-width: 768px) {
        iframe { height: 5800px !important; }
    }
    </style>
    """, unsafe_allow_html=True)
    components.html(lp_html, height=5800)
    st.stop()

# ── 成功ページ ──
if page == "success":
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:80px;margin-bottom:20px;">🎉</div><div class="section-title">応援完了！</div>', unsafe_allow_html=True)
    st.markdown('<div class="section-subtitle">ありがとうございます！🙏</div>', unsafe_allow_html=True)
    
    s_name = params.get("s_name", "")
    s_amt_str = params.get("s_amt", "0")
    s_acct = params.get("s_acct", "")
    s_msg = params.get("s_msg", "")
    
    # ── 応援メール送信 ──
    try:
        s_amt = int(s_amt_str)
    except ValueError:
        s_amt = 0
    
    if s_acct and s_name and s_amt > 0:
        try:
            # クリエイターのメールアドレスを取得
            acct_info = stripe.Account.retrieve(s_acct)
            creator_email = acct_info.get("email", "")
            
            if creator_email:
                ok, err = send_support_email(creator_email, s_name, s_amt, s_msg)
                if not ok:
                    st.error(f"⚠️ 通知メールの送信に失敗しました。\nエラー内容: {err}")
                else:
                    st.success("✅ クリエイターへ応援通知メールを送信しました！")
        except Exception as mail_err:
            st.error(f"❌ メール送信処理中にエラーが発生しました")
    share_text = f"応援したよ！\n{BASE_URL} #OshiPay"
    st.link_button("𝕏 でシェア", f"https://twitter.com/intent/tweet?text={urllib.parse.quote(share_text)}", use_container_width=True)
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms" target="_top">利用規約</a><a href="{BASE_URL}?page=privacy" target="_top">プライバシーポリシー</a><a href="{BASE_URL}?page=legal" target="_top">特定商取引法</a></div>', unsafe_allow_html=True)
    st.stop()

# ── キャンセル ──
elif page == "cancel":
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div style="text-align:center;font-size:80px;margin-bottom:20px;">🤔</div><div class="section-title">キャンセルしました</div>', unsafe_allow_html=True)
    st.stop()

# ── 応援・ダッシュボード ──
support_user = params.get("user", "")
connect_acct = params.get("acct", "")
support_name = params.get("name", "")
support_icon = params.get("icon", "🎤")

if page == "support" and support_user:
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
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

    st.markdown(f'<div class="selected-amount-display">¥{int(st.session_state.amt):,}</div>', unsafe_allow_html=True)
    msg = st.text_area("応援メッセージ（オプション）", max_chars=140)
    
    # ボタンの無効化処理を追加
    is_disabled = st.session_state.amt < 100
    if is_disabled:
        st.info("💡 応援は100円から受け付けています。金額を選択してください。")

    if st.button("🔥 応援する！", disabled=is_disabled):
        amt = st.session_state.amt
        try:
            checkout_params = {
                "payment_method_types": ["card"], "mode": "payment",
                "line_items": [{"price_data": {"currency": "jpy", "product_data": {"name": f"{support_name}への応援"}, "unit_amount": amt}, "quantity": 1}],
                "success_url": f"{BASE_URL}?page=success&s_name={urllib.parse.quote(support_name)}&s_amt={amt}&s_acct={connect_acct}&s_msg={urllib.parse.quote(msg or '')}", "cancel_url": f"{BASE_URL}?page=cancel",
                "metadata": {"user_id": support_user, "message": msg}
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

else: # Dashboard
    st.markdown('<div class="oshi-logo"><span class="icon">🔥</span> <span class="text">OshiPay</span></div>', unsafe_allow_html=True)
    st.markdown('<div class="section-title">QRコードを発行</div>', unsafe_allow_html=True)
    # アカウントIDの特定
    acct_id = connect_acct or params.get("acct")
    
    if not acct_id:
        st.markdown('<div class="header">応援用QRコードを作成</div>', unsafe_allow_html=True)
        st.write("応援（決済）を受け取るためのStripeアカウントを作成、または連携します。")
        
        # 明示的なボタンによる発行の意思確認
        if st.checkbox("新規にQRコードを発行して応援を受け取りますか？"):
            if "onboarding_url" not in st.session_state:
                if st.button("🔗 Stripeアカウントを連携する"):
                    with st.spinner("Stripeと連携する準備をしています... (数秒かかります)"):
                        try:
                            # アカウント作成（ウェブサイトURLなどを事前注入）
                            acct_id = create_connect_account()
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
    else:
        st.markdown(f"""
        <div style="background: rgba(139,92,246,0.1); border: 1px solid rgba(139,92,246,0.2); border-radius: 12px; padding: 16px; margin-bottom: 20px;">
            <div style="color: #8b5cf6; font-weight: 700; font-size: 14px; margin-bottom: 4px;">✅ Stripe連携済み</div>
            <div style="font-size: 12px; color: rgba(240,240,245,0.6); margin-bottom: 12px;">ID: <code>{acct_id}</code></div>
            <div style="font-size: 11px; color: #f97316; font-weight: 700; margin-bottom: 8px;">⚠️ ログイン機能はありません。このページをブックマークして保存してください！</div>
        </div>
        """, unsafe_allow_html=True)
        
        name = st.text_input("表示名", value=st.session_state.get("name", ""))
        icon = st.selectbox("アイコン", list(ICON_OPTIONS.keys()))
        
        col1, col2 = st.columns([2, 1])
        if col1.button("✨ QRコードを生成"):
            support_url = f"{BASE_URL}?page=support&user={uuid.uuid4()}&name={urllib.parse.quote(name)}&icon={icon}&acct={acct_id}"
            st.session_state.qr_url = support_url
        
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
            st.markdown(f'<div class="qr-frame"><img src="data:image/png;base64,{generate_qr_data(st.session_state.qr_url)[0]}"></div>', unsafe_allow_html=True)
            st.code(st.session_state.qr_url)
    st.markdown(f'<div class="oshi-footer">Powered by <a href="{BASE_URL}?page=dashboard">OshiPay</a></div>', unsafe_allow_html=True)
    st.markdown(f'<div class="legal-links text-center pt-2"><a href="{BASE_URL}?page=terms" target="_top">利用規約</a><a href="{BASE_URL}?page=privacy" target="_top">プライバシーポリシー</a><a href="{BASE_URL}?page=legal" target="_top">特定商取引法</a></div>', unsafe_allow_html=True)