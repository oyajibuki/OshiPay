"""
OshiPay DR同期スクリプト
本番DB (oshipay2JP) → バックアップDB (oshipay) へデータを同期する

使い方:
  1. supabase/.env.dr を作成して認証情報を記入
  2. pip install supabase python-dotenv
  3. python supabase/sync_to_dr.py

同期対象テーブル（優先度順）:
  - creators          / supporters / supporter_accounts
  - supports          / pending_supports
  - deleted_slugs     / stamps
除外: bot_logs（復旧に不要）
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# .env.dr を読み込む（スクリプトの場所から探す）
env_path = Path(__file__).parent / ".env.dr"
load_dotenv(env_path)

PRIMARY_URL = os.environ.get("PRIMARY_SUPABASE_URL", "")
PRIMARY_KEY = os.environ.get("PRIMARY_SUPABASE_KEY", "")  # service_role key
DR_URL      = os.environ.get("DR_SUPABASE_URL", "")
DR_KEY      = os.environ.get("DR_SUPABASE_KEY", "")       # service_role key

if not all([PRIMARY_URL, PRIMARY_KEY, DR_URL, DR_KEY]):
    print("❌ supabase/.env.dr に認証情報が不足しています。.env.dr.example を参照してください。")
    sys.exit(1)

primary = create_client(PRIMARY_URL, PRIMARY_KEY)
dr      = create_client(DR_URL, DR_KEY)

# テーブル名, 主キー列名（upsert用）
TABLES = [
    ("creators",           "acct_id"),
    ("supporters",         "supporter_id"),
    ("supporter_accounts", "supporter_id"),
    ("supports",           "support_id"),
    ("pending_supports",   "id"),
    ("deleted_slugs",      "slug"),
    ("stamps",             "id"),
]


def fetch_all(client, table: str) -> list:
    """1000件ずつページネーションして全行取得"""
    rows = []
    limit = 1000
    offset = 0
    while True:
        res = client.table(table).select("*").range(offset, offset + limit - 1).execute()
        rows.extend(res.data or [])
        if len(res.data or []) < limit:
            break
        offset += limit
    return rows


def sync_table(table: str, pk: str) -> tuple[int, str]:
    """1テーブルを同期。(件数, ステータス) を返す"""
    try:
        rows = fetch_all(primary, table)
        if not rows:
            return 0, "skip（データなし）"
        # 1000件ずつバッチでupsert
        batch = 1000
        for i in range(0, len(rows), batch):
            dr.table(table).upsert(rows[i:i+batch], on_conflict=pk).execute()
        return len(rows), "✅"
    except Exception as e:
        return 0, f"❌ {e}"


def main():
    started = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*50}")
    print(f"OshiPay DR同期開始: {started}")
    print(f"本番 → {PRIMARY_URL[:40]}...")
    print(f"DR   → {DR_URL[:40]}...")
    print(f"{'='*50}\n")

    total_rows = 0
    for table, pk in TABLES:
        count, status = sync_table(table, pk)
        total_rows += count
        print(f"  {status}  {table:<25} {count:>6} 行")

    finished = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*50}")
    print(f"完了: {finished}  合計 {total_rows} 行同期")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
