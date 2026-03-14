# ClearCut アプリケーション仕様書

## 1. 概要
「ClearCut」は、AI（rembg）を使用して画像から背景を高精度で切り抜くブラウザベースのWebアプリケーションです。Stripe決済と連携し、無料ユーザーには1日3回の利用制限、有料ユーザーには無制限の利用権（ライセンスキー）を提供します。

## 2. システム構成・技術スタック
- **フロントエンド**: HTML5, Vanilla JavaScript, CSS (外部フレームワーク不使用), i18n (多言語対応エンジン自作)
- **バックエンド**: Python 3.10, FastAPI, Uvicorn
- **AIエンジン**: `rembg` (以下の複数モデルを選択可能)
    - `isnet-general-use`: 一般用途向け高品質モデル（デフォルト）
    - `u2net`: 標準的な汎用モデル
    - `u2net_human_seg`: 人物の切り抜きに特化したモデル
    - `silueta`: 高速処理に特化した軽量モデル
- **外部連携**: 
    - Google Apps Script (GAS): メール送信、スプレッドシートへのアクセス/購入ログ記録
    - Stripe: 決済（Apple Pay, Google Pay, PayPay, 銀行振込等に対応）

## 3. 主要機能
### 3.1. 背景切り抜き機能
- ドラッグ＆ドロップまたはクリックで画像をアップロード
- AIモデルの選択機能（品質重視・速度重視・人物特化など）
- ブラウザ上でAI処理を実行し、背景を透過
- 元画像と処理後の比較表示

### 3.2. 多言語対応 (i18n)
- 5カ国語に対応：英語、日本語、中国語、ヒンディ語、ポルトガル語
- OSに依存せず国旗を表示するためのカスタムSVGドロップダウンUIを搭載
- 言語選択はブラウザの `localStorage` に保存され、次回訪問時も維持

### 3.3. ブラシツール（手動微調整機能）
- **消しゴム（Erase）** / **復元（Restore）**：AIの結果をピクセル単位で微調整

### 3.4. マネタイズ・アクセス管理
- **利用制限**: 1日3回までの無料枠（IPベース管理）
- **Stripe連携**: `payment_method_types`を自動設定にすることで、Apple Pay/Google Pay/PayPayなど多彩な決済に対応
- **購入後の自動化**: Stripe Webhook ➔ GAS ➔ 顧客への自動メール送信 ➔ スプレッドシートへの記録

## 4. ディレクトリ構成
```text
07.photo/
├── app.py             # FastAPI本体・i18nロジック・HTML/JSを内包
├── stripe_handler.py  # Stripe Checkout作成・Webhook（GAS連携）
├── license.py         # ライセンスキー生成ロジック・無料制限チェック
├── database.py        # SQLite3初期化
├── gas_webhook.js     # Google Apps Script用コード（メール送信・DB記録）
├── generate_free_license.py # 管理者が無料でキーを発行するためのツール
├── requirements.txt   # 依存ライブラリ一覧
├── Dockerfile         # Hugging Face用環境構築
└── cleancut.db        # 利用ログ・ライセンスDB
```

## 5. データベース設計（SQLite）
- **usages テーブル**: 無料ユーザーの利用履歴
  - `ip_address`: (TEXT, PRIMARY KEY) IPアドレス
  - `usage_count`: (INTEGER) 当日の利用回数
  - `last_reset`: (TEXT) 最後に利用回数をリセットした日付（YYYY-MM-DD）
- **licenses テーブル**: 有料ユーザーのライセンス情報
  - `license_key`: (TEXT, PRIMARY KEY) ライセンスキー
  - `email`: (TEXT) 顧客のメールアドレス
  - `is_active`: (BOOLEAN) 有効状態（デフォルト: 1）

## 6. 動作環境・デプロイ手順
### 6.1 ローカル開発環境の起動
```bash
# 依存パッケージインストール
pip install -r requirements.txt
# サーバー起動 (http://localhost:8000)
uvicorn app:app --host 0.0.0.0 --port 8000
```
※ Stripeのテスト（Webhook受信）を行う場合は別途 `stripe listen --forward-to localhost:8000/stripe-webhook` を実行。

### 6.2 本番環境（Hugging Face Spaces - Docker）
- OS: `python:3.10-slim`
- 実行ポート: `7860`
- `Dockerfile` により `libgl1` や `libglib2.0-0`（画像処理用システム依存ファイル）を自動インストール
- Stripe連携用の環境変数は Hugging Face の `Settings` > `Variables and secrets` にて登録
  - `STRIPE_SECRET_KEY`
  - `STRIPE_PRICE_ID`
  - `STRIPE_WEBHOOK_SECRET`
