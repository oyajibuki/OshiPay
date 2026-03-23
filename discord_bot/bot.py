"""
OshiPay Discord Bot — MVP
==========================
コマンド一覧:
  /setup    acct_id channel  サーバーに紐づくOshiPayクリエイターを設定（管理者専用）
  /oshipay                   応援リンクをボタン付きで表示
  /qr                        応援用QRコードを画像で表示
  /ranking                   応援ランキングをトップ10表示
  /register                  クリエイター登録案内

自動機能:
  - 新しい応援が届くと設定チャンネルに通知（60秒ポーリング）
"""

import os
import json
import io
import asyncio
import qrcode
import discord
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
intents = discord.Intents.default()
client  = discord.Client(intents=intents)
tree    = app_commands.CommandTree(client)

# ── ブランドカラー ─────────────────────────────────────────────
COLOR_PURPLE = 0x8b5cf6
COLOR_ORANGE = 0xf97316
COLOR_GREEN  = 0x22c55e

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

                embed = discord.Embed(
                    title="🎉 新しい応援が届きました！",
                    description=f"**{sup_name}**さんから **¥{amount:,}** の応援が届きました！",
                    color=COLOR_GREEN,
                )
                embed.set_footer(text=f"{creator_name}さんへ / oshipay.me")

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
    await tree.sync()           # スラッシュコマンドを全サーバーに登録
    notify_new_supports.start() # 通知ループ開始
    print(f"✅ Bot起動完了: {client.user} (id: {client.user.id})")
    print(f"   接続サーバー数: {len(client.guilds)}")


client.run(DISCORD_TOKEN)
