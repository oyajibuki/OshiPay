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

## STEP 3B｜Google Cloud（GCP）でデプロイ（永久無料）

> **e2-micro VM**（us-central1）が永久無料枠。スリープなし・常時起動。

### 3B-1｜GCPアカウント作成
1. https://cloud.google.com → 「無料で開始」
2. クレカ登録（無料枠内は請求なし）
3. 新しいプロジェクトを作成（例: `oshipay-bot`）

### 3B-2｜VM インスタンス作成
1. 左メニュー「Compute Engine」→「VM インスタンス」→「インスタンスを作成」
2. 以下の通り設定：

| 項目 | 値 |
|---|---|
| **名前** | `oshipay-discord-bot` |
| **リージョン** | `us-central1`（無料枠対象） |
| **マシンタイプ** | `e2-micro`（無料枠対象） |
| **ブートディスク** | `Ubuntu 22.04 LTS` / 30GB |
| **ファイアウォール** | HTTP・HTTPS トラフィックを許可 |

3. 「作成」

### 3B-3｜SSH接続してBotをセットアップ
VMの「SSH」ボタンをクリック → ブラウザでターミナルが開く

```bash
# Pythonと必要ツールをインストール
sudo apt update && sudo apt install -y python3-pip git

# リポジトリをクローン
git clone https://github.com/oyajibuki/OshiPay.git
cd OshiPay/discord_bot

# ライブラリをインストール
pip3 install -r requirements.txt

# 環境変数をセット
export DISCORD_BOT_TOKEN="DiscordでコピーしたToken"
export SUPABASE_URL="SupabaseのURL"
export SUPABASE_KEY="SupabaseのAnon Key"
export APP_URL="https://oshipay.me"

# 常時起動設定（systemd）
sudo tee /etc/systemd/system/oshipay-bot.service > /dev/null <<EOF
[Unit]
Description=OshiPay Discord Bot
After=network.target

[Service]
User=$USER
WorkingDirectory=/home/$USER/OshiPay/discord_bot
ExecStart=/usr/bin/python3 bot.py
Restart=always
Environment=DISCORD_BOT_TOKEN=ここにトークン
Environment=SUPABASE_URL=ここにURL
Environment=SUPABASE_KEY=ここにKey
Environment=APP_URL=https://oshipay.me

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable oshipay-bot
sudo systemctl start oshipay-bot

# 起動確認
sudo systemctl status oshipay-bot
```

`Active: active (running)` と表示されれば成功 ✅

### 3B-4｜コードを更新するとき
```bash
cd ~/OshiPay
git pull
sudo systemctl restart oshipay-bot
```

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

**Botが起動しない（GCP）**
→ `sudo systemctl status oshipay-bot` でエラー内容を確認してください。
→ `sudo journalctl -u oshipay-bot -n 50` で直近50行のログを確認できます。

**Botが反応しなくなる（GCP）**
→ `sudo systemctl restart oshipay-bot` で再起動してください。
→ VMが停止していないかGCPコンソールで確認してください。
