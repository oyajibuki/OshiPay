# OshiPay Discord Bot — セットアップガイド

## 必要なもの（全部無料）
- Discordアカウント
- Renderアカウント（https://render.com）
- GitHubアカウント（すでにあり）

---

## STEP 1｜Discordでアプリを作る

1. https://discord.com/developers/applications を開く
2. 右上「New Application」→ 名前「oshipay-bot」→ Create
3. 左メニュー「Bot」→ 「Add Bot」→ Yes
4. 「Reset Token」→ **トークンをコピーして保管**（後で使う）
5. 「Privileged Gateway Intents」は全部OFF のままでOK

---

## STEP 2｜Botをサーバーに招待するURLを作る

1. 左メニュー「OAuth2」→「URL Generator」
2. SCOPESで `bot` と `applications.commands` にチェック
3. BOT PERMISSIONSで `Send Messages` `Embed Links` `Attach Files` にチェック
4. 下に出たURLをコピー → ブラウザで開く → 自分のサーバーに招待

---

## STEP 3｜Renderにデプロイする

1. https://render.com でアカウント作成
2. 「New」→「Web Service」→「Build and deploy from a Git repository」
3. GitHubと連携 → OshiPayリポジトリを選択
4. 設定：
   - **Root Directory**: `discord_bot`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `python bot.py`
5. 「Environment Variables」で以下を設定：

| キー | 値 |
|---|---|
| `DISCORD_BOT_TOKEN` | STEP1でコピーしたトークン |
| `SUPABASE_URL` | SupabaseのURL |
| `SUPABASE_KEY` | SupabaseのAnon Key |
| `APP_URL` | https://oshipay.me |

6. 「Create Web Service」→ デプロイ開始（2〜3分）

---

## STEP 4｜Discordサーバーで設定する

Botが参加したサーバーで：
```
/setup acct_id:usr_あなたのID channel:#通知したいチャンネル
```

これで完了！

---

## コマンド一覧

| コマンド | 説明 | 誰が使える |
|---|---|---|
| `/setup` | クリエイターIDと通知チャンネルを設定 | 管理者のみ |
| `/oshipay` | 応援リンクをボタン付きで表示 | 全員 |
| `/qr` | 応援用QRコードを画像で表示 | 全員 |
| `/ranking` | 応援ランキング Top10 | 全員 |
| `/register` | OshiPayへの登録案内 | 全員 |

自動機能：新しい応援が届くと設定チャンネルに通知されます。

---

## トラブルシューティング

**コマンドが出てこない**
→ Botを追加後、反映に最大1時間かかる場合があります。

**「クリエイターIDが見つかりません」**
→ `oshipay.me` にログインしてダッシュボードのURLにある `acct=usr_xxx` の部分がIDです。

**通知が来ない**
→ BotにそのチャンネルのSend Messages権限があるか確認してください。
