from __future__ import annotations

import discord
from discord.ext import commands
from discord.ui import LayoutView, Container, Section, TextDisplay, Separator, Thumbnail, ActionRow, Button
import psutil
import platform
import time

from emojis import (
    STATS as EMOJI_STATS,
    CPU as EMOJI_CPU,
    EMOJIES,
)


class StatsView(LayoutView):
    def __init__(
        self,
        bot: commands.Bot,
        start_time: float,
        author: discord.User | None = None,
        guild: discord.Guild | None = None,
    ):
        super().__init__(timeout=120)

        self.bot = bot
        self.start_time = start_time
        self.author = author
        self.guild = guild
        self.message: discord.Message | None = None

        container = Container()
        self._build(container)
        self.add_item(container)

    def _format_uptime(self) -> str:
        s = int(time.time() - self.start_time)
        d, r = divmod(s, 86400)
        h, r = divmod(r, 3600)
        m, _ = divmod(r, 60)
        return f"{d}d {h}h {m}m"

    def _build(self, c: Container):
        # ── Header with bot avatar thumbnail ──
        header_text = TextDisplay(
            f"# {EMOJI_STATS} Zyn's Statistics\n"
            f"-# Complete real-time overview of Zyn's operational status and resource usage."
        )
        if self.bot.user and self.bot.user.avatar:
            c.add_item(Section(header_text, accessory=Thumbnail(self.bot.user.avatar.url)))
        else:
            c.add_item(header_text)

        c.add_item(Separator(spacing=discord.SeparatorSpacing.large))

        # ── Stats paragraph ──
        total_members  = sum(g.member_count or 0 for g in self.bot.guilds)
        total_channels = sum(len(g.channels) for g in self.bot.guilds)
        latency        = round(self.bot.latency * 1000)
        ram            = psutil.virtual_memory()
        cpu            = psutil.cpu_percent(interval=None)
        total_commands = len(self.bot.commands) + len(self.bot.tree.get_commands())
        uptime         = self._format_uptime()

        shard_line = (
            f" This server is on shard **` {self.guild.shard_id} `**."
            if self.guild is not None and hasattr(self.guild, "shard_id")
            else ""
        )

        c.add_item(TextDisplay(
            f"Zyn is currently active across **{len(self.bot.guilds):,}** servers, "
            f"supporting **{total_members:,}** users and managing **{total_channels:,}** "
            f"channels. The bot has been online continuously for **{uptime}** "
            f"with a gateway latency of **{latency}ms**.**{shard_line}**\n\n"
            f"Running with **{total_commands}** loaded commands across **{len(self.bot.cogs)}** modules. "
            f"Currently consuming **{ram.used / (1024**2):.1f} MB** of memory at **{cpu}%** CPU — "
            f"powered by **Python {platform.python_version()}** "
            f"and **discord.py {discord.__version__}**."
        ))

        c.add_item(Separator(spacing=discord.SeparatorSpacing.small))

        # ── Buttons (ZEON-style: 2 rows) ──
        c.add_item(ActionRow(
            Button(label="Support Server", style=discord.ButtonStyle.link, url=self.bot.support_link),
            Button(label="Invite Zyn",    style=discord.ButtonStyle.link, url=self.bot.invite_link),
        ))
        c.add_item(ActionRow(
            Button(label="Vote for Zyn",  style=discord.ButtonStyle.link, url=self.bot.vote_link),
            Button(label="Website",        style=discord.ButtonStyle.link, url=self.bot.support_link),
        ))

        if self.author:
            c.add_item(Separator(spacing=discord.SeparatorSpacing.small))
            c.add_item(TextDisplay(f"-# Requested by {self.author.display_name}"))


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="stats", aliases=["botinfo", "bi"])
    @commands.guild_only()
    async def stats(self, ctx: commands.Context):
        view = StatsView(self.bot, self.start_time, author=ctx.author, guild=ctx.guild)
        msg = await ctx.send(view=view)
        view.message = msg


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
