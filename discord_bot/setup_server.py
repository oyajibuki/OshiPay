"""
OshiPay Discord サーバー自動セットアップ
========================================
実行すると既存チャンネルを削除して
推し活部屋 × OshiPay の構成に作り直します。

実行方法:
  python setup_server.py
"""

import asyncio
import os
import discord
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

TOKEN    = os.environ["DISCORD_BOT_TOKEN"]
GUILD_ID = 1455927221767110731

# ══════════════════════════════════════════════════════════════
# チャンネル構成定義
# ══════════════════════════════════════════════════════════════
STRUCTURE = [
    {
        "category": "📌 情報",
        "channels": [
            {
                "name": "ようこそ",
                "topic": "👋 推し活部屋へようこそ！まずここを読んでね",
                "message": """👋 **推し活部屋 × OshiPay** へようこそ！

ここは推し活好きが集まって
推しへの愛を語り合う場所です🔥

━━━━━━━━━━━━━━━
**このサーバーでできること**

❤️ 推しを紹介する
🗣️ 推し語りを聞いてもらう
🎪 グッズ・ライブ情報をシェアする
💬 同じ推し活仲間と交流する
━━━━━━━━━━━━━━━

まずは <#自己紹介> で推しを教えてください！

なにか質問があれば
**#よくある質問-bot** で `/ask` と入力すると
Botが答えてくれます💬"""
            },
            {
                "name": "ルールと利用規約",
                "topic": "📋 楽しく使うためのルール",
                "message": """📋 **楽しく使うためのルール**

━━━━━━━━━━━━━━━
① 推しへのリスペクトを忘れずに
　他の人の推しを否定しない

② 荒らし・誹謗中傷は即BAN

③ 宣伝・勧誘は #導入相談 へ

④ 年齢・性別・ジャンル関係なく仲良く

⑤ 楽しむこと！
━━━━━━━━━━━━━━━

ルールを守って推し活を楽しみましょう🔥"""
            },
            {
                "name": "お知らせ",
                "topic": "📣 運営からの最新情報はここ",
                "message": """📣 **運営からの最新情報をここに投稿します**

新機能・イベント・キャンペーン情報など
見逃さないようにこのチャンネルをフォローしてね！"""
            },
        ]
    },
    {
        "category": "🔥 推し活を語る",
        "channels": [
            {
                "name": "自己紹介",
                "topic": "👤 推しと一緒に自己紹介しよう！",
                "message": """👤 **まずは自己紹介してください！**

以下をコピペして使ってね👇

━━━━━━━━━━━━━━━
【名前/ニックネーム】
【推し】
【推し歴】
【推し活の楽しみ方】
【一言】
━━━━━━━━━━━━━━━

気軽に投稿してください🙌"""
            },
            {
                "name": "推し紹介",
                "topic": "❤️ あなたの推しを教えて！",
                "message": """❤️ **あなたの推しを紹介してください！**

推しの名前・活動ジャンル・好きな理由など
自由に書いてOKです！

画像・動画もどんどん貼って🔥"""
            },
            {
                "name": "推し語り放題",
                "topic": "🗣️ 語りたいことを全部ここに",
                "message": """🗣️ **語りたいことを全部ここに！**

「今日のライブ最高だった」
「新曲聴いた？」
「グッズ買っちゃった」

なんでもOKです。
全力で語ってください🔥"""
            },
            {
                "name": "推しのここが好き",
                "topic": "💘 好きなところを語り尽くそう",
                "message": """💘 **推しの好きなところを語り尽くそう**

ビジュアル・声・ダンス・人柄・発言…
どんな些細なことでもOK！

「わかる！」って共感してもらえるはず🥹"""
            },
            {
                "name": "グッズ・ライブ情報",
                "topic": "🎪 グッズ・ライブ・イベント情報をシェア",
                "message": """🎪 **グッズ・ライブ・イベント情報をシェアしよう！**

新グッズ情報・ライブレポ・イベント告知など
推し活仲間に教えてあげてください📣

※宣伝・転売目的の投稿はNG"""
            },
        ]
    },
    {
        "category": "💬 交流",
        "channels": [
            {
                "name": "雑談",
                "topic": "☕ 推し活以外も何でも話そう",
                "message": """☕ **推し活以外も何でも話そう**

疲れた・今日あったこと・天気の話でもOK
気軽に話しかけてください😊"""
            },
            {
                "name": "登録してみた",
                "topic": "✨ OshiPay使ってみた人はこちら",
                "message": """✨ **OshiPay使ってみた人はこちら！**

登録した感想・QRコードのシェアなど
ぜひ投稿してください🙌

まだの人はこちら→ https://oshipay.me"""
            },
        ]
    },
    {
        "category": "🎁 OshiPayを使う",
        "channels": [
            {
                "name": "OshiPayって何",
                "topic": "💡 OshiPayの説明はここ",
                "message": """💡 **OshiPayとは？**

世界中のファンから応援（投げ銭）を
受け取れるサービスです🌍

━━━━━━━━━━━━━━━
✅ 登録・月額0円
✅ メアド登録だけで30秒でQR発行
✅ 海外ファンからも受け取れる
✅ 手数料13.6%（業界最安水準）
━━━━━━━━━━━━━━━

詳しくは → https://oshipay.me
質問は **#よくある質問-bot** へ💬"""
            },
            {
                "name": "よくある質問-bot",
                "topic": "💬 /askで何でも質問できます",
                "message": """💬 **OshiPayについて何でも聞いてください！**

👇 こんな感じで質問できます
`/ask 手数料はいくらですか？`
`/ask 海外から受け取れますか？`
`/ask 登録方法を教えて`

24時間いつでも即答します⚡"""
            },
            {
                "name": "クリエイターqr広場",
                "topic": "📲 QRコードをシェアしよう",
                "message": """📲 **あなたのQRコードをシェアしよう！**

OshiPayに登録したクリエイターの方は
ここにQRコードを貼ってください🔥

お互いに応援し合いましょう！"""
            },
            {
                "name": "導入相談",
                "topic": "🤝 使い方相談はここへ",
                "message": """🤝 **OshiPayの使い方・導入相談はここへ**

「自分に向いてる？」
「設定がわからない」
「Stripeってなに？」

なんでも相談してください。
運営が直接対応します💬"""
            },
        ]
    },
]

# ══════════════════════════════════════════════════════════════
# セットアップ処理
# ══════════════════════════════════════════════════════════════
async def setup():
    intents = discord.Intents.default()
    client  = discord.Client(intents=intents)

    @client.event
    async def on_ready():
        print(f"✅ ログイン: {client.user}")
        guild = client.get_guild(GUILD_ID)
        if not guild:
            print("❌ サーバーが見つかりません")
            await client.close()
            return

        # 既存チャンネル・カテゴリを全削除
        print("🗑️  既存チャンネルを削除中...")
        for channel in guild.channels:
            try:
                await channel.delete()
                print(f"   削除: {channel.name}")
            except Exception as e:
                print(f"   削除失敗: {channel.name} - {e}")

        # 新しい構成で作成
        for cat_data in STRUCTURE:
            print(f"\n📁 カテゴリ作成: {cat_data['category']}")
            category = await guild.create_category(cat_data["category"])

            for ch_data in cat_data["channels"]:
                print(f"   📝 チャンネル作成: #{ch_data['name']}")
                channel = await guild.create_text_channel(
                    name    = ch_data["name"],
                    topic   = ch_data["topic"],
                    category= category,
                )
                await channel.send(ch_data["message"])

        print("\n🎉 セットアップ完了！")
        await client.close()

    await client.start(TOKEN)

asyncio.run(setup())
