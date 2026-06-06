from __future__ import annotations

import discord
from discord.ext import commands
from discord.ui import LayoutView, Container, TextDisplay, Separator, ActionRow, Select
import psutil
import platform
import time


def format_uptime(seconds: int) -> str:
    d, r = divmod(seconds, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s"


def build_page(bot: commands.Bot, page: str, start_time: float) -> LayoutView:
    uptime_secs = int(time.time() - start_time)
    ram = psutil.virtual_memory()
    cpu = psutil.cpu_percent(interval=None)
    ws_latency = round(bot.latency * 1000)
    shard_count = bot.shard_count or 1
    servers = len(bot.guilds)
    users = sum(g.member_count or 0 for g in bot.guilds)
    channels = sum(len(g.channels) for g in bot.guilds)
    commands_count = len(bot.commands) + len(bot.tree.get_commands())
    created = bot.user.created_at.strftime("%d %B %Y") if bot.user else "N/A"

    container = Container()

    # Title
    container.add_item(TextDisplay("# Zyn Statistics"))
    container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

    if page == "server":
        container.add_item(TextDisplay(
            "**Server Statistics**\n\n"
            f"- Servers: {servers:,}\n"
            f"- Users: {users:,}\n"
            f"- Channels: {channels:,}\n"
            f"- Commands: {commands_count:,}\n"
            f"- Created: {created}"
        ))

    elif page == "latency":
        status = (
            "Excellent" if ws_latency < 150 else
            "Good" if ws_latency < 300 else
            "Degraded" if ws_latency < 600 else
            "Poor"
        )
        container.add_item(TextDisplay(
            "**Latency**\n\n"
            f"- Websocket: {ws_latency}ms\n"
            f"- Status: {status}"
        ))

    elif page == "shards":
        lines = [f"**Shards**\n\n- Total Shards: {shard_count}"]
        if hasattr(bot, "shards") and bot.shards:
            for shard_id, shard in bot.shards.items():
                ping = round(shard.latency * 1000) if shard.latency else "N/A"
                lines.append(f"- Shard {shard_id}: {ping}ms")
        else:
            lines.append("- Shard 0: N/A")
        container.add_item(TextDisplay("\n".join(lines)))

    elif page == "system":
        container.add_item(TextDisplay(
            "**System Performance**\n\n"
            f"- Uptime: {format_uptime(uptime_secs)}\n"
            f"- CPU Usage: {cpu}%\n"
            f"- Memory Usage: {ram.used / (1024 ** 2):.2f} MB\n"
            f"- Total Memory: {ram.total / (1024 ** 2):.0f} MB\n"
            f"- Python: {platform.python_version()}\n"
            f"- discord.py: {discord.__version__}"
        ))

    container.add_item(Separator(spacing=discord.SeparatorSpacing.large))
    container.add_item(TextDisplay("-# Powered By Zyn Development"))

    # Dropdown to switch pages
    select = Select(
        placeholder="Navigate to...",
        options=[
            discord.SelectOption(label="Server Statistics", value="server",   description="Servers, users, channels & commands"),
            discord.SelectOption(label="Latency",           value="latency",  description="Websocket ping & status"),
            discord.SelectOption(label="Shards",            value="shards",   description="Shard count & per-shard ping"),
            discord.SelectOption(label="System Performance",value="system",   description="CPU, RAM, uptime & versions"),
        ],
    )

    # store refs for callback
    select._bot = bot
    select._start_time = start_time

    async def select_callback(interaction: discord.Interaction):
        chosen = select.values[0]
        new_view = build_page(interaction.client, chosen, start_time)
        await interaction.response.edit_message(view=new_view)

    select.callback = select_callback
    container.add_item(ActionRow(select))

    view = LayoutView(timeout=120)
    view.add_item(container)
    return view


class Stats(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.start_time = time.time()

    @commands.command(name="stats", aliases=["botinfo", "bi"])
    @commands.guild_only()
    async def stats(self, ctx: commands.Context):
        view = build_page(self.bot, "server", self.start_time)
        await ctx.send(view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Stats(bot))
