import os
import sqlite3
import asyncio
import time
import random
from pathlib import Path
import discord
from discord.ext import commands
from dotenv import load_dotenv
import aiosqlite

# =========================
# LOAD ENV
# =========================
load_dotenv()
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("TOKEN not found in .env file")

# =========================
# BASIC CONFIG
# =========================
OWNER_IDS = [1376415399360594082, 1043752570243526757, 1504365980032172032]
DEVELOPER_IDS = [1376415399360594082, 1043752570243526757, 1504365980032172032]
DEFAULT_PREFIX = "."

CORE_DB = Path("db/core.db")
PREMIUM_DB = Path("db/premium.db")
TRACKER_DB = Path("db/tracker.db")

# All loadable subdirectories under cogs/
COG_DIRS = {
    Path("cogs/moderation"):  "Moderation",
    Path("cogs/security"):    "Security",
    Path("cogs/automod"):     "Automod",
    Path("cogs/utility"):     "Utility",
    Path("cogs/social"):      "Social",
    Path("cogs/guild"):       "Guild",
    Path("cogs/owner"):       "Owner",
    Path("cogs/events"):      "Events",
}

# =========================
# SHARD CONFIG
# =========================
SHARD_COUNT = 12  # Total shards (adjust between 10-15 as needed)

# =========================
# PREMIUM CONFIG
# =========================
SUPPORT_LINK = "https://discord.gg/AbZ79uzqp"
INVITE_LINK = "https://discord.com/oauth2/authorize?client_id=1424373333142671461"
VOTE_LINK = "https://top.gg/bot/clientid/vote"
SUPPORT_SERVER = SUPPORT_LINK
LOCKED_COGS = ("ChangeAvatar", "ChangeBanner", "ChangeBio")

# =========================
# CUSTOM EMOJIS
# =========================
from emojis import EMOJIES

# =========================
# BOT SETUP (AutoShardedBot)
# =========================
intents = discord.Intents.default()
intents.presences = True
intents.message_content = True
intents.guilds = True
intents.voice_states = True
intents.members = True

async def get_prefix(bot, message):
    if not message or not message.guild:
        return DEFAULT_PREFIX
    async with aiosqlite.connect(CORE_DB) as db:
        async with db.execute("SELECT prefix FROM prefixes WHERE guild_id = ?", (message.guild.id,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else DEFAULT_PREFIX

bot = commands.AutoShardedBot(
    command_prefix=get_prefix,
    shard_count=SHARD_COUNT,
    owner_ids=set(OWNER_IDS),
    intents=intents,
    help_command=None,
    case_insensitive=True
)

# Attach Global Links & Config
bot.support_link = SUPPORT_LINK
bot.invite_link = INVITE_LINK
bot.vote_link = VOTE_LINK
bot.start_time = time.time()

# =========================
# 🔒 GLOBAL PREMIUM LOCK
# =========================
@bot.check
async def premium_global_lock(ctx: commands.Context):
    if not ctx.guild or not ctx.command:
        return True
    if ctx.command.cog_name not in LOCKED_COGS:
        return True

    async with aiosqlite.connect(PREMIUM_DB) as db:
        async with db.execute(
            "SELECT expires FROM premium_guilds WHERE guild_id = ?", (ctx.guild.id,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        await ctx.send(
            f"{EMOJIES['lock']} **Premium Required**\n\n"
            f"{EMOJIES['info']} This command requires an active premium subscription."
        )
        return False

    if row[0] < 9_999_999_999 and row[0] <= time.time():
        await ctx.send(
            f"{EMOJIES['cross']} **Premium Expired**\n\n"
            f"{EMOJIES['cart']} Renew your premium to continue using this feature."
        )
        return False

    return True

# =========================
# DB INITIALIZER
# =========================
async def init_databases():
    Path("db").mkdir(exist_ok=True)

    async with aiosqlite.connect(CORE_DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS prefixes (guild_id INTEGER PRIMARY KEY, prefix TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS devreact (user_id INTEGER, role TEXT, PRIMARY KEY (user_id, role))")
        await db.execute("CREATE TABLE IF NOT EXISTS noprefix (user_id INTEGER PRIMARY KEY, plan TEXT, added_by INTEGER, added_at TEXT, expires TEXT)")
        await db.commit()

    async with aiosqlite.connect(PREMIUM_DB) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS premium_guilds (
                guild_id  INTEGER PRIMARY KEY,
                plan      TEXT,
                added_by  INTEGER,
                expires   INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS trial_used (
                guild_id INTEGER PRIMARY KEY
            )
        """)
        await db.commit()

    async with aiosqlite.connect(TRACKER_DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS messages (guild_id INTEGER, user_id INTEGER, message_count INTEGER DEFAULT 0, daily_count INTEGER DEFAULT 0, PRIMARY KEY (guild_id, user_id))")
        await db.execute("CREATE TABLE IF NOT EXISTS blacklisted_channels (guild_id INTEGER, channel_id INTEGER, PRIMARY KEY (guild_id, channel_id))")
        await db.commit()

# =========================
# PRESENCE ROTATION
# =========================
PRESENCE_CYCLE = [
    # (activity_type, name)
    ("streaming", "Protecting Servers."),
    ("watching",  "over {guilds} servers"),
    ("playing",   "with {members} members"),
    ("streaming", "Zyn The Best"),
    ("watching",  "{members} users"),
    ("listening",   ".help"),
]

async def update_status():
    await bot.wait_until_ready()
    idx = 0
    while not bot.is_closed():
        entry_type, name_template = PRESENCE_CYCLE[idx % len(PRESENCE_CYCLE)]
        guilds  = len(bot.guilds)
        members = sum(g.member_count or 0 for g in bot.guilds)
        name = name_template.format(guilds=guilds, members=members)

        if entry_type == "streaming":
            activity = discord.Streaming(name=name, url="https://twitch.tv/placeholder")
        elif entry_type == "watching":
            activity = discord.Activity(type=discord.ActivityType.watching, name=name)
        else:  # playing
            activity = discord.Game(name=name)

        await bot.change_presence(status=discord.Status.dnd, activity=activity)
        idx += 1
        await asyncio.sleep(random.randint(10, 12))

# =========================
# READY EVENT
# =========================
@bot.event
async def on_ready():
    print("=" * 55)
    print(f"🤖 Logged in as: {bot.user}")
    print(f"🔀 Shards: {bot.shard_count}")
    print(f"📚 Commands Loaded: {len(bot.commands)}")
    print(f"🧩 Cogs Loaded: {len(bot.cogs)}")
    try:
        synced = await bot.tree.sync()
        print(f"✅ Slash Commands Synced: {len(synced)}")
    except Exception as e:
        print(f"❌ Slash Sync Failed: {e}")
    print("🚀 BOT IS FULLY READY")
    print("=" * 55)
    asyncio.create_task(update_status())

@bot.event
async def on_shard_ready(shard_id: int):
    print(f"✅ Shard [{shard_id}] ready")

@bot.event
async def on_shard_connect(shard_id: int):
    print(f"🔗 Shard [{shard_id}] connected")

@bot.event
async def on_shard_disconnect(shard_id: int):
    print(f"⚠️  Shard [{shard_id}] disconnected")

# =========================
# PREFIX COMMANDS
# =========================
@bot.command()
@commands.has_permissions(administrator=True)
async def setprefix(ctx, prefix: str):
    if not prefix or len(prefix) > 10:
        return await ctx.send(f"{EMOJIES['cross']} Prefix must be 1–10 characters")

    async with aiosqlite.connect(CORE_DB) as db:
        await db.execute("INSERT OR REPLACE INTO prefixes (guild_id, prefix) VALUES (?, ?)", (ctx.guild.id, prefix))
        await db.commit()
    await ctx.send(f"{EMOJIES['check']} Prefix set to `{prefix}`")

@bot.command()
@commands.has_permissions(administrator=True)
async def resetprefix(ctx):
    async with aiosqlite.connect(CORE_DB) as db:
        await db.execute("DELETE FROM prefixes WHERE guild_id = ?", (ctx.guild.id,))
        await db.commit()
    await ctx.send(f"{EMOJIES['check']} Prefix reset to `{DEFAULT_PREFIX}`")

# =========================
# LOADERS (VERBOSE)
# =========================
async def load_folder(folder: Path, label: str):
    folder.mkdir(exist_ok=True)
    ok = fail = 0
    for file in folder.glob("*.py"):
        if file.name.startswith("_"):
            continue
        # Build dotted path relative to project root: e.g. cogs.utility.ping
        ext = ".".join(file.with_suffix("").parts)
        try:
            await bot.load_extension(ext)
            print(f"✅ Loaded {label}: {ext}")
            ok += 1
        except Exception as e:
            print(f"❌ Failed {label}: {ext}\n   ↳ {e}")
            fail += 1
    print(f"📦 {label} Loaded: {ok} | Failed: {fail}\n")

async def load_jishaku_ext():
    try:
        await bot.load_extension("jishaku")
        print("✅ Jishaku Loaded (Owner Only)\n")
    except Exception as e:
        print(f"❌ Jishaku Failed: {e}\n")

# =========================
# MAIN
# =========================
async def main():
    await init_databases()
    async with bot:
        for folder, label in COG_DIRS.items():
            await load_folder(folder, label)
        await load_jishaku_ext()
        await bot.start(TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
