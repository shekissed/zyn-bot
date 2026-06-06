import discord
from discord.ext import commands
from discord.ui import View, Button
import aiosqlite
import asyncio
import io
import json
import random
import re
import sys
import urllib.request
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import CHECK, VERIFIED_CHECK, ZTICK, UNGHOST

# ─────────────────────────────────────────────
# FONTS  (safe fallback — never crashes on missing font)
# ─────────────────────────────────────────────
import os as _os

def _find_font(candidates):
    for p in candidates:
        if p and _os.path.isfile(p):
            return p
    return None

def _load_font(candidates, size):
    path = _find_font(candidates)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)

_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_MEDIUM_CANDIDATES = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Medium.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_REGULAR_CANDIDATES = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

# ─────────────────────────────────────────────
# 5 CARD THEMES  (rotate randomly on each join)
# ─────────────────────────────────────────────
CARD_THEMES = [
    {"name": "midnight", "bg": (10, 10, 20),  "accent": (88, 101, 242), "text": (255,255,255), "sub": (180,180,210)},
    {"name": "aurora",   "bg": (8,  22, 18),  "accent": (0,  200, 120), "text": (255,255,255), "sub": (160,220,190)},
    {"name": "crimson",  "bg": (18,  8,  8),  "accent": (220,  50,  80),"text": (255,255,255), "sub": (220,170,175)},
    {"name": "gold",     "bg": (15, 12,  5),  "accent": (220, 170,  40),"text": (255,255,255), "sub": (210,195,150)},
    {"name": "violet",   "bg": (12,  8, 22),  "accent": (160,  80, 240),"text": (255,255,255), "sub": (190,165,230)},
]

# ─────────────────────────────────────────────
# GREET VARIABLE RESOLUTION  (ported from Falcron)
# ─────────────────────────────────────────────

def _ordinal(n: int) -> str:
    s = ["th", "st", "nd", "rd"]
    v = n % 100
    return str(n) + (s[(v-20) % 10] if 20 < v and (v-20) % 10 < len(s) else s[v] if v < len(s) else s[0])


def _resolve_greet_variables(template: str, member: discord.Member) -> str:
    """Resolve {curly-brace} variables in a greet message template.

    Supported variables:
        {user}          — member mention  (@Username)
        {user_name}     — member username
        {user_tag}      — member name + discriminator (or username on new system)
        {member_count}  — total server member count
        {member_number} — ordinal member count (e.g. 100th)
        {server}        — server name
        {join_time}     — join timestamp (Discord relative)
    """
    guild = member.guild
    member_count = guild.member_count or 1
    join_ts = int(member.joined_at.timestamp()) if member.joined_at else 0
    join_time = f"<t:{join_ts}:F>" if join_ts else "Unknown"

    vars_map = {
        "{user}":          member.mention,
        "{user_name}":     member.name,
        "{user_tag}":      str(member),
        "{member_count}":  str(member_count),
        "{member_number}": _ordinal(member_count),
        "{server}":        guild.name,
        "{join_time}":     join_time,
    }
    # Sort longest-key-first so e.g. {member_number} is replaced before {member_count}
    for key, value in sorted(vars_map.items(), key=lambda kv: -len(kv[0])):
        template = template.replace(key, value)
    return template

# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _fetch_avatar(url: str) -> bytes | None:
    """Blocking fetch — must be called via run_in_executor only."""
    try:
        import socket
        old = socket.getdefaulttimeout()
        socket.setdefaulttimeout(5)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.read()
        finally:
            socket.setdefaulttimeout(old)
    except Exception:
        return None


def _draw_card(
    username: str,
    member_number: str,
    server_name: str,
    avatar_bytes: bytes | None = None,
    theme_index: int | None = None,
) -> io.BytesIO:
    """Pure CPU — safe to call in run_in_executor."""
    if theme_index is None:
        theme_index = random.randint(0, len(CARD_THEMES) - 1)
    t  = CARD_THEMES[theme_index % len(CARD_THEMES)]
    W, H = 900, 320

    card = Image.new("RGBA", (W, H), t["bg"])
    draw = ImageDraw.Draw(card)

    # Left accent bar
    draw.rectangle([0, 0, 8, H], fill=t["accent"])

    # Radial glow behind avatar area
    glow  = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    cx, cy = 160, H // 2
    for r in range(140, 0, -4):
        alpha = int(38 * (1 - r / 140))
        gdraw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*t["accent"], alpha))
    card = Image.alpha_composite(card, glow)
    draw = ImageDraw.Draw(card)

    # Dot grid top-right
    for row in range(4):
        for col in range(8):
            x = W - 30 - col * 22
            y = 30 + row * 22
            draw.ellipse([x-2, y-2, x+2, y+2], fill=(*t["accent"], 55))

    # Separator
    draw.rectangle([28, H//2+10, W-40, H//2+12], fill=(*t["accent"], 70))

    # Avatar
    AV = 160
    ax, ay = 40, (H - AV) // 2
    if avatar_bytes:
        try:
            av = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA").resize((AV, AV))
        except Exception:
            av = Image.new("RGBA", (AV, AV), (80, 80, 100, 255))
    else:
        av = Image.new("RGBA", (AV, AV), (80, 80, 100, 255))

    mask = Image.new("L", (AV, AV), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, AV, AV], fill=255)
    av.putalpha(mask)

    ring_size = AV + 8
    ring_img  = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring_img).ellipse([0, 0, ring_size, ring_size], fill=(*t["accent"], 220))
    inner = Image.new("L", (ring_size, ring_size), 0)
    ImageDraw.Draw(inner).ellipse([4, 4, ring_size-4, ring_size-4], fill=255)
    ring_img.putalpha(inner)
    card.paste(ring_img, (ax-4, ay-4), ring_img)
    card.paste(av, (ax, ay), av)

    # Text
    tx     = ax + AV + 36
    draw   = ImageDraw.Draw(card)
    f_name  = _load_font(_BOLD_CANDIDATES,    54)
    f_sub   = _load_font(_MEDIUM_CANDIDATES,  28)
    f_small = _load_font(_REGULAR_CANDIDATES, 22)

    draw.text((tx, 70), username, font=f_name, fill=t["text"])

    badge_text = f"Member #{member_number}"
    bb = f_sub.getbbox(badge_text)
    tw, th = bb[2]-bb[0]+28, bb[3]-bb[1]+14
    draw.rounded_rectangle([tx, 142, tx+tw, 142+th], radius=7, fill=(*t["accent"], 210))
    draw.text((tx+14, 146), badge_text, font=f_sub, fill=(255, 255, 255))

    draw.text((tx, 200), f"Welcome to {server_name}", font=f_small, fill=t["sub"])
    draw.rectangle([28, H-24, W-40, H-22], fill=(*t["accent"], 45))

    buf = io.BytesIO()
    card.save(buf, "PNG")
    buf.seek(0)
    return buf


# ─────────────────────────────────────────────
# DATABASE SCHEMA
# ─────────────────────────────────────────────
# welcome table:
#   guild_id   INTEGER PRIMARY KEY
#   channel_id INTEGER
#   enabled    INTEGER DEFAULT 1
#
# greet_container table  (new — Falcron container greet system):
#   guild_id      INTEGER PRIMARY KEY
#   channel_id    INTEGER
#   greet_type    TEXT    DEFAULT 'card'   -- 'card' | 'simple' | 'container'
#   message       TEXT                     -- simple mode text
#   content_text  TEXT                     -- plain message content sent alongside the container embed
#   title         TEXT
#   description   TEXT
#   color         INTEGER
#   thumbnail_url TEXT
#   image_url     TEXT
#   delete_after  INTEGER                  -- seconds, NULL = never


# ─────────────────────────────────────────────
# COG
# ─────────────────────────────────────────────

class Welcomer(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.bot.loop.create_task(self._init_db())

    async def _init_db(self):
        async with aiosqlite.connect("db/welcome.db") as db:
            # Original welcome card table
            await db.execute("""
                CREATE TABLE IF NOT EXISTS welcome (
                    guild_id   INTEGER PRIMARY KEY,
                    channel_id INTEGER,
                    enabled    INTEGER DEFAULT 1
                )
            """)
            try:
                await db.execute("ALTER TABLE welcome ADD COLUMN enabled INTEGER DEFAULT 1")
            except Exception:
                pass  # Column already exists

            # New container greet table (Falcron greet system)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS greet_container (
                    guild_id      INTEGER PRIMARY KEY,
                    channel_id    INTEGER,
                    greet_type    TEXT    DEFAULT 'card',
                    message       TEXT,
                    content_text  TEXT,
                    title         TEXT,
                    description   TEXT,
                    color         INTEGER,
                    thumbnail_url TEXT,
                    image_url     TEXT,
                    delete_after  INTEGER
                )
            """)
            # Migrate: add content_text if the table was created without it
            try:
                await db.execute("ALTER TABLE greet_container ADD COLUMN content_text TEXT")
            except Exception:
                pass  # Column already exists
            await db.commit()

    # ─────────────────────────────────────────────
    # GREET CONTAINER DB HELPERS
    # ─────────────────────────────────────────────

    async def _get_greet_config(self, guild_id: int) -> dict | None:
        async with aiosqlite.connect("db/welcome.db") as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM greet_container WHERE guild_id = ?", (guild_id,)
            ) as cur:
                row = await cur.fetchone()
        return dict(row) if row else None

    async def _set_greet_config(self, guild_id: int, **fields):
        """Upsert individual fields into greet_container."""
        async with aiosqlite.connect("db/welcome.db") as db:
            # Ensure row exists
            await db.execute(
                "INSERT OR IGNORE INTO greet_container (guild_id) VALUES (?)", (guild_id,)
            )
            for col, val in fields.items():
                await db.execute(
                    f"UPDATE greet_container SET {col} = ? WHERE guild_id = ?", (val, guild_id)
                )
            await db.commit()

    async def _delete_greet_config(self, guild_id: int):
        async with aiosqlite.connect("db/welcome.db") as db:
            await db.execute("DELETE FROM greet_container WHERE guild_id = ?", (guild_id,))
            await db.commit()

    # ── greet group ────────────────────────────

    @commands.hybrid_group(name="greet", invoke_without_command=True)
    async def greet(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    # ── setup — one click, done ─────────────────

    @greet.command(name="setup", help="Enable card welcome messages for this server.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_setup(self, ctx: commands.Context):
        # Check if already configured
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)
            ) as cur:
                row = await cur.fetchone()

        if row and row[0]:
            ch = ctx.guild.get_channel(row[0])
            embed = discord.Embed(
                description=f"Card welcome is already set up in {ch.mention if ch else '`unknown channel`'}.\n"
                            f"Use `{ctx.prefix}greet channel` to change the channel, or `{ctx.prefix}greet disable` to turn it off.",
                color=0x2b2d31
            )
            embed.set_author(name="Already configured")
            return await ctx.send(embed=embed)

        # Channel picker
        channels  = ctx.guild.text_channels
        if not channels:
            return await ctx.send("❌ No text channels found in this server.")

        chunks = [channels[i:i+25] for i in range(0, len(channels), 25)]
        page   = [0]

        embed = discord.Embed(
            title="Card Welcome Setup",
            description="Select the channel where welcome cards will be posted.",
            color=0x2b2d31
        )

        def make_view(p: int) -> View:
            from discord.ui import Select
            v   = View(timeout=120)
            sel = discord.ui.Select(
                placeholder="Pick a welcome channel",
                options=[
                    discord.SelectOption(label=f"# {ch.name}", value=str(ch.id), emoji=UNGHOST)
                    for ch in chunks[p]
                ]
            )

            async def on_select(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    return await interaction.response.send_message("Not authorised.", ephemeral=True)
                try:
                    ch_id = int(sel.values[0])
                    ch    = ctx.guild.get_channel(ch_id) or interaction.guild.get_channel(ch_id)
                    if ch is None:
                        return await interaction.response.send_message(
                            "❌ Could not find that channel. Please try again.", ephemeral=True
                        )
                    async with aiosqlite.connect("db/welcome.db") as db:
                        await db.execute(
                            "INSERT OR REPLACE INTO welcome (guild_id, channel_id) VALUES (?,?)",
                            (ctx.guild.id, ch_id)
                        )
                        await db.commit()
                    done = discord.Embed(
                        description=f"{ZTICK} Card welcome enabled! New members will get a welcome card in {ch.mention}.",
                        color=0x2b2d31
                    )
                    await interaction.response.edit_message(embed=done, view=None)
                except Exception as e:
                    try:
                        await interaction.response.send_message(f"❌ Something went wrong: {e}", ephemeral=True)
                    except discord.InteractionResponded:
                        await interaction.followup.send(f"❌ Something went wrong: {e}", ephemeral=True)

            sel.callback = on_select
            v.add_item(sel)

            if len(chunks) > 1:
                prev = Button(label="◀", style=discord.ButtonStyle.secondary, disabled=p == 0)
                nxt  = Button(label="▶", style=discord.ButtonStyle.secondary, disabled=p >= len(chunks)-1)

                async def on_prev(i: discord.Interaction):
                    if i.user != ctx.author:
                        return await i.response.send_message("Not authorised.", ephemeral=True)
                    page[0] -= 1
                    await i.response.edit_message(view=make_view(page[0]))

                async def on_next(i: discord.Interaction):
                    if i.user != ctx.author:
                        return await i.response.send_message("Not authorised.", ephemeral=True)
                    page[0] += 1
                    await i.response.edit_message(view=make_view(page[0]))

                prev.callback = on_prev
                nxt.callback  = on_next
                v.add_item(prev)
                v.add_item(nxt)

            cancel = Button(label="Cancel", style=discord.ButtonStyle.danger)

            async def on_cancel(i: discord.Interaction):
                if i.user != ctx.author:
                    return await i.response.send_message("Not authorised.", ephemeral=True)
                await i.response.edit_message(content="Setup cancelled.", embed=None, view=None)

            cancel.callback = on_cancel
            v.add_item(cancel)
            return v

        await ctx.send(embed=embed, view=make_view(0))

    # ── channel — change channel ────────────────

    @greet.command(name="channel", help="Change the welcome card channel.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_channel(self, ctx: commands.Context):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            return await ctx.send(
                f"❌ Not set up yet. Use `{ctx.prefix}greet setup` first."
            )

        channels = ctx.guild.text_channels
        chunks   = [channels[i:i+25] for i in range(0, len(channels), 25)]
        page     = [0]
        cur_ch   = ctx.guild.get_channel(row[0]) if row[0] else None

        embed = discord.Embed(
            title="Change Welcome Channel",
            description=f"Current: {cur_ch.mention if cur_ch else 'None'}\nSelect a new channel below.",
            color=0x2b2d31
        )

        def make_view(p: int) -> View:
            from discord.ui import Select
            v   = View(timeout=120)
            sel = discord.ui.Select(
                placeholder="Pick a channel",
                options=[
                    discord.SelectOption(label=f"# {ch.name}", value=str(ch.id), emoji=UNGHOST)
                    for ch in chunks[p]
                ]
            )

            async def on_select(interaction: discord.Interaction):
                if interaction.user != ctx.author:
                    return await interaction.response.send_message("Not authorised.", ephemeral=True)
                try:
                    ch_id = int(sel.values[0])
                    ch    = ctx.guild.get_channel(ch_id) or interaction.guild.get_channel(ch_id)
                    if ch is None:
                        return await interaction.response.send_message(
                            "❌ Could not find that channel. Please try again.", ephemeral=True
                        )
                    async with aiosqlite.connect("db/welcome.db") as db:
                        await db.execute(
                            "UPDATE welcome SET channel_id = ? WHERE guild_id = ?",
                            (ch_id, ctx.guild.id)
                        )
                        await db.commit()
                    done = discord.Embed(
                        description=f"{VERIFIED_CHECK} Welcome channel changed to {ch.mention}.",
                        color=0x2b2d31
                    )
                    await interaction.response.edit_message(embed=done, view=None)
                except Exception as e:
                    try:
                        await interaction.response.send_message(f"❌ Something went wrong: {e}", ephemeral=True)
                    except discord.InteractionResponded:
                        await interaction.followup.send(f"❌ Something went wrong: {e}", ephemeral=True)

            sel.callback = on_select
            v.add_item(sel)

            if len(chunks) > 1:
                prev = Button(label="◀", style=discord.ButtonStyle.secondary, disabled=p == 0)
                nxt  = Button(label="▶", style=discord.ButtonStyle.secondary, disabled=p >= len(chunks)-1)

                async def on_prev(i):
                    if i.user != ctx.author: return await i.response.send_message("Not authorised.", ephemeral=True)
                    page[0] -= 1
                    await i.response.edit_message(view=make_view(page[0]))

                async def on_next(i):
                    if i.user != ctx.author: return await i.response.send_message("Not authorised.", ephemeral=True)
                    page[0] += 1
                    await i.response.edit_message(view=make_view(page[0]))

                prev.callback = on_prev
                nxt.callback  = on_next
                v.add_item(prev)
                v.add_item(nxt)

            return v

        await ctx.send(embed=embed, view=make_view(0))

    # ── disable ────────────────────────────────

    @greet.command(name="disable", aliases=["reset"], help="Disable welcome cards for this server.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_disable(self, ctx: commands.Context):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)
            ) as cur:
                row = await cur.fetchone()

        if not row:
            return await ctx.send("❌ Welcome cards are not set up on this server.")

        view    = View(timeout=60)
        confirm = Button(label="Confirm", style=discord.ButtonStyle.danger)
        cancel  = Button(label="Cancel",  style=discord.ButtonStyle.secondary)

        async def on_confirm(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            async with aiosqlite.connect("db/welcome.db") as db:
                await db.execute("DELETE FROM welcome WHERE guild_id = ?", (ctx.guild.id,))
                await db.commit()
            await interaction.response.edit_message(
                content=f"{VERIFIED_CHECK} Welcome cards disabled.", embed=None, view=None
            )

        async def on_cancel(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

        confirm.callback = on_confirm
        cancel.callback  = on_cancel
        view.add_item(confirm)
        view.add_item(cancel)

        await ctx.send(
            embed=discord.Embed(
                description="Are you sure you want to disable welcome cards?",
                color=0x2b2d31
            ),
            view=view
        )

    # ── test ───────────────────────────────────

    @greet.command(name="test", help="Send a test welcome card.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_test(self, ctx: commands.Context):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT channel_id FROM welcome WHERE guild_id = ?", (ctx.guild.id,)
            ) as cur:
                row = await cur.fetchone()

        if not row or not row[0]:
            return await ctx.send(
                f"❌ Not configured. Use `{ctx.prefix}greet setup` first."
            )

        channel = ctx.guild.get_channel(row[0])
        if not channel:
            return await ctx.send(f"❌ Welcome channel no longer exists. Use `{ctx.prefix}greet channel` to set a new one.")

        await self._send_welcome_card(channel, ctx.author)
        await ctx.send(f"{CHECK} Test card sent to {channel.mention}.")

    # ── config ─────────────────────────────────

    @greet.command(name="config", help="Show the current welcome configuration.")
    @commands.has_permissions(administrator=True)
    async def greet_config(self, ctx: commands.Context):
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT channel_id, enabled FROM welcome WHERE guild_id = ?", (ctx.guild.id,)
            ) as cur:
                row = await cur.fetchone()

        greet_cfg = await self._get_greet_config(ctx.guild.id)

        embed = discord.Embed(title="Welcome Config", color=0x2b2d31)

        # --- Card welcome section ---
        if row:
            ch      = ctx.guild.get_channel(row[0]) if row[0] else None
            enabled = bool(row[1]) if len(row) > 1 else True
            embed.add_field(name="Card Welcome — Status",  value="✅ Enabled" if enabled else "❌ Disabled", inline=True)
            embed.add_field(name="Card Welcome — Channel", value=ch.mention if ch else "Not set",            inline=True)
            embed.add_field(name="Card Themes",  value="5 rotating (midnight, aurora, crimson, gold, violet)", inline=False)
        else:
            embed.add_field(name="Card Welcome", value="Not set up", inline=False)

        # --- Container greet section ---
        if greet_cfg and greet_cfg.get("channel_id"):
            gc = ctx.guild.get_channel(greet_cfg["channel_id"])
            greet_type   = greet_cfg.get("greet_type", "card")
            delete_after = greet_cfg.get("delete_after")
            embed.add_field(name="Container Greet — Channel", value=gc.mention if gc else "Not set",   inline=True)
            embed.add_field(name="Container Greet — Type",    value=greet_type.capitalize(),            inline=True)
            embed.add_field(
                name="Container Greet — Delete After",
                value=f"{delete_after}s" if delete_after else "Never",
                inline=True,
            )
        else:
            embed.add_field(name="Container Greet", value="Not set up (`greet container` to configure)", inline=False)

        embed.set_footer(text=f"Use {ctx.prefix}greet channel to change the card channel.")
        await ctx.send(embed=embed)

    # ═══════════════════════════════════════════
    # CONTAINER GREET SUBCOMMANDS  (Falcron port)
    # ═══════════════════════════════════════════

    # ── preview builder ────────────────────────

    def _build_container_preview(self, cfg: dict) -> discord.Embed:
        """
        Build a live preview embed from the current greet_container config.
        Variables are shown as-is (not resolved) so the admin sees the template.
        """
        color = cfg.get("color") or 0x2b2d31
        title = cfg.get("title") or "Welcome"
        desc  = cfg.get("description") or "*(no description set)*"

        embed = discord.Embed(title=title, description=desc, color=color)

        thumbnail_url = cfg.get("thumbnail_url")
        if thumbnail_url and (thumbnail_url.startswith("http://") or thumbnail_url.startswith("https://")):
            embed.set_thumbnail(url=thumbnail_url)

        image_url = cfg.get("image_url")
        if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
            embed.set_image(url=image_url)

        # Status footer
        greet_type   = cfg.get("greet_type", "?")
        delete_after = cfg.get("delete_after")
        content_text = cfg.get("content_text")
        channel_id   = cfg.get("channel_id")

        footer_parts = [f"Type: {greet_type}"]
        if channel_id:
            footer_parts.append(f"Channel: <#{channel_id}>")
        if content_text:
            footer_parts.append(f'Content: "{content_text[:40]}{"…" if len(content_text) > 40 else ""}"')
        footer_parts.append(f"Delete after: {delete_after}s" if delete_after else "Delete after: never")
        embed.set_footer(text="  •  ".join(footer_parts))

        return embed

    @greet.group(name="container", invoke_without_command=True, help="Manage the container-style greet message.")
    @commands.has_permissions(administrator=True)
    async def greet_container(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @greet_container.command(name="setup", help="Interactive setup for the container greet message.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_container_setup(self, ctx: commands.Context):
        """
        Lets admins choose between Simple (plain text + variables) or
        Container (rich embed-style with title, description, thumbnail, image, colour)
        — mirroring Falcron's greetsetup flow.
        """
        cfg = await self._get_greet_config(ctx.guild.id)

        view = View(timeout=120)

        simple_btn    = Button(label="Simple",    style=discord.ButtonStyle.secondary)
        container_btn = Button(label="Container", style=discord.ButtonStyle.secondary)
        cancel_btn    = Button(label="Cancel",    style=discord.ButtonStyle.danger)

        async def on_simple(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            await self._set_greet_config(ctx.guild.id, greet_type="simple")
            await interaction.response.edit_message(
                embed=discord.Embed(
                    description="✅ Set to **Simple** mode.\n"
                                f"Use `{ctx.prefix}greet container message <text>` to set your message.\n"
                                "Available variables: `{user}`, `{user_name}`, `{user_tag}`, "
                                "`{member_count}`, `{member_number}`, `{server}`, `{join_time}`",
                    color=0x2b2d31
                ),
                view=None
            )

        async def on_container(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            await self._set_greet_config(ctx.guild.id, greet_type="container")
            await interaction.response.edit_message(
                embed=discord.Embed(
                    description="✅ Set to **Container** mode.\n"
                                f"Use `{ctx.prefix}greet container title`, `{ctx.prefix}greet container description`, "
                                f"`{ctx.prefix}greet container color`, `{ctx.prefix}greet container thumbnail`, "
                                f"`{ctx.prefix}greet container image`, and `{ctx.prefix}greet container content` to customise it.\n"
                                "Variables: `{user}`, `{user_name}`, `{user_tag}`, "
                                "`{member_count}`, `{member_number}`, `{server}`, `{join_time}`",
                    color=0x2b2d31
                ),
                view=None
            )

        async def on_cancel(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

        simple_btn.callback    = on_simple
        container_btn.callback = on_container
        cancel_btn.callback    = on_cancel
        view.add_item(simple_btn)
        view.add_item(container_btn)
        view.add_item(cancel_btn)

        embed = discord.Embed(
            title="Container Greet Setup",
            description=(
                "Choose the type of greet message:\n\n"
                "**Simple** — plain text with variable substitution.\n"
                "**Container** — rich styled message with title, description, thumbnail, image, and colour.\n\n"
                "Both types support: `{user}`, `{user_name}`, `{user_tag}`, "
                "`{member_count}`, `{member_number}`, `{server}`, `{join_time}`."
            ),
            color=0x2b2d31
        )
        await ctx.send(embed=embed, view=view)

    @greet_container.command(name="channel", help="Set the channel for container greet messages.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_container_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        channel = channel or ctx.channel
        await self._set_greet_config(ctx.guild.id, channel_id=channel.id)
        await ctx.send(embed=discord.Embed(
            description=f"{ZTICK} Container greet channel set to {channel.mention}.",
            color=0x2b2d31
        ))

    @greet_container.command(name="message", help="Set the simple greet message text (supports variables).")
    @commands.has_permissions(administrator=True)
    async def greet_container_message(self, ctx: commands.Context, *, message: str):
        await self._set_greet_config(ctx.guild.id, message=message)
        cfg = await self._get_greet_config(ctx.guild.id)
        await ctx.send(
            embed=discord.Embed(
                description=f"{ZTICK} Greet message updated.\n\n**Preview of your message:**\n{message}",
                color=cfg.get("color") or 0x2b2d31
            )
        )

    @greet_container.command(name="content", help="Set the plain-text content sent alongside the container embed (supports variables).")
    @commands.has_permissions(administrator=True)
    async def greet_container_content(self, ctx: commands.Context, *, content: str = None):
        """
        Sets an optional plain-text message sent as the `content` field of the
        container greet (above the embed). Useful for pinging the new member.
        Pass 'none' or leave blank to clear it.
        """
        val = None if (content is None or content.lower() == "none") else content
        await self._set_greet_config(ctx.guild.id, content_text=val)
        cfg = await self._get_greet_config(ctx.guild.id)
        cleared = val is None
        desc = (
            f"{ZTICK} Content text cleared. No plain-text message will be sent."
            if cleared else
            f"{ZTICK} Content text set to:\n> {val}"
        )
        await ctx.send(
            content=f"**Preview content:** {val}" if not cleared else None,
            embed=self._build_container_preview(cfg) if cfg.get("greet_type") == "container" else
                  discord.Embed(description=desc, color=cfg.get("color") or 0x2b2d31)
        )

    @greet_container.command(name="title", help="Set the container greet title (supports variables).")
    @commands.has_permissions(administrator=True)
    async def greet_container_title(self, ctx: commands.Context, *, title: str):
        await self._set_greet_config(ctx.guild.id, title=title)
        cfg = await self._get_greet_config(ctx.guild.id)
        await ctx.send(
            content=f"{ZTICK} Greet title updated. **Live preview:**",
            embed=self._build_container_preview(cfg)
        )

    @greet_container.command(name="description", help="Set the container greet description (supports variables).")
    @commands.has_permissions(administrator=True)
    async def greet_container_description(self, ctx: commands.Context, *, description: str):
        await self._set_greet_config(ctx.guild.id, description=description)
        cfg = await self._get_greet_config(ctx.guild.id)
        await ctx.send(
            content=f"{ZTICK} Greet description updated. **Live preview:**",
            embed=self._build_container_preview(cfg)
        )

    @greet_container.command(name="color", help="Set the container greet accent color (hex, e.g. #5865F2).")
    @commands.has_permissions(administrator=True)
    async def greet_container_color(self, ctx: commands.Context, color: str):
        match = re.match(r"^#?([0-9A-Fa-f]{6})$", color.strip())
        if not match:
            return await ctx.send("❌ Invalid hex colour. Example: `#5865F2` or `5865F2`.")
        color_int = int(match.group(1), 16)
        await self._set_greet_config(ctx.guild.id, color=color_int)
        cfg = await self._get_greet_config(ctx.guild.id)
        await ctx.send(
            content=f"{ZTICK} Greet colour set to `#{match.group(1).upper()}`. **Live preview:**",
            embed=self._build_container_preview(cfg)
        )

    @greet_container.command(name="thumbnail", help="Set the container greet thumbnail URL.")
    @commands.has_permissions(administrator=True)
    async def greet_container_thumbnail(self, ctx: commands.Context, url: str):
        if not (url.startswith("http://") or url.startswith("https://")):
            return await ctx.send("❌ Please provide a valid URL starting with `http://` or `https://`.")
        await self._set_greet_config(ctx.guild.id, thumbnail_url=url)
        cfg = await self._get_greet_config(ctx.guild.id)
        await ctx.send(
            content=f"{ZTICK} Greet thumbnail set. **Live preview:**",
            embed=self._build_container_preview(cfg)
        )

    @greet_container.command(name="image", help="Set the container greet main image URL.")
    @commands.has_permissions(administrator=True)
    async def greet_container_image(self, ctx: commands.Context, url: str):
        if not (url.startswith("http://") or url.startswith("https://")):
            return await ctx.send("❌ Please provide a valid URL starting with `http://` or `https://`.")
        await self._set_greet_config(ctx.guild.id, image_url=url)
        cfg = await self._get_greet_config(ctx.guild.id)
        await ctx.send(
            content=f"{ZTICK} Greet image set. **Live preview:**",
            embed=self._build_container_preview(cfg)
        )

    @greet_container.command(name="deleteafter", help="Auto-delete the greet message after N seconds (0 to disable).")
    @commands.has_permissions(administrator=True)
    async def greet_container_deleteafter(self, ctx: commands.Context, seconds: int):
        if seconds < 0:
            return await ctx.send("❌ Seconds must be 0 or greater.")
        val = seconds if seconds > 0 else None
        await self._set_greet_config(ctx.guild.id, delete_after=val)
        cfg = await self._get_greet_config(ctx.guild.id)
        notice = f"{ZTICK} Auto-delete set to **{seconds}s**." if val else f"{ZTICK} Auto-delete disabled."
        await ctx.send(
            content=notice,
            embed=self._build_container_preview(cfg) if cfg.get("greet_type") == "container" else None
        )

    @greet_container.command(name="disable", help="Disable the container greet system.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_container_disable(self, ctx: commands.Context):
        cfg = await self._get_greet_config(ctx.guild.id)
        if not cfg:
            return await ctx.send("❌ Container greet is not configured.")

        view    = View(timeout=60)
        confirm = Button(label="Confirm", style=discord.ButtonStyle.danger)
        cancel  = Button(label="Cancel",  style=discord.ButtonStyle.secondary)

        async def on_confirm(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            await self._delete_greet_config(ctx.guild.id)
            await interaction.response.edit_message(
                content=f"{VERIFIED_CHECK} Container greet disabled.", embed=None, view=None
            )

        async def on_cancel(interaction: discord.Interaction):
            if interaction.user != ctx.author:
                return await interaction.response.send_message("Not authorised.", ephemeral=True)
            await interaction.response.edit_message(content="Cancelled.", embed=None, view=None)

        confirm.callback = on_confirm
        cancel.callback  = on_cancel
        view.add_item(confirm)
        view.add_item(cancel)

        await ctx.send(embed=discord.Embed(
            description="Are you sure you want to disable the container greet?",
            color=0x2b2d31
        ), view=view)

    @greet_container.command(name="test", help="Send a test container greet message.")
    @commands.has_permissions(administrator=True)
    @commands.cooldown(1, 6, commands.BucketType.user)
    async def greet_container_test(self, ctx: commands.Context):
        cfg = await self._get_greet_config(ctx.guild.id)
        if not cfg or not cfg.get("channel_id"):
            return await ctx.send(
                f"❌ Not configured. Use `{ctx.prefix}greet container channel` first."
            )
        channel = ctx.guild.get_channel(cfg["channel_id"])
        if not channel:
            return await ctx.send("❌ Greet channel no longer exists.")
        await self._send_container_greet(channel, ctx.author, cfg)
        await ctx.send(f"{CHECK} Test container greet sent to {channel.mention}.")

    @greet_container.command(name="variables", help="Show available greet message variables.")
    async def greet_container_variables(self, ctx: commands.Context):
        embed = discord.Embed(title="Greet Variables", color=0x2b2d31)
        embed.description = (
            "Use these in any greet text field (message, content, title, description):\n\n"
            "`{user}` — Mentions the member (e.g. @Username)\n"
            "`{user_name}` — The member's username\n"
            "`{user_tag}` — The member's name and discriminator\n"
            "`{member_count}` — Server's total member count\n"
            "`{member_number}` — Ordinal count (e.g. 100th)\n"
            "`{server}` — The server's name\n"
            "`{join_time}` — The member's join timestamp\n"
        )
        await ctx.send(embed=embed)

    # ── on_member_join ─────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        await asyncio.gather(
            self._handle_card_welcome(member),
            self._handle_container_greet(member),
            return_exceptions=True,
        )

    async def _handle_card_welcome(self, member: discord.Member):
        """Original image-card welcome."""
        async with aiosqlite.connect("db/welcome.db") as db:
            async with db.execute(
                "SELECT channel_id FROM welcome WHERE guild_id = ?", (member.guild.id,)
            ) as cur:
                row = await cur.fetchone()

        if not row or not row[0]:
            return

        channel = self.bot.get_channel(row[0])
        if not channel:
            return

        await self._send_welcome_card(channel, member)

    async def _handle_container_greet(self, member: discord.Member):
        """Falcron-style container/simple greet."""
        cfg = await self._get_greet_config(member.guild.id)
        if not cfg or not cfg.get("channel_id"):
            return

        channel = self.bot.get_channel(cfg["channel_id"])
        if not channel:
            return

        await self._send_container_greet(channel, member, cfg)

    # ── card sender ────────────────────────────

    async def _send_welcome_card(self, channel: discord.TextChannel, member: discord.Member):
        username   = member.display_name
        member_num = _ordinal(member.guild.member_count or 1)
        server     = member.guild.name

        # Fetch avatar in executor (blocking network call)
        av_url_raw = str(member.display_avatar.replace(size=256, format="png").url)
        av_bytes = await self.bot.loop.run_in_executor(None, _fetch_avatar, av_url_raw)

        # Draw card in executor (CPU work)
        buf = await self.bot.loop.run_in_executor(
            None, _draw_card, username, member_num, server, av_bytes, None
        )

        await channel.send(
            content=member.mention,
            file=discord.File(buf, filename="welcome.png")
        )

    # ── container greet sender ─────────────────

    async def _send_container_greet(
        self,
        channel: discord.TextChannel,
        member: discord.Member,
        cfg: dict,
    ):
        """
        Sends the greet. Supports:
          - 'simple'    → plain text (message field), optional content_text alongside it
          - 'container' → discord.Embed with title/desc/thumbnail/image,
                          optional content_text sent as the message content
        All text fields are resolved with {curly} variables.
        """
        greet_type   = cfg.get("greet_type", "simple")
        content_text = cfg.get("content_text")
        resolved_content = _resolve_greet_variables(content_text, member) if content_text else None

        sent_msg = None

        if greet_type == "simple":
            template = cfg.get("message") or "Welcome {user} to {server}! You are our {member_number} member."
            text = _resolve_greet_variables(template, member)
            # content_text goes as a separate message before, or merged if no content_text
            if resolved_content and resolved_content != text:
                await channel.send(content=resolved_content)
            sent_msg = await channel.send(content=text)

        elif greet_type == "container":
            title_raw = cfg.get("title") or "Welcome"
            desc_raw  = cfg.get("description") or "Welcome to {server}!"
            title = _resolve_greet_variables(title_raw, member)
            desc  = _resolve_greet_variables(desc_raw,  member)

            color = cfg.get("color") or 0x2b2d31
            embed = discord.Embed(title=title, description=desc, color=color)

            thumbnail_url = cfg.get("thumbnail_url")
            if thumbnail_url and (thumbnail_url.startswith("http://") or thumbnail_url.startswith("https://")):
                embed.set_thumbnail(url=thumbnail_url)

            image_url = cfg.get("image_url")
            if image_url and (image_url.startswith("http://") or image_url.startswith("https://")):
                embed.set_image(url=image_url)

            # content_text is sent as the plain message content (above the embed),
            # defaults to the member mention if not set
            msg_content = resolved_content or member.mention
            sent_msg = await channel.send(content=msg_content, embed=embed)

        # Auto-delete if configured
        delete_after = cfg.get("delete_after")
        if sent_msg and delete_after and delete_after > 0:
            await asyncio.sleep(delete_after)
            try:
                await sent_msg.delete()
            except discord.NotFound:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Welcomer(bot))
