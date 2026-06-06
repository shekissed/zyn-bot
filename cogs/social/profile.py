import discord
import aiosqlite
import os
import re
import sys
import io
import asyncio
import traceback
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from discord.ext import commands

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import CHECK, CROSS, INFO

DB_PATH = "db/profile.db"

VALID_IMAGE_REGEX = re.compile(
    r'^https?://.+\.(png|jpg|jpeg|gif|webp)(\?.*)?$', re.IGNORECASE
)
SOCIAL_KEYS = ["instagram", "twitter", "youtube", "tiktok", "twitch", "github"]
_executor = ThreadPoolExecutor(max_workers=4)


# ── Database ────────────────────────────────────────────────────────────────

async def init_db():
    os.makedirs("db", exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profiles (
                user_id     INTEGER PRIMARY KEY,
                description TEXT    DEFAULT NULL,
                background  TEXT    DEFAULT NULL,
                noprefix    INTEGER DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS profile_socials (
                user_id  INTEGER,
                platform TEXT,
                link     TEXT,
                PRIMARY KEY (user_id, platform)
            )
        """)
        # Migration: add columns that may not exist in older DB versions
        for col, definition in [
            ("noprefix", "INTEGER DEFAULT 0"),
            ("background", "TEXT DEFAULT NULL"),
        ]:
            try:
                await db.execute(f"ALTER TABLE profiles ADD COLUMN {col} {definition}")
            except Exception:
                pass  # Column already exists
        await db.commit()


async def get_profile(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT description, background, noprefix FROM profiles WHERE user_id = ?",
            (user_id,)
        ) as cur:
            row = await cur.fetchone()
        socials = {}
        async with db.execute(
            "SELECT platform, link FROM profile_socials WHERE user_id = ?",
            (user_id,)
        ) as cur:
            async for platform, link in cur:
                socials[platform] = link
    if row:
        return {"description": row[0], "background": row[1], "noprefix": bool(row[2]), "socials": socials}
    return {"description": None, "background": None, "noprefix": False, "socials": {}}


async def ensure_profile(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO profiles (user_id) VALUES (?)", (user_id,))
        await db.commit()


# ── Helpers ──────────────────────────────────────────────────────────────────

async def fetch_bytes(url: str) -> bytes:
    try:
        import aiohttp
        async with aiohttp.ClientSession() as s:
            async with s.get(url, timeout=aiohttp.ClientTimeout(total=15)) as r:
                r.raise_for_status()
                return await r.read()
    except ImportError:
        import urllib.request
        with urllib.request.urlopen(url, timeout=15) as r:
            return r.read()


def _get_status_str(member: discord.Member) -> str:
    s = str(member.status)
    return s if s in ("online", "idle", "dnd", "offline") else "offline"


def _get_clan_tag(member: discord.Member):
    try:
        clan = getattr(member, "clan", None)
        if clan:
            return clan.tag
    except Exception:
        pass
    return None


def _render_sync(av_bytes, display_name, username, clan_tag, status, joined, bg_bytes):
    from card_generator import make_profile_card
    return make_profile_card(
        avatar_bytes=av_bytes,
        display_name=display_name,
        username=username,
        clan_tag=clan_tag,
        status=status,
        joined_date=joined,
        background_bytes=bg_bytes,
    )


# ── Core send function used by both view and card ────────────────────────────

async def _send_profile(ctx: commands.Context, target: discord.Member, show_embed: bool):
    """Generate and send the profile card. show_embed=True adds the info embed."""
    print(f"[profile] _send_profile called for {target} embed={show_embed}")

    # 1. Load profile from DB
    try:
        prof = await get_profile(target.id)
        print(f"[profile] got profile: {prof}")
    except Exception as e:
        print(f"[profile] DB error: {e}")
        traceback.print_exc()
        return await ctx.send(f"{CROSS} Database error: `{e}`")

    # 2. Fetch avatar
    try:
        av_url = target.display_avatar.replace(format="png", size=512).url
        print(f"[profile] fetching avatar: {av_url}")
        av_bytes = await fetch_bytes(av_url)
        print(f"[profile] avatar fetched: {len(av_bytes)} bytes")
    except Exception as e:
        print(f"[profile] avatar fetch error: {e}")
        traceback.print_exc()
        return await ctx.send(f"{CROSS} Could not fetch avatar: `{e}`")

    # 3. Optional background
    bg_bytes = None
    if prof["background"]:
        try:
            bg_bytes = await fetch_bytes(prof["background"])
            print(f"[profile] background fetched: {len(bg_bytes)} bytes")
        except Exception as e:
            print(f"[profile] background fetch failed (ignored): {e}")

    # 4. Gather discord data
    clan_tag = _get_clan_tag(target)
    status   = _get_status_str(target)
    joined   = target.created_at.strftime("%b %d, %Y")
    print(f"[profile] clan={clan_tag} status={status} joined={joined}")

    # 5. Render card in thread
    try:
        loop = asyncio.get_running_loop()
        card_bytes = await loop.run_in_executor(
            _executor, _render_sync,
            av_bytes, target.display_name, str(target),
            clan_tag, status, joined, bg_bytes,
        )
        print(f"[profile] card rendered: {len(card_bytes)} bytes")
    except Exception as e:
        print(f"[profile] render error: {e}")
        traceback.print_exc()
        return await ctx.send(f"{CROSS} Card render failed: `{e}`")

    # 6. Send
    try:
        file = discord.File(io.BytesIO(card_bytes), filename="profile.png")

        if not show_embed:
            await ctx.send(file=file)
            print("[profile] card-only sent")
            return

        # NoPrefix: show a toggle-style indicator matching the reference (off = grey toggle)
        noprefix_display = (
            "<:Enabled:1509858724226007101>" if prof["noprefix"]
            else "<:toggle_off:1509859361638322307>"
        )

        # Social links
        if prof["socials"]:
            links = "\n".join(f"**{k.capitalize()}:** {v}" for k, v in prof["socials"].items())
        else:
            links = "No social media links set."

        # Description — italic None if unset
        description_value = prof["description"] if prof["description"] else "*None*"

        embed = discord.Embed(color=0x000000)
        # Card image sits at the top of the embed
        embed.set_image(url="attachment://profile.png")

        # Row 1: User
        embed.add_field(name="**User**", value=f"{target}", inline=False)
        # Row 2: NoPrefix
        embed.add_field(name="**NoPrefix**", value=noprefix_display, inline=False)
        # Row 3: Social links (no header label, just value)
        embed.add_field(name="**Social Links**", value=links, inline=False)
        # Row 4: Description / None (no header label)
        embed.add_field(name="**Description**", value=description_value, inline=False)

        await ctx.send(file=file, embed=embed)
        print("[profile] card+embed sent")
    except Exception as e:
        print(f"[profile] send error: {e}")
        traceback.print_exc()
        await ctx.send(f"{CROSS} Failed to send: `{e}`")


# ── Cog ──────────────────────────────────────────────────────────────────────

class ProfileCog(commands.Cog, name="Profile"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.loop.create_task(init_db())

    @commands.group(name="profile", aliases=["pr"], invoke_without_command=True)
    async def profile(self, ctx: commands.Context, *, member: discord.Member = None):
        """View your profile card + info."""
        target = member or ctx.author
        await _send_profile(ctx, target, show_embed=True)

    @profile.command(name="view")
    async def profile_view(self, ctx: commands.Context, *, member: discord.Member = None):
        """View profile card + full info embed."""
        target = member or ctx.author
        await _send_profile(ctx, target, show_embed=True)

    @profile.command(name="card")
    async def profile_card(self, ctx: commands.Context, *, member: discord.Member = None):
        """View just the profile card image."""
        target = member or ctx.author
        await _send_profile(ctx, target, show_embed=False)

    # ── profile description ───────────────────────────────────────────────────

    @profile.command(name="description", aliases=["desc", "bio"])
    async def profile_description(self, ctx: commands.Context, *, text: str = None):
        """Set your profile bio. Leave blank to clear."""
        await ensure_profile(ctx.author.id)
        if text and len(text) > 200:
            return await ctx.send(f"{CROSS} Description must be under **200 characters**.")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE profiles SET description = ? WHERE user_id = ?", (text, ctx.author.id)
            )
            await db.commit()
        await ctx.send(f"{CHECK} Description {'updated' if text else 'cleared'}.")

    # ── profile background ────────────────────────────────────────────────────

    @profile.command(name="background", aliases=["bg"])
    async def profile_background(self, ctx: commands.Context, *, image_url: str = None):
        """Set your card background image URL."""
        await ensure_profile(ctx.author.id)
        if image_url is None:
            embed = discord.Embed(
                title="Missing Image Link", color=0x2b2d31,
                description=(
                    "**Usage:** `profile background <image_url>`\n"
                    "**Example:** `profile background https://i.imgur.com/example.png`\n\n"
                    "**Note:** Use Imgur — Discord URLs expire!"
                )
            )
            return await ctx.send(embed=embed)
        if not VALID_IMAGE_REGEX.match(image_url):
            return await ctx.send(f"{CROSS} Invalid image URL.")
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "UPDATE profiles SET background = ? WHERE user_id = ?", (image_url, ctx.author.id)
            )
            await db.commit()
        await ctx.send(f"{CHECK} Background updated.")

    # ── profile social ────────────────────────────────────────────────────────

    @profile.command(name="social")
    async def profile_social(self, ctx: commands.Context, platform: str = None, *, link: str = None):
        """Add or remove a social link."""
        await ensure_profile(ctx.author.id)
        if platform is None:
            embed = discord.Embed(
                title="Profile Social", color=0x2b2d31,
                description=(
                    f"**Usage:** `profile social <platform> <link>`\n"
                    f"**Platforms:** `{', '.join(SOCIAL_KEYS)}`\n\n"
                    "Leave link blank to **remove** a platform."
                )
            )
            return await ctx.send(embed=embed)
        platform = platform.lower()
        if platform not in SOCIAL_KEYS:
            return await ctx.send(f"{CROSS} Invalid platform. Choose from: `{', '.join(SOCIAL_KEYS)}`")
        async with aiosqlite.connect(DB_PATH) as db:
            if link:
                if len(link) > 200:
                    return await ctx.send(f"{CROSS} Link too long.")
                await db.execute(
                    "INSERT OR REPLACE INTO profile_socials (user_id, platform, link) VALUES (?, ?, ?)",
                    (ctx.author.id, platform, link)
                )
                await db.commit()
                await ctx.send(f"{CHECK} **{platform.capitalize()}** added.")
            else:
                await db.execute(
                    "DELETE FROM profile_socials WHERE user_id = ? AND platform = ?",
                    (ctx.author.id, platform)
                )
                await db.commit()
                await ctx.send(f"{CHECK} **{platform.capitalize()}** removed.")

    # ── profile reset ─────────────────────────────────────────────────────────

    @profile.command(name="reset")
    async def profile_reset(self, ctx: commands.Context):
        """Reset your entire profile."""
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM profiles WHERE user_id = ?", (ctx.author.id,))
            await db.execute("DELETE FROM profile_socials WHERE user_id = ?", (ctx.author.id,))
            await db.commit()
        await ctx.send(f"{CHECK} Profile reset.")

    # ── server commands ───────────────────────────────────────────────────────

    @commands.command(name="serveravatar", aliases=["sav"])
    async def serveravatar(self, ctx: commands.Context, *, member: discord.Member = None):
        target = member or ctx.author
        av = target.guild_avatar or target.display_avatar
        embed = discord.Embed(title=f"{target.display_name}'s Server Avatar", color=0x2b2d31)
        embed.set_image(url=av.url)
        await ctx.send(embed=embed)

    @commands.command(name="serverbanner")
    @commands.has_permissions(manage_guild=True)
    async def serverbanner(self, ctx: commands.Context):
        if not ctx.guild.banner:
            return await ctx.send(f"{CROSS} No banner set.")
        embed = discord.Embed(title=f"{ctx.guild.name}'s Banner", color=0x2b2d31)
        embed.set_image(url=ctx.guild.banner.url)
        await ctx.send(embed=embed)

    @commands.command(name="serverbio")
    async def serverbio(self, ctx: commands.Context):
        desc = ctx.guild.description or "*No description.*"
        embed = discord.Embed(title=ctx.guild.name, description=desc, color=0x2b2d31)
        if ctx.guild.icon:
            embed.set_thumbnail(url=ctx.guild.icon.url)
        await ctx.send(embed=embed)

    @commands.command(name="servername")
    async def servername(self, ctx: commands.Context):
        embed = discord.Embed(color=0x2b2d31)
        embed.add_field(name="Server Name", value=ctx.guild.name, inline=True)
        embed.add_field(name="Server ID",   value=str(ctx.guild.id), inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="serverresetprofile")
    @commands.has_permissions(manage_guild=True)
    async def serverresetprofile(self, ctx: commands.Context, *, member: discord.Member):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("DELETE FROM profiles WHERE user_id = ?", (member.id,))
            await db.execute("DELETE FROM profile_socials WHERE user_id = ?", (member.id,))
            await db.commit()
        await ctx.send(f"{CHECK} **{member.display_name}**'s profile reset.")

    @serverbanner.error
    @serverresetprofile.error
    async def perm_error(self, ctx, error):
        if isinstance(error, commands.MissingPermissions):
            await ctx.send(f"{CROSS} You need **Manage Server** permission!")

    # ── Global error handler so NOTHING is swallowed silently ────────────────

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        print(f"[profile] cog_command_error: {type(error).__name__}: {error}")
        traceback.print_exc()
        # Unwrap the discord.py wrapper
        original = getattr(error, "original", error)
        if not isinstance(error, commands.MissingPermissions):
            await ctx.send(f"{CROSS} Error: `{type(original).__name__}: {original}`")


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCog(bot))
