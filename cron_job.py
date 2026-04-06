"""
oshipay cron ジョブ
GitHub Actions から毎時実行される。

処理内容:
  ④ 24時間前リマインド: expires_at まで24時間を切った pending に支払いリマインドメール送信
  ⑤ 自動キャンセル:    expires_at を過ぎた pending を cancelled に更新し、双方にキャンセルメール送信
"""

import os
import datetime
import urllib.parse
import resend
import stripe

from supabase import create_client

# ── 環境変数 ──────────────────────────────────────────
SUPABASE_URL     = os.environ["SUPABASE_URL"]
SUPABASE_KEY     = os.environ["SUPABASE_SERVICE_KEY"]   # service_role キー
RESEND_API_KEY   = os.environ["RESEND_API_KEY"]
STRIPE_SECRET    = os.environ["STRIPE_SECRET"]
BASE_URL         = os.environ.get("APP_URL", "https://oshipay.me").rstrip("/") + "/"
RESEND_FROM      = "noreply@oshipay.me"
PAYOUT_THRESHOLD = 10000  # ¥10,000以上で自動ペイアウト

resend.api_key   = RESEND_API_KEY
stripe.api_key   = STRIPE_SECRET
db = create_client(SUPABASE_URL, SUPABASE_KEY)
now = datetime.datetime.now(datetime.timezone.utc)

# ── メール送信ヘルパー ─────────────────────────────────
def send_email(to_email: str, subject: str, body: str):
    resend.Emails.send({"from": RESEND_FROM, "to": [to_email], "subject": subject, "text": body})

def jst_str(dt: datetime.datetime) -> str:
    jst = dt.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    return jst.strftime("%Y/%m/%d %H:%M（JST）")

def get_creator_info(creator_acct: str) -> dict:
    try:
        r = db.table("creators").select("display_name,name,email").eq("acct_id", creator_acct).maybe_single().execute()
        return r.data or {}
    except Exception:
        return {}

def get_supporter_display_name(supporter_id: str) -> str:
    """supporter_id から display_name を取得。なければ '匿名' を返す"""
    if not supporter_id:
        return "匿名"
    try:
        r = db.table("supporters").select("display_name").eq("supporter_id", supporter_id).maybe_single().execute()
        return (r.data or {}).get("display_name", "") or "匿名"
    except Exception:
        return "匿名"

# ══════════════════════════════════════════════════════
# ④ 24時間前リマインドメール
# ══════════════════════════════════════════════════════
print("── ④ リマインド処理 開始 ──")

remind_from = now + datetime.timedelta(hours=0)
remind_to   = now + datetime.timedelta(hours=24)

try:
    rows = (
        db.table("pending_supports")
        .select("*")
        .eq("status", "pending")
        .is_("reminded_at", "null")          # まだリマインド未送信
        .gte("expires_at", remind_from.isoformat())
        .lte("expires_at", remind_to.isoformat())
        .execute()
    )
    remind_targets = rows.data or []
except Exception as e:
    print(f"  リマインド取得エラー: {e}")
    remind_targets = []

remind_count = 0
for row in remind_targets:
    pid          = str(row["id"])
    sup_email    = row.get("supporter_email", "")
    sup_id       = row.get("supporter_id", "")
    creator_acct = row.get("creator_acct", "")
    amount       = row.get("amount", 0)
    message      = row.get("message", "")
    try:
        exp_dt  = datetime.datetime.fromisoformat(row["expires_at"].replace("Z", "+00:00"))
        exp_str = jst_str(exp_dt)
    except Exception:
        exp_str = "まもなく期限切れ"

    cr = get_creator_info(creator_acct)
    creator_name = cr.get("display_name") or cr.get("name") or "クリエイター"
    pay_url = f"{BASE_URL}?page=pay_pending&pid={pid}&email={urllib.parse.quote(sup_email)}"
    sup_disp = get_supporter_display_name(sup_id)

    # サポーターへリマインドメール
    if sup_email:
        try:
            subject = f"【oshipay】⏰ {creator_name}さんへの応援 支払い期限まで24時間を切りました"
            body = (
                f"{sup_disp}さん\n\n"
                f"応援ありがとうございます！\n\n"
                f"{creator_name}さんへの応援の支払い期限まで24時間を切りました。\n\n"
                f"💰 応援金額: {amount:,}円\n"
                f"⏰ 有効期限: {exp_str}\n\n"
                f"🔗 支払いはこちら:\n{pay_url}\n\n"
                f"期限を過ぎると自動的にキャンセルとなりますのでご注意ください。\n\n"
                f"--\noshipay\n{BASE_URL}"
            )
            send_email(sup_email, subject, body)
            print(f"  リマインドメール送信: {sup_email} (pid={pid})")
        except Exception as e:
            print(f"  リマインドメール失敗: {sup_email} - {e}")

    # reminded_at を更新
    try:
        db.table("pending_supports").update({"reminded_at": now.isoformat()}).eq("id", pid).execute()
        remind_count += 1
    except Exception as e:
        print(f"  reminded_at 更新失敗: {e}")

print(f"  リマインド処理完了: {remind_count}件")

# ══════════════════════════════════════════════════════
# ⑤ 自動キャンセル + 双方へキャンセルメール
# ══════════════════════════════════════════════════════
print("── ⑤ 自動キャンセル処理 開始 ──")

try:
    expired_rows = (
        db.table("pending_supports")
        .select("*")
        .eq("status", "pending")
        .lt("expires_at", now.isoformat())
        .execute()
    )
    expired_targets = expired_rows.data or []
except Exception as e:
    print(f"  期限切れ取得エラー: {e}")
    expired_targets = []

cancel_count = 0
for row in expired_targets:
    pid          = str(row["id"])
    sup_email    = row.get("supporter_email", "")
    creator_acct = row.get("creator_acct", "")
    amount       = row.get("amount", 0)

    cr = get_creator_info(creator_acct)
    creator_name  = cr.get("display_name") or cr.get("name") or "クリエイター"
    creator_email = cr.get("email", "")
    _cancel_sup_id = row.get("supporter_id", "")
    _cancel_sup_disp = get_supporter_display_name(_cancel_sup_id)

    # status を cancelled に更新
    try:
        db.table("pending_supports").update({"status": "cancelled"}).eq("id", pid).execute()
    except Exception as e:
        print(f"  キャンセル更新失敗 pid={pid}: {e}")
        continue

    # サポーターへキャンセルメール
    if sup_email:
        try:
            subject = f"【oshipay】{creator_name}さんへの応援金がキャンセルされました"
            body = (
                f"{_cancel_sup_disp}さん\n\n"
                f"お知らせです。\n\n"
                f"{creator_name}さんへの応援金について、期限内にお支払いが完了しなかったため、キャンセルとなりました。\n\n"
                f"💰 応援金額: {amount:,}円\n\n"
                f"もし引き続き応援いただける場合は、再度 oshipay.me からお手続きいただけますと幸いです。\n\n"
                f"--\noshipay\n{BASE_URL}"
            )
            send_email(sup_email, subject, body)
            print(f"  キャンセルメール(サポーター): {sup_email} (pid={pid})")
        except Exception as e:
            print(f"  キャンセルメール失敗(サポーター): {e}")

    # クリエイターへキャンセルメール
    if creator_email:
        try:
            subject = f"【oshipay】応援チケットがキャンセルになりました"
            body = (
                f"{creator_name}さん\n\n"
                f"{_cancel_sup_disp}さんから期限内に応援金が支払われなかったため、以下の応援チケットがキャンセルとなりました。\n\n"
                f"💰 金額: {amount:,}円\n\n"
                f"今後サポーターから新たに応援金が届いた場合には、口座へ入金されます。\n引き続きよろしくお願いします！\n\n"
                f"--\noshipay\n{BASE_URL}"
            )
            send_email(creator_email, subject, body)
            print(f"  キャンセルメール(クリエイター): {creator_email} (pid={pid})")
        except Exception as e:
            print(f"  キャンセルメール失敗(クリエイター): {e}")

    cancel_count += 1

print(f"  自動キャンセル処理完了: {cancel_count}件")
# ══════════════════════════════════════════════════════
# ⑥ 自動ペイアウト（¥10,000以上貯まったクリエイターに振込）
# ══════════════════════════════════════════════════════
print("── ⑥ 自動ペイアウト処理 開始 ──")

try:
    payout_creators = (
        db.table("creators")
        .select("acct_id,display_name,name,email,stripe_acct_id")
        .eq("payout_enabled", True)
        .not_.is_("stripe_acct_id", "null")
        .execute()
    )
    payout_targets = payout_creators.data or []
except Exception as e:
    print(f"  クリエイター取得エラー: {e}")
    payout_targets = []

payout_count = 0
for creator in payout_targets:
    stripe_acct_id = creator.get("stripe_acct_id", "")
    creator_name   = creator.get("display_name") or creator.get("name") or "クリエイター"
    creator_email  = creator.get("email", "")
    if not stripe_acct_id:
        continue
    try:
        balance   = stripe.Balance.retrieve(stripe_account=stripe_acct_id)
        available = next((b.amount for b in balance.available if b.currency == "jpy"), 0)
        if available >= PAYOUT_THRESHOLD:
            stripe.Payout.create(
                amount=available,
                currency="jpy",
                stripe_account=stripe_acct_id
            )
            print(f"  ペイアウト実行: {stripe_acct_id} ¥{available:,}")
            # クリエイターへ通知メール
            if creator_email:
                try:
                    send_email(
                        creator_email,
                        "【oshipay】応援金の振込を実行しました",
                        f"{creator_name}さん\n\n"
                        f"口座残高が¥{PAYOUT_THRESHOLD:,}を超えたため、¥{available:,}の振込を実行しました。\n"
                        f"銀行口座への反映まで数営業日かかる場合があります。\n\n"
                        f"--\noshipay\n{BASE_URL}"
                    )
                except Exception as e:
                    print(f"  ペイアウト通知メール失敗: {e}")
            payout_count += 1
        else:
            print(f"  残高不足でスキップ: {stripe_acct_id} ¥{available:,} / ¥{PAYOUT_THRESHOLD:,}")
    except Exception as e:
        print(f"  ペイアウトエラー: {stripe_acct_id} - {e}")

print(f"  自動ペイアウト処理完了: {payout_count}件")
print("── cron_job.py 完了 ──")
