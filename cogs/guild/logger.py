"""
logger.py — HQ Server Logger
Logs bot activity to separate channels via webhooks.

SETUP: Fill in the channel IDs below, then run ;setuplogger (owner only)
to auto-create webhooks in each channel. Done — all events log automatically.
"""

from __future__ import annotations

import discord
from discord.ext import commands
import aiosqlite
import asyncio
import traceback
from datetime import datetime, timezone
from pathlib import Path

# ═══════════════════════════════════════════════════════════════
#  🔧 CONFIGURE YOUR LOG CHANNEL IDs HERE
# ═══════════════════════════════════════════════════════════════

LOG_CHANNELS = {
    "guild_join":    1510289889546080276,   # Bot added to a server
    "guild_leave":   1510289960303988746,   # Bot removed from a server
    "commands":      1510287707622871140,   # Every command usage
    "errors":        1510639487418368181,   # Command errors / exceptions
    "noprefix":      1509833029219258369,   # No-prefix command usage
    "ready":         1509532413254963231,   # Bot ready / restart events
}

# ═══════════════════════════════════════════════════════════════

DB_PATH = Path("db/core.db")
WEBHOOK_NAME = "Zyn Logger"

# Colours per log type
COLORS = {
    "guild_join":  0x000000,  # green
    "guild_leave": 0x000000,  # red
    "commands":    0x000000,  # blurple
    "errors":      0x000000,  # bright red
    "noprefix":    0x000000,  # yellow
    "ready":       0x000000,  # cyan
}


class Logger(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._webhooks: dict[str, discord.Webhook] = {}
        self._lock = asyncio.Lock()

    # ─── DB ────────────────────────────────────────────────────────────────

    async def _init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS logger_webhooks (
                    log_type TEXT PRIMARY KEY,
                    webhook_url TEXT
                )
            """)
            await db.commit()

    async def _save_webhook(self, log_type: str, url: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO logger_webhooks (log_type, webhook_url) VALUES (?,?)",
                (log_type, url)
            )
            await db.commit()

    async def _load_webhooks(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT log_type, webhook_url FROM logger_webhooks") as cur:
                rows = await cur.fetchall()
        for log_type, url in rows:
            try:
                wh = discord.Webhook.from_url(url, client=self.bot)
                self._webhooks[log_type] = wh
            except Exception:
                pass

    # ─── Webhook sender ────────────────────────────────────────────────────

    async def _send(self, log_type: str, embed: discord.Embed):
        wh = self._webhooks.get(log_type)
        if not wh:
            return
        embed.color = COLORS.get(log_type, 0x000000)
        embed.timestamp = datetime.now(timezone.utc)
        try:
            await wh.send(embed=embed, username=f"Zyn Logs — {log_type.replace('_', ' ').title()}")
        except discord.NotFound:
            # Webhook was deleted — remove from cache
            self._webhooks.pop(log_type, None)
        except Exception:
            pass

    # ─── Setup command ─────────────────────────────────────────────────────

    @commands.command(name="setuplogger")
    @commands.is_owner()
    async def setup_logger(self, ctx: commands.Context):
        """Create/refresh webhooks in all configured log channels."""
        await ctx.typing()
        results = []

        for log_type, channel_id in LOG_CHANNELS.items():
            if not channel_id:
                results.append(f"<:warn:1509819732600029345> `{log_type}` — no channel ID set")
                continue

            channel = self.bot.get_channel(channel_id)
            if not channel or not isinstance(channel, discord.TextChannel):
                results.append(f"<:wickk:1506950253545394257> `{log_type}` — channel `{channel_id}` not found")
                continue

            try:
                # Delete old webhook with same name if exists
                existing = await channel.webhooks()
                for wh in existing:
                    if wh.name == WEBHOOK_NAME and wh.user == self.bot.user:
                        await wh.delete()

                # Create fresh webhook
                wh = await channel.create_webhook(
                    name=WEBHOOK_NAME,
                    avatar=await self.bot.user.display_avatar.read() if self.bot.user else None
                )
                await self._save_webhook(log_type, wh.url)
                self._webhooks[log_type] = discord.Webhook.from_url(wh.url, client=self.bot)
                results.append(f"<:success:1506951632670298162> `{log_type}` → {channel.mention}")
            except discord.Forbidden:
                results.append(f"<:wickk:1506950253545394257> `{log_type}` — missing Manage Webhooks in {channel.mention}")
            except Exception as e:
                results.append(f"<:wickk:1506950253545394257> `{log_type}` — {e}")

        await ctx.send("**Logger Setup Results:**\n" + "\n".join(results))

    # ─── Ready ─────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        await self._init_db()
        await self._load_webhooks()

        embed = discord.Embed(title="🟢 Bot Online")
        embed.add_field(name="Bot", value=f"`{self.bot.user}`", inline=True)
        embed.add_field(name="Servers", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="Commands", value=f"`{len(self.bot.commands)}`", inline=True)
        embed.add_field(name="Users", value=f"`{sum(g.member_count or 0 for g in self.bot.guilds):,}`", inline=True)
        embed.add_field(name="Ping", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True)
        await self._send("ready", embed)

    # ─── Guild Join ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        owner = guild.owner
        bots   = sum(1 for m in guild.members if m.bot)
        humans = (guild.member_count or 0) - bots

        embed = discord.Embed(title="📥 Joined a Server")
        embed.add_field(name="Server", value=f"`{guild.name}`", inline=True)
        embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Owner", value=f"`{owner}` (`{owner.id}`)" if owner else "`Unknown`", inline=True)
        embed.add_field(name="Members", value=f"`{guild.member_count}`", inline=True)
        embed.add_field(name="Humans", value=f"`{humans}`", inline=True)
        embed.add_field(name="Bots", value=f"`{bots}`", inline=True)
        embed.add_field(name="Channels", value=f"`{len(guild.channels)}`", inline=True)
        embed.add_field(name="Roles", value=f"`{len(guild.roles)}`", inline=True)
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Total Servers Now", value=f"`{len(self.bot.guilds)}`", inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await self._send("guild_join", embed)

    # ─── Guild Leave ───────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        embed = discord.Embed(title="📤 Left a Server")
        embed.add_field(name="Server", value=f"`{guild.name}`", inline=True)
        embed.add_field(name="ID", value=f"`{guild.id}`", inline=True)
        embed.add_field(name="Members", value=f"`{guild.member_count}`", inline=True)
        embed.add_field(name="Total Servers Now", value=f"`{len(self.bot.guilds)}`", inline=True)
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await self._send("guild_leave", embed)

    # ─── Command Usage ─────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_command(self, ctx: commands.Context):
        if ctx.author.bot:
            return

        embed = discord.Embed(title="⚡ Command Used")
        embed.add_field(name="Command", value=f"`{ctx.command.qualified_name}`", inline=True)
        embed.add_field(name="User", value=f"`{ctx.author}` (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Server", value=f"`{ctx.guild.name}`" if ctx.guild else "`DM`", inline=True)
        embed.add_field(name="Channel", value=ctx.channel.mention if ctx.guild else "`DM`", inline=True)
        embed.add_field(name="Message", value=f"```{ctx.message.content[:200]}```", inline=False)
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await self._send("commands", embed)

    # ─── Errors ────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        # Skip common user errors — only log real bot/code errors
        ignored = (
            commands.CommandNotFound,
            commands.CheckFailure,
            commands.MissingRequiredArgument,
            commands.BadArgument,
            commands.MemberNotFound,
            commands.RoleNotFound,
            commands.MissingPermissions,
            commands.BotMissingPermissions,
            commands.CommandOnCooldown,
        )
        if isinstance(error, ignored):
            return

        tb = "".join(traceback.format_exception(type(error), error, error.__traceback__))
        short_tb = tb[-1800:] if len(tb) > 1800 else tb  # discord field limit

        embed = discord.Embed(title="🔴 Command Error")
        embed.add_field(name="Command", value=f"`{ctx.command}`", inline=True)
        embed.add_field(name="User", value=f"`{ctx.author}` (`{ctx.author.id}`)", inline=True)
        embed.add_field(name="Server", value=f"`{ctx.guild.name if ctx.guild else 'DM'}`", inline=True)
        embed.add_field(name="Error", value=f"```py\n{str(error)[:500]}```", inline=False)
        embed.add_field(name="Traceback", value=f"```py\n{short_tb}```", inline=False)
        await self._send("errors", embed)

    # ─── No-prefix usage ───────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Detect when bot is mentioned with no real command (noprefix attempt or plain mention)
        bot_mention = f"<@{self.bot.user.id}>"
        alt_mention = f"<@!{self.bot.user.id}>"
        content = message.content.strip()

        if content in (bot_mention, alt_mention):
            # Plain mention — log as noprefix probe
            embed = discord.Embed(title="🔔 Bot Mentioned")
            embed.add_field(name="User", value=f"`{message.author}` (`{message.author.id}`)", inline=True)
            embed.add_field(name="Server", value=f"`{message.guild.name}`", inline=True)
            embed.add_field(name="Channel", value=message.channel.mention, inline=True)
            embed.set_thumbnail(url=message.author.display_avatar.url)
            await self._send("noprefix", embed)
            return

        # Detect noprefix usage: message starts with mention + command text
        for mention in (bot_mention, alt_mention):
            if content.startswith(mention):
                remainder = content[len(mention):].strip()
                if remainder:
                    embed = discord.Embed(title="✨ No-Prefix Command")
                    embed.add_field(name="User", value=f"`{message.author}` (`{message.author.id}`)", inline=True)
                    embed.add_field(name="Server", value=f"`{message.guild.name}`", inline=True)
                    embed.add_field(name="Channel", value=message.channel.mention, inline=True)
                    embed.add_field(name="Content", value=f"```{remainder[:300]}```", inline=False)
                    embed.set_thumbnail(url=message.author.display_avatar.url)
                    await self._send("noprefix", embed)
                return


async def setup(bot: commands.Bot):
    await bot.add_cog(Logger(bot))
