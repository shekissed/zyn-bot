# cogs/premium.py — Server-based Premium System
import discord
import aiosqlite
import time
import sys
from discord.ext import commands
from discord.ui import Select, View
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from main import PREMIUM_DB, DEVELOPER_IDS
from emojis import CHECK, CROSS, REPLY, TIMER

LOG_CHANNEL_ID = 1509833029219258369

TRIAL_DAYS = 3

# days=None means Lifetime
PLANS = {
    "1 Month":   {"days": 30},
    "3 Months":  {"days": 90},
    "6 Months":  {"days": 180},
    "Lifetime":  {"days": None},
}

LIFETIME_SENTINEL = 9_999_999_999  # unix timestamp used for lifetime rows


def is_developer():
    async def predicate(ctx):
        return ctx.author.id in DEVELOPER_IDS
    return commands.check(predicate)


def _expires_unix(days: int | None) -> int:
    if days is None:
        return LIFETIME_SENTINEL
    return int(time.time() + days * 86400)


def _plan_label(plan: str, expires: int) -> str:
    if expires >= LIFETIME_SENTINEL:
        return f"`{plan}` — **Lifetime**"
    return f"`{plan}` — expires <t:{expires}:R>"


# ── Dropdown for ;premium add ─────────────────────────────────────────────────

class PremiumPlanSelect(Select):
    def __init__(self, bot: commands.Bot, guild: discord.Guild, invoker: discord.Member):
        options = []
        for plan, info in PLANS.items():
            desc = "Never expires" if info["days"] is None else f"{info['days']} days"
            options.append(discord.SelectOption(label=plan, description=desc))

        super().__init__(
            placeholder="Choose a Premium plan...",
            min_values=1, max_values=1,
            options=options
        )
        self.bot = bot
        self.guild = guild
        self.invoker = invoker

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        days = PLANS[chosen]["days"]
        expires = _expires_unix(days)
        expire_display = "Never" if expires >= LIFETIME_SENTINEL else f"<t:{expires}:F>"

        async with aiosqlite.connect(PREMIUM_DB) as db:
            await db.execute(
                "INSERT OR REPLACE INTO premium_guilds (guild_id, plan, added_by, expires) VALUES (?, ?, ?, ?)",
                (self.guild.id, chosen, self.invoker.id, expires)
            )
            await db.commit()

        # Log
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(title="Premium Activated", color=0x2b2d31, timestamp=datetime.utcnow())
            embed.add_field(name="Server",   value=f"{self.guild.name} (`{self.guild.id}`)", inline=False)
            embed.add_field(name="Plan",     value=chosen,          inline=True)
            embed.add_field(name="Expires",  value=expire_display,  inline=True)
            embed.add_field(name="Added by", value=f"{self.invoker} (`{self.invoker.id}`)", inline=False)
            try:
                await log_ch.send(embed=embed)
            except Exception:
                pass

        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"{CHECK} **Premium Activated**\n"
            f"{REPLY} **{self.guild.name}** now has **{chosen}** premium, "
            f"expiring {expire_display}."
        )
        await interaction.response.edit_message(content=None, embed=embed, view=None)


class PremiumPlanView(View):
    def __init__(self, bot, guild, invoker, timeout=60):
        super().__init__(timeout=timeout)
        self.add_item(PremiumPlanSelect(bot, guild, invoker))

    async def on_timeout(self):
        # Disable the select on timeout
        for item in self.children:
            item.disabled = True


# ── Cog ───────────────────────────────────────────────────────────────────────

class PremiumSystem(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def log(self, msg: str):
        ch = self.bot.get_channel(LOG_CHANNEL_ID)
        if ch:
            try:
                await ch.send(msg)
            except Exception:
                pass

    # ── ;premium ──────────────────────────────────────────────────────────────
    @commands.group(name="premium", invoke_without_command=True)
    @is_developer()
    async def premium(self, ctx: commands.Context):
        p = ctx.prefix
        embed = discord.Embed(title="Premium Commands", color=0x2b2d31)
        embed.description = (
            f"{REPLY} `{p}premium add [server_id]` — Add premium to a server\n"
            f"{REPLY} `{p}premium remove <server_id>` — Revoke a server's premium\n"
            f"{REPLY} `{p}premium list` — List all premium servers\n"
            f"{REPLY} `{p}premium trial` — Activate a 3-day trial for this server\n\n"
            f"**Plans:** `1 Month` · `3 Months` · `6 Months` · `Lifetime`"
        )
        await ctx.send(embed=embed)

    # ── ;premium add [server_id] ──────────────────────────────────────────────
    @premium.command(name="add")
    @is_developer()
    async def premium_add(self, ctx: commands.Context, server_id: int = None):
        """Add premium to a server via dropdown. Defaults to current server."""
        if server_id:
            guild = self.bot.get_guild(server_id)
            if not guild:
                return await ctx.send(embed=discord.Embed(
                    description=f"{CROSS} Could not find a server with ID `{server_id}`.",
                    color=0x2b2d31
                ))
        else:
            guild = ctx.guild

        # Warn if server already has active premium
        now = int(time.time())
        async with aiosqlite.connect(PREMIUM_DB) as db:
            async with db.execute(
                "SELECT plan, expires FROM premium_guilds WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                existing = await cursor.fetchone()

        if existing:
            plan, exp = existing
            if exp >= LIFETIME_SENTINEL:
                status = "**Lifetime**"
            elif exp > now:
                status = f"<t:{exp}:R>"
            else:
                status = "~~expired~~"

            if exp >= LIFETIME_SENTINEL or exp > now:
                return await ctx.send(embed=discord.Embed(
                    description=(
                        f"{CROSS} **{guild.name}** already has Premium activated.\n"
                        f"{REPLY} Plan: `{plan}` — {status}\n\n"
                        f"Use `{ctx.prefix}premium remove {guild.id}` first to replace it."
                    ),
                    color=0x2b2d31
                ))

        view = PremiumPlanView(self.bot, guild, ctx.author, timeout=60)
        await ctx.send(
            f"Select a premium plan for **{guild.name}** — *(60s to choose)*",
            view=view
        )

    # ── ;premium remove <server_id> ───────────────────────────────────────────
    @premium.command(name="remove")
    @is_developer()
    async def premium_remove(self, ctx: commands.Context, server_id: int):
        async with aiosqlite.connect(PREMIUM_DB) as db:
            async with db.execute(
                "SELECT plan FROM premium_guilds WHERE guild_id = ?", (server_id,)
            ) as cursor:
                row = await cursor.fetchone()

            if not row:
                return await ctx.send(embed=discord.Embed(
                    description=f"{CROSS} Server `{server_id}` does not have premium.",
                    color=0x2b2d31
                ))

            await db.execute("DELETE FROM premium_guilds WHERE guild_id = ?", (server_id,))
            await db.commit()

        guild = self.bot.get_guild(server_id)
        name = guild.name if guild else str(server_id)

        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"{CHECK} **Premium Removed**\n"
            f"{REPLY} **{name}**'s premium (`{row[0]}`) has been revoked."
        )
        await ctx.send(embed=embed)
        await self.log(f"{CROSS} Premium removed → {name} (`{server_id}`)")

    # ── ;premium list ─────────────────────────────────────────────────────────
    @premium.command(name="list")
    @is_developer()
    async def premium_list(self, ctx: commands.Context):
        async with aiosqlite.connect(PREMIUM_DB) as db:
            async with db.execute(
                "SELECT guild_id, plan, expires FROM premium_guilds ORDER BY expires DESC"
            ) as cursor:
                rows = await cursor.fetchall()

        if not rows:
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS} No premium servers found.",
                color=0x2b2d31
            ))

        now = int(time.time())
        lines = []
        for gid, plan, expires in rows:
            guild = self.bot.get_guild(gid)
            name = guild.name if guild else str(gid)
            if expires >= LIFETIME_SENTINEL:
                status = "**Lifetime**"
            elif expires > now:
                status = f"<t:{expires}:R>"
            else:
                status = "~~expired~~"
            lines.append(f"{REPLY} **{name}** — `{plan}` — {status}")

        embed = discord.Embed(title="Premium Servers", color=0x2b2d31)
        embed.description = "\n".join(lines)
        await ctx.send(embed=embed)

    # ── ;premium trial — usable by anyone (once per server) ──────────────────
    @premium.command(name="trial")
    async def premium_trial(self, ctx: commands.Context):
        """Activate a 3-day premium trial for this server. One trial per server."""
        guild = ctx.guild
        if not guild:
            return

        now = int(time.time())
        expires = _expires_unix(TRIAL_DAYS)
        expire_ts = f"<t:{expires}:F>"

        async with aiosqlite.connect(PREMIUM_DB) as db:
            # Ensure both tables exist (safety net if DB setup missed them)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS premium_guilds (
                    guild_id INTEGER PRIMARY KEY,
                    plan TEXT NOT NULL,
                    added_by INTEGER,
                    expires INTEGER NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS trial_used (
                    guild_id INTEGER PRIMARY KEY
                )
            """)
            await db.commit()

            # ── Check active premium ──────────────────────────────────────
            async with db.execute(
                "SELECT plan, expires FROM premium_guilds WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                existing = await cursor.fetchone()

            if existing:
                plan, exp = existing
                # Active premium (paid or lifetime)
                if plan != "Trial" and (exp >= LIFETIME_SENTINEL or exp > now):
                    if exp >= LIFETIME_SENTINEL:
                        status = "**Lifetime**"
                    else:
                        status = f"<t:{exp}:R>"
                    return await ctx.send(embed=discord.Embed(
                        description=(
                            f"{CROSS} **This server already has Premium activated.**\n"
                            f"{REPLY} Plan: `{plan}` — {status}"
                        ),
                        color=0x2b2d31
                    ))
                # Active trial
                if plan == "Trial" and exp > now:
                    return await ctx.send(embed=discord.Embed(
                        description=(
                            f"{CROSS} **This server already has an active Trial.**\n"
                            f"{REPLY} Your trial expires <t:{exp}:R>."
                        ),
                        color=0x2b2d31
                    ))

            # ── Check if trial was already used (even if expired/removed) ─
            async with db.execute(
                "SELECT 1 FROM trial_used WHERE guild_id = ?", (guild.id,)
            ) as cursor:
                used = await cursor.fetchone()

            if used:
                return await ctx.send(embed=discord.Embed(
                    description=(
                        f"{CROSS} **This server has already used its free trial.**\n"
                        f"{REPLY} Contact a developer to get a paid plan."
                    ),
                    color=0x2b2d31
                ))

            # ── Grant trial ───────────────────────────────────────────────
            await db.execute(
                "INSERT OR REPLACE INTO premium_guilds (guild_id, plan, added_by, expires) VALUES (?, ?, ?, ?)",
                (guild.id, "Trial", ctx.author.id, expires)
            )
            await db.execute(
                "INSERT OR IGNORE INTO trial_used (guild_id) VALUES (?)", (guild.id,)
            )
            await db.commit()

        embed = discord.Embed(color=0x2b2d31)
        embed.description = (
            f"{CHECK} **Trial Activated!**\n"
            f"{REPLY} **{guild.name}** now has a **{TRIAL_DAYS}-day** premium trial.\n"
            f"{TIMER} Expires: {expire_ts}"
        )
        await ctx.send(embed=embed)
        await self.log(
            f"{CHECK} Trial activated → {guild.name} (`{guild.id}`) by {ctx.author} | expires: {expire_ts}"
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(PremiumSystem(bot))
