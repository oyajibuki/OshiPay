"""
OshiPay Discord Bot — MVP
==========================
コマンド一覧:
  /setup    acct_id channel  サーバーに紐づくOshiPayクリエイターを設定（管理者専用）
  /oshipay                   応援リンクをボタン付きで表示
  /qr                        応援用QRコードを画像で表示
  /ranking                   応援ランキングをトップ10表示
  /register                  クリエイター登録案内
  /ask      question         oshipayについて何でも質問できるAIチャットBot
  /welcome                   #ようこそ チャンネルに歓迎メッセージを投稿（管理者専用）

自動機能:
  - 新しい応援が届くと設定チャンネルに通知（60秒ポーリング）
  - 新規メンバー入室時に歓迎DM＋役割選択ボタン（クリエイター/サポーター）
"""

import os
import json
import io
import asyncio
import qrcode
import discord
from aiohttp import web
from dotenv import load_dotenv
from matcher import find_answer

# .envファイルを自動読み込み
load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
from discord import app_commands
from discord.ext import tasks
from supabase import create_client
from datetime import datetime, timezone

# ── 環境変数 ──────────────────────────────────────────────────
DISCORD_TOKEN = os.environ["DISCORD_BOT_TOKEN"]
SUPABASE_URL  = os.environ["SUPABASE_URL"]
SUPABASE_KEY  = os.environ["SUPABASE_KEY"]        # anon or service_role
BASE_URL      = os.environ.get("APP_URL", "https://oshipay.me").rstrip("/")

# ── Supabase ──────────────────────────────────────────────────
db = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Bot ログ保存 ──────────────────────────────────────────────
async def save_bot_log(question: str, answer: str | None, channel_name: str = "", user_id: str = "", guild_id: str = ""):
    try:
        db.table("bot_logs").insert({
            "question":     question,
            "answer":       answer,
            "answered":     answer is not None,
            "channel_name": channel_name,
            "user_id":      str(user_id),
            "guild_id":     str(guild_id),
        }).execute()
    except Exception as e:
        print(f"[bot_log error] {e}")

# ── サーバー設定（JSONで永続化）────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "server_config.json")

def load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

# ── ヘルパー ──────────────────────────────────────────────────
def get_support_url(slug: str) -> str:
    return f"{BASE_URL}?page=support&creator={slug}"

def get_supporters_map(supporter_ids: list) -> dict:
    if not supporter_ids:
        return {}
    try:
        resp = db.table("supporters").select("supporter_id,display_name").in_("supporter_id", supporter_ids).execute()
        return {r["supporter_id"]: (r.get("display_name") or "匿名") for r in (resp.data or [])}
    except Exception:
        return {}

# ── Discordクライアント設定 ───────────────────────────────────
intents         = discord.Intents.default()
intents.members = True   # on_member_join に必要
client          = discord.Client(intents=intents)
tree            = app_commands.CommandTree(client)

# ── ブランドカラー ─────────────────────────────────────────────
COLOR_PURPLE = 0x8b5cf6
COLOR_ORANGE = 0xf97316
COLOR_GREEN  = 0x22c55e
COLOR_PINK   = 0xff69b4

# ══════════════════════════════════════════════════════════════
# 役割選択ボタン（クリエイター / サポーター）
# ══════════════════════════════════════════════════════════════
ROLE_CREATOR   = "🌸 クリエイター"
ROLE_SUPPORTER = "💜 サポーター"

class RoleSelectView(discord.ui.View):
    """入室時に表示する役割選択ボタン。タイムアウトなしで永続動作する。"""
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🌸 クリエイター（応援を受け取りたい）",
                       style=discord.ButtonStyle.primary,
                       custom_id="role_creator")
    async def btn_creator(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _assign_role(interaction, ROLE_CREATOR)

    @discord.ui.button(label="💜 サポーター（誰かを応援したい）",
                       style=discord.ButtonStyle.secondary,
                       custom_id="role_supporter")
    async def btn_supporter(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _assign_role(interaction, ROLE_SUPPORTER)


async def _assign_role(interaction: discord.Interaction, role_name: str):
    """指定ロールをメンバーに付与する。なければ作成する。"""
    guild  = interaction.guild
    member = interaction.user

    role = discord.utils.get(guild.roles, name=role_name)
    if not role:
        # ロールが存在しない場合は自動作成
        color = discord.Color(0x8b5cf6) if "クリエイター" in role_name else discord.Color(0xa855f7)
        role  = await guild.create_role(name=role_name, color=color)

    if role in member.roles:
        await interaction.response.send_message(
            f"すでに **{role_name}** ロールが付いています！", ephemeral=True
        )
    else:
        await member.add_roles(role)
        msg = (
            f"**{role_name}** ロールを付与しました🎉\n\n"
            + (
                "**#3分で体験** チャンネルで `/qr` を試してみてください！\n"
                "**#よくある質問-bot** で `/ask 登録方法` と聞くと詳しく教えます👇"
                if "クリエイター" in role_name else
                "**#クリエイターqr広場** でQRコードを見つけて応援してみましょう！\n"
                "**#よくある質問-bot** で `/ask oshipayとは` と聞くと詳しく教えます👇"
            )
        )
        await interaction.response.send_message(msg, ephemeral=True)


def _build_welcome_embed() -> discord.Embed:
    embed = discord.Embed(
        title="🌸 oshipay 公式サーバーへようこそ！",
        description=(
            "**oshipay** は推し活専用のチップ・応援金サービスです。\n"
            "QRコード1枚で、ファンからスマホ直接応援を受け取れます。\n\n"
            "━━━━━━━━━━━━━━━━━━━━━\n"
            "**まずあなたはどちら？** 👇\n"
            "ボタンを押してロールを取得してください！"
        ),
        color=COLOR_PURPLE,
    )
    embed.add_field(name="🌸 クリエイター",  value="応援を受け取りたい方",        inline=True)
    embed.add_field(name="💜 サポーター",    value="推しを応援したい方",           inline=True)
    embed.add_field(
        name="📌 使い方",
        value=(
            "`/ask [質問]` — 何でも聞いてね\n"
            "`/qr` — 応援QRコードを表示\n"
            "`/ranking` — 応援ランキング\n"
            "`/register` — クリエイター登録"
        ),
        inline=False,
    )
    embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")
    return embed


# ══════════════════════════════════════════════════════════════
# on_member_join — 新規入室時の歓迎DM
# ══════════════════════════════════════════════════════════════
@client.event
async def on_member_join(member: discord.Member):
    try:
        embed = _build_welcome_embed()
        await member.send(embed=embed, view=RoleSelectView())
    except discord.Forbidden:
        # DM が無効な場合は #ようこそ チャンネルに投稿
        ch = discord.utils.find(
            lambda c: "ようこそ" in c.name or "welcome" in c.name.lower(),
            member.guild.text_channels,
        )
        if ch:
            await ch.send(f"{member.mention} ようこそ！", embed=embed, view=RoleSelectView())


# ══════════════════════════════════════════════════════════════
# /welcome — #ようこそ に歓迎メッセージを手動投稿（管理者専用）
# ══════════════════════════════════════════════════════════════
@tree.command(name="welcome", description="#ようこそ チャンネルに歓迎メッセージを投稿します（管理者専用）")
@app_commands.checks.has_permissions(administrator=True)
async def cmd_welcome(interaction: discord.Interaction):
    embed = _build_welcome_embed()
    await interaction.response.send_message(embed=embed, view=RoleSelectView())


# ══════════════════════════════════════════════════════════════
# /setup — 管理者専用
# ══════════════════════════════════════════════════════════════
@tree.command(name="setup", description="OshiPayの設定をします（管理者専用）")
@app_commands.describe(
    acct_id="OshiPayクリエイターID（例: usr_xxxxxxxxxxxxxxxx）",
    channel="応援通知を送るチャンネル",
)
@app_commands.checks.has_permissions(administrator=True)
async def cmd_setup(
    interaction: discord.Interaction,
    acct_id: str,
    channel: discord.TextChannel,
):
    await interaction.response.defer(ephemeral=True)

    # DBでID確認
    try:
        res = db.table("creators").select("display_name,name,slug,acct_id").eq("acct_id", acct_id.strip()).maybe_single().execute()
    except Exception as e:
        await interaction.followup.send(f"❌ DB接続エラー: {e}", ephemeral=True)
        return

    if not res.data:
        await interaction.followup.send(
            "❌ クリエイターIDが見つかりませんでした。\n"
            f"`oshipay.me` に登録済みの ID を確認してください。",
            ephemeral=True,
        )
        return

    creator_data = res.data
    creator_name = creator_data.get("display_name") or creator_data.get("name") or acct_id
    slug         = creator_data.get("slug") or acct_id

    config = load_config()
    config[str(interaction.guild_id)] = {
        "acct_id":      acct_id.strip(),
        "channel_id":   channel.id,
        "creator_name": creator_name,
        "slug":         slug,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    save_config(config)

    embed = discord.Embed(title="✅ セットアップ完了！", color=COLOR_PURPLE)
    embed.add_field(name="👤 クリエイター", value=creator_name, inline=True)
    embed.add_field(name="📢 通知チャンネル", value=channel.mention, inline=True)
    embed.add_field(
        name="使えるコマンド",
        value="`/oshipay` `/qr` `/ranking` `/register`",
        inline=False,
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# ══════════════════════════════════════════════════════════════
# /oshipay — 応援リンク表示
# ══════════════════════════════════════════════════════════════
@tree.command(name="oshipay", description="推しへの応援リンクを表示します")
async def cmd_oshipay(interaction: discord.Interaction):
    config = load_config()
    cfg    = config.get(str(interaction.guild_id))

    if not cfg:
        await interaction.response.send_message(
            "⚠️ まだ設定されていません。管理者が `/setup` を実行してください。",
            ephemeral=True,
        )
        return

    creator_name = cfg["creator_name"]
    support_url  = get_support_url(cfg["slug"])

    embed = discord.Embed(
        title=f"🌸 {creator_name}さんを応援しよう！",
        description="oshipayを使ってスマホから直接応援できます！",
        color=COLOR_PURPLE,
    )
    embed.add_field(name="💳 支払い方法", value="クレカ / Apple Pay / Google Pay", inline=False)
    embed.add_field(name="💰 還元率",     value=f"応援額の **86.4%** が {creator_name}さんへ直接届きます", inline=False)
    embed.add_field(name="⚡ 手数料",     value="初期費用・月額料金 **0円**", inline=False)
    embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label=f"🌸 {creator_name}さんを応援する",
        url=support_url,
        style=discord.ButtonStyle.link,
    ))
    await interaction.response.send_message(embed=embed, view=view)


# ══════════════════════════════════════════════════════════════
# /qr — QRコード画像送信
# ══════════════════════════════════════════════════════════════
@tree.command(name="qr", description="応援用QRコードを表示します")
async def cmd_qr(interaction: discord.Interaction):
    config = load_config()
    cfg    = config.get(str(interaction.guild_id))

    if not cfg:
        await interaction.response.send_message(
            "⚠️ まだ設定されていません。管理者が `/setup` を実行してください。",
            ephemeral=True,
        )
        return

    await interaction.response.defer()

    creator_name = cfg["creator_name"]
    support_url  = get_support_url(cfg["slug"])

    # QRコード生成（紫×白）
    qr  = qrcode.QRCode(version=1, box_size=12, border=4)
    qr.add_data(support_url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#8b5cf6", back_color="white")

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    file  = discord.File(buf, filename="oshipay_qr.png")
    embed = discord.Embed(
        title=f"📱 {creator_name}さんの応援QRコード",
        description="スマホカメラでスキャン → すぐに応援できます！",
        color=COLOR_PURPLE,
    )
    embed.set_image(url="attachment://oshipay_qr.png")
    embed.set_footer(text=support_url)

    await interaction.followup.send(embed=embed, file=file)


# ══════════════════════════════════════════════════════════════
# /ranking — 応援ランキング Top10
# ══════════════════════════════════════════════════════════════
@tree.command(name="ranking", description="応援ランキング Top10を表示します")
async def cmd_ranking(interaction: discord.Interaction):
    config = load_config()
    cfg    = config.get(str(interaction.guild_id))

    if not cfg:
        await interaction.response.send_message("⚠️ 設定されていません。", ephemeral=True)
        return

    await interaction.response.defer()

    acct_id      = cfg["acct_id"]
    creator_name = cfg["creator_name"]
    support_url  = get_support_url(cfg["slug"])

    try:
        res = (
            db.table("supports")
            .select("amount,supporter_id,created_at")
            .eq("creator_acct", acct_id)
            .order("amount", desc=True)
            .limit(10)
            .execute()
        )
        supports = res.data or []
    except Exception as e:
        await interaction.followup.send(f"❌ データ取得エラー: {e}")
        return

    if not supports:
        embed = discord.Embed(
            title=f"🏆 {creator_name}さんの応援ランキング",
            description="📭 まだ応援がありません。\n**あなたが最初の応援者になろう！**",
            color=COLOR_ORANGE,
        )
        view = discord.ui.View()
        view.add_item(discord.ui.Button(label=f"🌸 最初に応援する", url=support_url, style=discord.ButtonStyle.link))
        await interaction.followup.send(embed=embed, view=view)
        return

    # supporter表示名を一括取得
    sup_ids = [s["supporter_id"] for s in supports if s.get("supporter_id")]
    sup_map = get_supporters_map(sup_ids)

    medals = ["🥇", "🥈", "🥉"] + ["🏅"] * 7
    lines  = []
    for i, s in enumerate(supports):
        name = sup_map.get(s.get("supporter_id", ""), "匿名")
        lines.append(f"{medals[i]} **{name}** — ¥{s['amount']:,}")

    embed = discord.Embed(
        title=f"🏆 {creator_name}さん 応援ランキング",
        description="\n".join(lines),
        color=COLOR_ORANGE,
    )
    embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label=f"🌸 {creator_name}さんを応援する",
        url=support_url,
        style=discord.ButtonStyle.link,
    ))
    await interaction.followup.send(embed=embed, view=view)


# ══════════════════════════════════════════════════════════════
# /register — クリエイター登録案内
# ══════════════════════════════════════════════════════════════
@tree.command(name="register", description="OshiPayにクリエイター登録する方法を案内します")
async def cmd_register(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🌸 OshiPayにクリエイター登録しよう",
        description="QRコードを1枚置くだけで、ファンからスマホで直接応援を受け取れます。",
        color=COLOR_PURPLE,
    )
    embed.add_field(name="✅ 初期費用",  value="完全無料",     inline=True)
    embed.add_field(name="✅ 機器",      value="不要（QRのみ）", inline=True)
    embed.add_field(name="✅ 還元率",    value="86.4%",         inline=True)
    embed.add_field(
        name="📋 登録ステップ",
        value="1️⃣ oshipay.meにアクセス\n2️⃣ 名前・メールを登録\n3️⃣ QRを印刷して置くだけ！",
        inline=False,
    )
    embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")

    view = discord.ui.View()
    view.add_item(discord.ui.Button(
        label="✨ 無料で登録する（5分）",
        url=BASE_URL,
        style=discord.ButtonStyle.link,
    ))
    await interaction.response.send_message(embed=embed, view=view)


# ══════════════════════════════════════════════════════════════
# /ask — Q&Aチャットbot
# ══════════════════════════════════════════════════════════════
@tree.command(name="ask", description="oshipayについて何でも聞いてね！")
@app_commands.describe(question="質問を入力してください（例: 手数料はいくら？）")
async def cmd_ask(interaction: discord.Interaction, question: str):
    answer = find_answer(question)

    if answer:
        embed = discord.Embed(
            title=f"💬 {question}",
            description=answer,
            color=COLOR_PURPLE,
        )
        embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")
        await interaction.response.send_message(embed=embed)
    else:
        embed = discord.Embed(
            title="🤔 うーん、ちょっとわかりませんでした",
            description=(
                f"「**{question}**」についての回答が見つかりませんでした🙏\n\n"
                "以下からお問い合わせください👇\n"
                "・X（旧Twitter）: @oshipay_me\n"
                "・お問い合わせフォーム: https://oshipay.me\n\n"
                "**よく聞かれる質問の例:**\n"
                "`/ask 手数料はいくら？`\n"
                "`/ask 登録方法を教えて`\n"
                "`/ask 入金はいつ？`"
            ),
            color=COLOR_ORANGE,
        )
        await interaction.response.send_message(embed=embed)

    await save_bot_log(
        question=question,
        answer=answer,
        channel_name=interaction.channel.name if interaction.channel else "",
        user_id=interaction.user.id,
        guild_id=interaction.guild_id or "",
    )


# ══════════════════════════════════════════════════════════════
# 自動通知（60秒ポーリング）
# ══════════════════════════════════════════════════════════════
@tasks.loop(seconds=60)
async def notify_new_supports():
    config = load_config()
    updated = False

    for guild_id, cfg in config.items():
        try:
            acct_id      = cfg["acct_id"]
            channel_id   = cfg["channel_id"]
            creator_name = cfg["creator_name"]
            slug         = cfg.get("slug", acct_id)
            last_checked = cfg.get("last_checked", datetime.now(timezone.utc).isoformat())

            # 前回チェック以降の新着応援を取得
            res = (
                db.table("supports")
                .select("*")
                .eq("creator_acct", acct_id)
                .gt("created_at", last_checked)
                .order("created_at")
                .execute()
            )
            new_supports = res.data or []

            if not new_supports:
                continue

            channel = client.get_channel(channel_id)
            if not channel:
                continue

            # supporter名を一括取得
            sup_ids = [s["supporter_id"] for s in new_supports if s.get("supporter_id")]
            sup_map = get_supporters_map(sup_ids)
            support_url = get_support_url(slug)

            for s in new_supports:
                sup_name = sup_map.get(s.get("supporter_id", ""), "匿名")
                amount   = s["amount"]
                msg      = s.get("message", "").strip()
                created  = s.get("created_at", "")[:16].replace("T", " ")

                embed = discord.Embed(
                    title="🎉 新しい応援が届きました！",
                    color=0xFFD700,  # ゴールド
                )
                embed.add_field(name="👤 サポーター", value=f"**{sup_name}** さん", inline=True)
                embed.add_field(name="💰 応援金額",   value=f"**¥{amount:,}**", inline=True)
                embed.add_field(name="📅 日時",       value=created, inline=True)
                if msg:
                    embed.add_field(name="💬 メッセージ", value=f"_{msg}_", inline=False)
                embed.set_footer(text=f"🌸 {creator_name}さんへ届きました | oshipay.me")

                view = discord.ui.View()
                view.add_item(discord.ui.Button(
                    label=f"🌸 {creator_name}さんを応援する",
                    url=support_url,
                    style=discord.ButtonStyle.link,
                ))
                await channel.send(embed=embed, view=view)

            # last_checked を最新に更新
            config[guild_id]["last_checked"] = new_supports[-1]["created_at"]
            updated = True

        except Exception as e:
            print(f"[notify] guild={guild_id} error: {e}")

    if updated:
        save_config(config)


# ══════════════════════════════════════════════════════════════
# /setup_server  チャンネル・カテゴリを自動作成
# ══════════════════════════════════════════════════════════════
SERVER_STRUCTURE = [
    {
        "category": "📌 情報",
        "channels": [
            ("ルールと利用規約",   "必ずお読みください。サーバーのルールと利用規約を掲載しています 📋"),
            ("ようこそ",          "OshiPayへようこそ！🌸 推しへの応援をもっと身近に。まずここを読んでください"),
            ("お知らせ",          "機能アップデート・キャンペーン・重要情報を投稿します 📣"),
        ]
    },
    {
        "category": "🎮 体験する",
        "channels": [
            ("3分で体験",          "/oshipay や /qr コマンドを試してみよう！3分でoshipayを体験できます ⚡"),
            ("よくある質問-bot",   "/ask コマンドで何でも聞いてください。例: /ask 手数料はいくら？ 💬"),
            ("登録してみた",       "oshipayに登録したら報告してください！みんなで応援し合おう 🎉"),
        ]
    },
    {
        "category": "🌟 活用事例",
        "channels": [
            ("みんなの活用事例",   "クリエイターや店舗のリアルな活用シーンをシェアしよう 🌟"),
        ]
    },
    {
        "category": "💜 ファンコミュニティ",
        "channels": [
            ("クリエイターqr広場", "クリエイターの方は /qr で応援QRを投稿しよう！サポーターはここからスキャン 🌸"),
            ("サポーターメダル自慢", "/ranking でもらったメダルを自慢しよう 🏅"),
            ("応援の場",           "クリエイターとサポーターが交流する場所です 💜 応援メッセージもどうぞ"),
            ("推し語り",           "推しについて自由に語ろう！ジャンル不問・全力オタクトークOK 🔥"),
        ]
    },
    {
        "category": "🏪 導入・相談",
        "channels": [
            ("導入相談",           "大量導入・法人でのご利用をご検討の方はこちらへ。まずはお気軽にご相談ください 📩"),
        ]
    },
]


@tree.command(name="setup_server", description="OshiPay用のチャンネル構成を自動作成します（管理者専用）")
@app_commands.checks.has_permissions(administrator=True)
async def cmd_setup_server(interaction: discord.Interaction):
    await interaction.response.send_message("⏳ チャンネルを作成中です...", ephemeral=True)
    guild = interaction.guild
    created = []
    skipped = []

    existing_names = {c.name for c in guild.channels}

    for section in SERVER_STRUCTURE:
        cat_name = section["category"]
        cat = discord.utils.get(guild.categories, name=cat_name)
        if cat is None:
            cat = await guild.create_category(cat_name)
            created.append(f"📁 {cat_name}")

        for ch_name, topic in section["channels"]:
            if ch_name in existing_names:
                skipped.append(f"#{ch_name}")
            else:
                await guild.create_text_channel(ch_name, category=cat, topic=topic)
                created.append(f"#{ch_name}")

    result = ""
    if created:
        result += "✅ **作成しました:**\n" + "\n".join(f"　{c}" for c in created) + "\n"
    if skipped:
        result += "\n⏭ **スキップ（既存）:**\n" + "\n".join(f"　{c}" for c in skipped)

    await interaction.followup.send(result or "変更なし", ephemeral=True)


@cmd_setup_server.error
async def setup_server_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 管理者権限が必要です。", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ エラー: {error}", ephemeral=True)


# ══════════════════════════════════════════════════════════════
# /post_intros  全チャンネルに紹介文を一括投稿（管理者専用）
# ══════════════════════════════════════════════════════════════
CHANNEL_INTROS = {
    "お知らせ": "📣 **OshiPay からのお知らせ**\n\n新機能・キャンペーン・メンテナンス情報などをここに投稿します。\n通知をONにしておくと見逃しません🔔\n\noshipay.me — その感動、今すぐカタチに。",
    "3分で体験": "🎮 **3分でOshiPayを体験してみよう！**\n\n① `/qr` と入力 → あなたの応援QRコードが表示されます\n② QRをスキャン → スマホから応援できます\n③ `/oshipay` → 応援リンクをシェアできます\n\nまずはやってみるのが一番早い！気軽に試してください🚀",
    "よくある質問-bot": "💬 **OshiPayについて何でも聞いてください！**\n\n👇 こんな感じで質問できます\n　`/ask 手数料はいくら？`\n　`/ask 登録方法を教えて`\n　`/ask 入金はいつ？`\n\nBotが即答します。答えられない場合は #導入相談 へどうぞ🙏",
    "登録してみた": "🌸 **登録・体験の報告はこちらへ！**\n\nOshiPayに登録してみた感想、使ってみた感想をぜひシェアしてください。\nはじめての応援を送った・受け取った報告も大歓迎です🎉\n\nみんなの体験談が新しいユーザーの背中を押します💜",
    "みんなの活用事例": "🌟 **リアルな活用シーンをシェアしよう！**\n\n・ライブ会場でQRを使ってみた\n・推しへの応援に使ってみた\n・こんな場面で役に立った\n\n写真・スクリーンショットも歓迎です📸\n使い方のアイデアをみんなで広げましょう！",
    "クリエイターqr広場": "🌸 **クリエイターの方はここにQRをシェアしよう！**\n\n`/qr` コマンドを使うとQRコードが表示されます。\nそのままここに投稿すれば、サポーターに見てもらえます。\n\n📌 投稿フォーマット（任意）\n名前：〇〇\n活動：（ライブ / 配信 / イラスト など）\nひとこと：",
    "サポーターメダル自慢": "💜 **応援バッジ・ランキングを自慢しよう！**\n\n`/ranking` でランキングが表示されます。\n上位に入ったらぜひここでシェアしてください🏆\n\n推しへの応援をみんなに見せよう！",
    "応援の場": "🔥 **クリエイター × サポーターの交流スペース**\n\n応援メッセージ、感謝の言葉、推し活報告など\nクリエイターとサポーターが自由に話せる場所です。\n\n推しへの愛を遠慮なく語ってください💜",
    "推し語り": "💬 **推しについて自由に語ろう！**\n\nジャンル問わず「推し」について語れるチャンネルです。\nVTuber・アイドル・バンド・配信者・クリエイターなど何でもOK🎵\n\nOshiPayユーザーの推し活仲間と繋がろう！",
    "導入相談": "🏪 **大量導入・法人でのご利用をお考えの方へ**\n\nOshiPayを複数店舗・イベント・組織で活用したい方の相談窓口です。\nお気軽にここに書き込んでください。担当者が対応します。\n\n📩 個別対応ご希望の方：oshipay.me@gmail.com\n🌐 公式サイト：https://oshipay.me",
}

@tree.command(name="post_intros", description="全チャンネルに紹介文を一括投稿します（管理者専用）")
@app_commands.checks.has_permissions(administrator=True)
async def cmd_post_intros(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    guild = interaction.guild
    posted, skipped = [], []
    for channel in guild.text_channels:
        intro = CHANNEL_INTROS.get(channel.name)
        if intro:
            try:
                await channel.send(intro)
                posted.append(f"✅ #{channel.name}")
            except Exception as e:
                skipped.append(f"❌ #{channel.name}（{e}）")
        else:
            skipped.append(f"⏭️ #{channel.name}（定義なし）")
    result = "\n".join(posted + skipped)
    await interaction.followup.send(f"**投稿完了！**\n{result}", ephemeral=True)

@cmd_post_intros.error
async def post_intros_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 管理者権限が必要です。", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ エラー: {error}", ephemeral=True)


# ══════════════════════════════════════════════════════════════
# /howto — 3ステップ使い方ガイド
# ══════════════════════════════════════════════════════════════
@tree.command(name="howto", description="oshipayの使い方を3ステップで表示します")
async def cmd_howto(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🚀 oshipayの使い方 — 3ステップ",
        color=COLOR_PINK,
    )
    embed.add_field(
        name="1️⃣ クリエイター登録（5分）",
        value="oshipay.me にアクセス → 名前・メール・パスワードを入力\nQRコードが即発行されます！",
        inline=False,
    )
    embed.add_field(
        name="2️⃣ QRコードを設置",
        value="ダウンロードして名刺・POPに印刷\nSNSプロフに応援URLを貼るだけでもOK📱",
        inline=False,
    )
    embed.add_field(
        name="3️⃣ ファンが応援",
        value="QRスキャン → 金額選択 → クレカ/Apple Pay/Google Payで決済\n**2営業日後に銀行口座へ自動振込** 💰",
        inline=False,
    )
    embed.set_footer(text="初期費用・月額料金 0円 / 手数料13.6%のみ | oshipay.me")
    view = discord.ui.View()
    view.add_item(discord.ui.Button(label="🌸 今すぐ登録する", url=f"{BASE_URL}", style=discord.ButtonStyle.link))
    await interaction.response.send_message(embed=embed, view=view)


# ══════════════════════════════════════════════════════════════
# /fee — 手数料詳細
# ══════════════════════════════════════════════════════════════
@tree.command(name="fee", description="oshipayの手数料を詳しく表示します")
async def cmd_fee(interaction: discord.Interaction):
    embed = discord.Embed(
        title="💰 oshipay 手数料のしくみ",
        color=COLOR_GREEN,
    )
    embed.add_field(name="合計手数料", value="**13.6%**", inline=True)
    embed.add_field(name="クリエイターへの還元率", value="**86.4%**", inline=True)
    embed.add_field(name="月額・初期費用", value="**0円**", inline=True)
    embed.add_field(
        name="内訳",
        value="Stripe決済手数料 **3.6%** ＋ oshipayシステム料 **10%**",
        inline=False,
    )
    embed.add_field(
        name="金額例",
        value=(
            "¥500の応援 → **¥432** 受け取り\n"
            "¥1,000の応援 → **¥864** 受け取り\n"
            "¥3,000の応援 → **¥2,592** 受け取り"
        ),
        inline=False,
    )
    embed.add_field(
        name="競合比較",
        value="SuperChat: 30〜50% / oshipay: **13.6%**（業界最安水準）",
        inline=False,
    )
    embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════════════════════
# /contact — お問い合わせ先
# ══════════════════════════════════════════════════════════════
@tree.command(name="contact", description="oshipayへのお問い合わせ先を表示します")
async def cmd_contact(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📬 お問い合わせ",
        description="お気軽にご連絡ください！",
        color=COLOR_PURPLE,
    )
    embed.add_field(name="📧 メール", value="oshipay.me@gmail.com", inline=False)
    embed.add_field(name="🐦 X（旧Twitter）", value="@oshipay_me へDM", inline=False)
    embed.add_field(name="💬 Discord", value="#導入相談 チャンネルへ", inline=False)
    embed.add_field(name="🌐 公式サイト", value="https://oshipay.me", inline=False)
    embed.set_footer(text="通常1〜2営業日以内にご返信します")
    await interaction.response.send_message(embed=embed)


# ══════════════════════════════════════════════════════════════
# B. #よくある質問-bot チャンネルでメッセージに自動応答
# ══════════════════════════════════════════════════════════════
@client.event
async def on_message(message: discord.Message):
    # Bot自身のメッセージは無視
    if message.author.bot:
        return
    # #よくある質問-bot チャンネルのみ反応
    if "よくある質問" not in message.channel.name and "faq" not in message.channel.name.lower():
        return
    # スラッシュコマンドは無視
    if message.content.startswith("/"):
        return
    question = message.content.strip()
    if not question:
        return
    answer = find_answer(question)
    embed = discord.Embed(
        title=f"💬 {question[:50]}{'...' if len(question) > 50 else ''}",
        description=answer,
        color=COLOR_PINK,
    )
    embed.set_footer(text="oshipay.me — その感動、今すぐカタチに。")
    await message.reply(embed=embed)

    await save_bot_log(
        question=question,
        answer=answer,
        channel_name=message.channel.name,
        user_id=message.author.id,
        guild_id=message.guild.id if message.guild else "",
    )


# ══════════════════════════════════════════════════════════════
# エラーハンドリング
# ══════════════════════════════════════════════════════════════
@cmd_setup.error
async def setup_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 管理者権限が必要です。", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ エラー: {error}", ephemeral=True)


# ══════════════════════════════════════════════════════════════
# 起動
# ══════════════════════════════════════════════════════════════
@client.event
async def on_ready():
    client.add_view(RoleSelectView())   # ボタンをBot再起動後も有効化（永続View）
    # ギルドごとに即時同期（copy_global_to_guildでコマンドをコピーしてから同期）
    for guild in client.guilds:
        tree.copy_global_to(guild=guild)
        await tree.sync(guild=guild)
        print(f"   ✅ スラッシュコマンド同期完了: {guild.name}")
    notify_new_supports.start()         # 通知ループ開始
    print(f"✅ Bot起動完了: {client.user} (id: {client.user.id})")
    print(f"   接続サーバー数: {len(client.guilds)}")


# ══════════════════════════════════════════════════════════════
# ヘルスチェック HTTP サーバー（Render Web Service 対応）
# ══════════════════════════════════════════════════════════════
async def health_check(request):
    return web.Response(text="OK")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", health_check)
    app.router.add_get("/health", health_check)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    print(f"✅ ヘルスチェックサーバー起動: port {port}")

async def main():
    await start_web_server()
    await client.start(DISCORD_TOKEN)

asyncio.run(main())
