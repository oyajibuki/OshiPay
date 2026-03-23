# OshiPay Discord Bot — セットアップガイド

## 必要なもの
- Discordアカウント
- GitHubアカウント（すでにあり）
- Pythonがインストール済みのPC（ローカル実行の場合）

---

## STEP 1｜Discordでアプリを作る

1. https://discord.com/developers/applications を開く
2. 右上「New Application」→ 名前「oshipay-bot」→ Create
3. 左メニュー「Bot」
4. 「Reset Token」→ **トークンをコピーして保管**（後で使う）
5. 「Privileged Gateway Intents」は全部OFF のままでOK
6. 「変更を保存」を押す

---

## STEP 2｜Botをサーバーに招待するURLを作る

1. 左メニュー「OAuth2」→「URL Generator」
2. SCOPESで `bot` と `applications.commands` にチェック
3. BOT PERMISSIONSで以下4つにチェック：
   - `メッセージを送る`（Send Messages）
   - `リンクを埋め込み`（Embed Links）
   - `ファイルを添付`（Attach Files）
   - `スラッシュコマンドを使用`（Use Slash Commands）
4. 下に出たURLをコピー → ブラウザで開く → 自分のサーバーに招待

---

## STEP 3A｜ローカルPC で動かす（無料・テスト向け）

```powershell
# discord_botフォルダに移動
cd C:\Users\User\Desktop\my-sideprojects\42.OshiPay\discord_bot

# ライブラリをインストール
pip install -r requirements.txt

# 環境変数をセット（PowerShell）
$env:DISCORD_BOT_TOKEN="DiscordでコピーしたToken"
$env:SUPABASE_URL="SupabaseのURL"
$env:SUPABASE_KEY="SupabaseのAnon Key"
$env:APP_URL="https://oshipay.me"

# 起動
python bot.py
```

`✅ Bot起動完了` と表示されれば成功。PC起動中のみ動作します。

---

## STEP 3B｜Railway でデプロイ（本番・月ほぼ無料）

> Railway は月$5の無料クレジットあり。小規模Botなら実質$0〜0.5/月。

1. https://railway.app でGitHubログイン
2. 「New Project」→「Deploy from GitHub repo」
3. OshiPayリポジトリを選択
4. 「Add variables」で環境変数を設定：

| キー | 値 |
|---|---|
| `DISCORD_BOT_TOKEN` | STEP1でコピーしたトークン |
| `SUPABASE_URL` | SupabaseのURL |
| `SUPABASE_KEY` | SupabaseのAnon Key |
| `APP_URL` | https://oshipay.me |

5. Settings → 「Root Directory」を `discord_bot` に設定
6. 「Start Command」を `python bot.py` に設定
7. デプロイ開始（2〜3分）

> ⚠️ Render を使う場合は「**Background Worker**」を選択（Web Serviceは不可）。
> ただしRenderのBackground Workerは無料枠なし（$7/月〜）のためRailway推奨。

---

## STEP 4｜Discordサーバーで設定する

Botが参加したサーバーで：
```
/setup acct_id:usr_あなたのID channel:#general
```

`channel:` の部分は入力するとチャンネル一覧が出るので選ぶだけ。

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

自動機能：新しい応援が届くと設定チャンネルに60秒以内に通知されます。

---

## トラブルシューティング

**コマンドが出てこない**
→ Botを追加後、反映に最大1時間かかる場合があります。

**「クリエイターIDが見つかりません」**
→ `oshipay.me` にログインしてダッシュボードのURLにある `acct=usr_xxx` の部分がIDです。

**通知が来ない**
→ BotにそのチャンネルのSend Messages権限があるか確認してください。

**Exited with status 1 エラー（Render）**
→ Web ServiceではなくBackground Workerで作成してください。またはRailleyを使用してください。
