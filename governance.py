"""
OshiPay ガバナンス・バリデーションモジュール
フェーズ1 必須ルール実装
"""
import re

# ── 予約ワード（ユーザーIDに使えないワード）──
RESERVED_USERNAMES = {
    "admin", "support", "help", "contact", "api", "login", "signup",
    "register", "oshipay", "official", "staff", "system", "root",
    "moderator", "mod", "bot", "service", "info", "news", "about",
    "terms", "privacy", "legal", "faq", "home", "dashboard", "ranking",
    "success", "cancel", "reply", "profile", "creator", "supporter",
}

# ── NGワード（表示名・プロフィール禁止 — なりすまし防止）──
NG_DISPLAY_NAME = [
    "公式", "運営", "サポート", "support", "official", "staff",
    "paypay", "stripe", "oshipay", "管理者", "admin", "moderator",
    "PayPay", "Stripe", "OshiPay",
]

# ── 外部連絡先パターン（bio等で禁止）──
_CONTACT_PATTERNS = [
    re.compile(r'\d{2,4}[-.\s]?\d{3,4}[-.\s]?\d{4}'),           # 電話番号
    re.compile(r'[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}'),                # メールアドレス
    re.compile(r'(?i)(line|ライン)\s*(id|ID|Id)\s*[:：]?\s*\S+'),  # LINE ID
    re.compile(r'(?i)lineid[:：]?\s*\S+'),                        # lineid: xxx
]

# ── 短縮URLパターン ──
_SHORT_URL_PATTERNS = re.compile(
    r'(?i)(bit\.ly|shorturl|tinyurl|goo\.gl|ow\.ly|buff\.ly|tiny\.cc|is\.gd|v\.gd)'
)

# ── 許可SNSパターン ──
_ALLOWED_SNS_PATTERNS = [
    re.compile(r'^https?://(www\.)?x\.com/[\w.]{1,50}/?$', re.IGNORECASE),
    re.compile(r'^https?://(www\.)?twitter\.com/[\w.]{1,50}/?$', re.IGNORECASE),
    re.compile(r'^https?://(www\.)?instagram\.com/[\w.]{1,50}/?$', re.IGNORECASE),
    re.compile(r'^https?://(www\.)?youtube\.com/(channel/[\w-]+|@[\w.]+|c/[\w.]+)/?$', re.IGNORECASE),
    re.compile(r'^https?://(www\.)?tiktok\.com/@[\w.]{1,50}/?$', re.IGNORECASE),
    re.compile(r'^https?://note\.com/[\w.]{1,50}/?$', re.IGNORECASE),
    re.compile(r'^https?://(www\.)?facebook\.com/[\w.\-]{1,100}/?$', re.IGNORECASE),
    re.compile(r'^https?://line\.me/[\w/.\-]{1,100}$', re.IGNORECASE),
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# バリデーション関数
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_password(password: str) -> tuple[bool, str]:
    """
    パスワードポリシーチェック
    - 8文字以上
    - 半角英数字のみ
    - 英字と数字を両方含む
    - 同じ文字の3連続禁止
    """
    if len(password) < 8:
        return False, "パスワードは8文字以上にしてください。"
    if not re.match(r'^[a-zA-Z0-9]+$', password):
        return False, "パスワードは半角英数字のみ使用できます（記号不可）。"
    if not re.search(r'[a-zA-Z]', password):
        return False, "パスワードには英字を1文字以上含めてください（例: Oshi1234）。"
    if not re.search(r'[0-9]', password):
        return False, "パスワードには数字を1文字以上含めてください（例: Oshi1234）。"
    if re.search(r'(.)\1\1', password):
        return False, "同じ文字を3文字以上連続して使用できません（例: aaa）。"
    return True, ""


def validate_username(slug: str, taken_slugs: list = None) -> tuple[bool, str]:
    """
    ユーザーID（slug）バリデーション
    - 3〜20文字
    - 半角英数字＋ハイフンのみ
    - 先頭・末尾ハイフン禁止
    - 連続ハイフン禁止
    - 予約ワード禁止
    - 重複禁止
    """
    if not slug:
        return False, "ユーザーIDを入力してください。"
    if len(slug) < 3:
        return False, "ユーザーIDは3文字以上にしてください。"
    if len(slug) > 20:
        return False, "ユーザーIDは20文字以下にしてください。"
    if not re.match(r'^[a-zA-Z0-9\-]+$', slug):
        return False, "ユーザーIDは半角英数字とハイフン(-)のみ使用できます。"
    if slug.startswith('-') or slug.endswith('-'):
        return False, "ユーザーIDの先頭・末尾にハイフンは使用できません。"
    if '--' in slug:
        return False, "ユーザーIDに連続したハイフンは使用できません。"
    if slug.lower() in RESERVED_USERNAMES:
        return False, f"「{slug}」は予約済みのため使用できません。"
    if taken_slugs and slug.lower() in [s.lower() for s in taken_slugs]:
        return False, "このユーザーIDはすでに使用されています。"
    return True, ""


def validate_display_name(name: str) -> tuple[bool, str]:
    """
    表示名バリデーション
    - 1〜30文字
    - NGワードチェック（なりすまし防止）
    """
    if not name:
        return False, "表示名を入力してください。"
    if len(name) > 30:
        return False, "表示名は30文字以下にしてください。"
    name_lower = name.lower()
    for ng in NG_DISPLAY_NAME:
        if ng.lower() in name_lower:
            return False, f"「{ng}」を含む表示名は使用できません（なりすまし防止）。"
    return True, ""


def validate_bio(bio: str) -> tuple[bool, str]:
    """
    プロフィール文章バリデーション
    - 500文字以内
    - 外部連絡先禁止（電話番号・メール・LINE ID）
    - 短縮URL禁止
    """
    if len(bio) > 500:
        return False, f"プロフィールは500文字以内にしてください（現在: {len(bio)}文字）。"
    for pattern in _CONTACT_PATTERNS:
        if pattern.search(bio):
            return False, "プロフィールに外部連絡先（電話番号・メール・LINE IDなど）を含めることはできません（詐欺防止）。"
    if _SHORT_URL_PATTERNS.search(bio):
        return False, "プロフィールに短縮URLを含めることはできません。"
    return True, ""


def normalize_sns_url(url: str) -> str:
    """https:// が欠けていれば補完する"""
    if not url:
        return ""
    url = url.strip()
    if url and not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url
    return url


def validate_sns_url(url: str) -> tuple[bool, str]:
    """
    SNSリンクバリデーション（X/Instagram/YouTube/TikTok/note/Facebook/LINE のみ許可）
    空文字列は許可（任意入力）。https:// の欠落は自動補完して検証。
    """
    if not url or not url.strip():
        return True, ""
    url = normalize_sns_url(url)
    # 短縮URL禁止
    if _SHORT_URL_PATTERNS.search(url):
        return False, "短縮URLは使用できません。"
    # 許可SNSチェック
    for pattern in _ALLOWED_SNS_PATTERNS:
        if pattern.match(url):
            return True, ""
    return False, "このURLは使用できません。X・Instagram・YouTube・TikTok・note・Facebook・LINEのURLのみ登録できます。"


def validate_image_file(file_obj, max_mb: float = 2.0) -> tuple[bool, str]:
    """
    アイコン画像バリデーション
    - JPEG / PNG のみ
    - 2MB以下
    """
    if file_obj is None:
        return True, ""  # 未選択は許可
    allowed_types = ["image/jpeg", "image/jpg", "image/png"]
    if hasattr(file_obj, "type") and file_obj.type not in allowed_types:
        return False, "画像はJPEGまたはPNG形式のみアップロードできます。"
    max_bytes = int(max_mb * 1024 * 1024)
    size = file_obj.size if hasattr(file_obj, "size") else len(file_obj.getvalue())
    if size > max_bytes:
        return False, f"画像は{max_mb}MB以下にしてください（現在: {size / 1024 / 1024:.1f}MB）。"
    return True, ""


def check_slug_taken(db_client, slug: str) -> bool:
    """Supabase で slug の重複チェック。使用済みならTrue。"""
    try:
        resp = db_client.table("creators").select("slug").eq("slug", slug.lower()).execute()
        return bool(resp.data)
    except Exception:
        return False


def check_slug_locked(db_client, slug: str) -> bool:
    """削除済みアカウントの slug ロックチェック。ロック済みならTrue。"""
    try:
        resp = db_client.table("deleted_slugs").select("slug").eq("slug", slug.lower()).execute()
        return bool(resp.data)
    except Exception:
        return False
