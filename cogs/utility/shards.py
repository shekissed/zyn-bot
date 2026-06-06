from __future__ import annotations

import time
import discord
from discord.ext import commands

from emojis import CPU, RAM

SHARDS_PER_PAGE = 2
EMBED_COLOR = 0x000000


def _fmt_uptime(seconds: float) -> str:
    s = int(seconds)
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m, s = divmod(r, 60)
    return f"{d}d {h}h {m}m {s}s"


def _build_embed(
    bot: commands.AutoShardedBot,
    page: int,
    uptime_secs: float,
    per_shard_mem: float,
    per_shard_cpu: float,
    sort_by_latency: bool = False,
) -> discord.Embed:
    shard_count = bot.shard_count or 1
    total_pages = (shard_count + SHARDS_PER_PAGE - 1) // SHARDS_PER_PAGE

    shard_ids = list(range(shard_count))
    if sort_by_latency:
        shard_ids.sort(key=lambda i: bot.get_shard(i).latency if bot.get_shard(i) else float("inf"))

    start = page * SHARDS_PER_PAGE
    page_shards = shard_ids[start: start + SHARDS_PER_PAGE]

    embed = discord.Embed(
        title=f"<a:Online:1512079439771467796> Shard Statistics [{shard_count}]",
        color=EMBED_COLOR,
    )

    if bot.user and bot.user.avatar:
        embed.set_thumbnail(url=bot.user.avatar.url)

    uptime_str = _fmt_uptime(uptime_secs)

    for shard_id in page_shards:
        shard = bot.get_shard(shard_id)
        status_emoji = "<:success:1506951632670298162>" if shard else "<:wickk:1506950253545394257>"
        latency = round(shard.latency * 1000) if shard else 0

        shard_guilds = [g for g in bot.guilds if g.shard_id == shard_id]
        servers = len(shard_guilds)
        members = sum(g.member_count or 0 for g in shard_guilds)
        members_str = f"{members / 1000:.1f}K" if members >= 1000 else str(members)

        value = (
            f"> <:latency:1508460582741872670> **Latency:** {latency}ms\n"
            f"> <:uptime:1512081206286745650> **Uptime:** {uptime_str}\n"
            f"> <:info:1509859307007770674> **Resources**\n"
            f"> \u200c {CPU} **CPU:** {per_shard_cpu}%\n"
            f"> \u200c {RAM} **RAM:** {per_shard_mem} MB\n"
            f"> <:logs:1512032814705545267> **Servers:** {servers}\n"
            f"> <:members:1509864852288704583> **Members:** {members_str}"
        )
        embed.add_field(
            name=f"{status_emoji} Shard [{shard_id}]",
            value=value,
            inline=False,
        )

    embed.set_footer(text=f"Page {page + 1}/{total_pages}  •  Powered By Zyn Devs")
    return embed


class ShardSelectMenu(discord.ui.Select):
    def __init__(self, bot: commands.AutoShardedBot, view: ShardsView):
        self.bot = bot
        self._view = view

        options = [
            discord.SelectOption(
                label=f"Shard [{i}]",
                value=str(i),
                description=f"Latency: {round(bot.get_shard(i).latency * 1000)}ms" if bot.get_shard(i) else "Unavailable",
                emoji="<:success:1506951632670298162>" if bot.get_shard(i) else "<:wickk:1506950253545394257>",
            )
            for i in range(bot.shard_count or 1)
        ]

        super().__init__(placeholder="» Jump to a shard", options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self._view.author_id:
            return await interaction.response.send_message("You cannot use this menu.", ephemeral=True)

        shard_id = int(self.values[0])
        # Jump to the page that contains this shard
        shard_count = self.bot.shard_count or 1
        shard_ids = list(range(shard_count))
        if self._view.sort_by_latency:
            shard_ids.sort(key=lambda i: self.bot.get_shard(i).latency if self.bot.get_shard(i) else float("inf"))

        if shard_id in shard_ids:
            idx = shard_ids.index(shard_id)
            self._view.page = idx // SHARDS_PER_PAGE

        self._view.update_buttons()
        embed = self._view.make_embed()
        await interaction.response.edit_message(embed=embed, view=self._view)


class ShardsView(discord.ui.View):
    def __init__(
        self,
        bot: commands.AutoShardedBot,
        author_id: int,
        uptime_secs: float,
        per_shard_mem: float,
        per_shard_cpu: float,
    ):
        super().__init__(timeout=120)
        self.bot = bot
        self.author_id = author_id
        self.uptime_secs = uptime_secs
        self.per_shard_mem = per_shard_mem
        self.per_shard_cpu = per_shard_cpu
        self.page = 0
        self.sort_by_latency = False
        self.message: discord.Message | None = None

        shard_count = bot.shard_count or 1
        self.total_pages = (shard_count + SHARDS_PER_PAGE - 1) // SHARDS_PER_PAGE

        self.btn_prev = discord.ui.Button(
            emoji=discord.PartialEmoji.from_str("<:left_arrow:1512082166555742348>"),
            style=discord.ButtonStyle.gray,
            custom_id="shard_prev",
            disabled=True,
        )
        self.btn_delete = discord.ui.Button(
            emoji=discord.PartialEmoji.from_str("<:delete:1512081855568937072>"),
            style=discord.ButtonStyle.gray,
            custom_id="shard_delete",
        )
        self.btn_next = discord.ui.Button(
            emoji=discord.PartialEmoji.from_str("<:right_arrow:1512082143382208564>"),
            style=discord.ButtonStyle.gray,
            custom_id="shard_next",
            disabled=self.total_pages <= 1,
        )
        self.btn_sort = discord.ui.Button(
            label="⇅",
            style=discord.ButtonStyle.gray,
            custom_id="shard_sort",
        )
        self.btn_page = discord.ui.Button(
            label=f"1/{self.total_pages}",
            style=discord.ButtonStyle.gray,
            disabled=True,
            custom_id="shard_page_label",
        )

        self.btn_prev.callback = self.prev_callback
        self.btn_delete.callback = self.delete_callback
        self.btn_next.callback = self.next_callback
        self.btn_sort.callback = self.sort_callback

        self.add_item(self.btn_prev)
        self.add_item(self.btn_delete)
        self.add_item(self.btn_next)
        self.add_item(self.btn_sort)
        self.add_item(self.btn_page)
        self.add_item(ShardSelectMenu(bot, self))

    def make_embed(self) -> discord.Embed:
        now = time.time()
        uptime_secs = now - (now - self.uptime_secs)  # keep relative
        return _build_embed(
            self.bot,
            self.page,
            self.uptime_secs,
            self.per_shard_mem,
            self.per_shard_cpu,
            self.sort_by_latency,
        )

    def update_buttons(self):
        self.btn_prev.disabled = self.page == 0
        self.btn_next.disabled = self.page >= self.total_pages - 1
        self.btn_page.label = f"{self.page + 1}/{self.total_pages}"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.data.get("custom_id") in ("shard_prev", "shard_next", "shard_sort", "shard_delete"):
            if interaction.user.id != self.author_id:
                await interaction.response.send_message("You cannot use these buttons.", ephemeral=True)
                return False
        return True

    async def prev_callback(self, interaction: discord.Interaction):
        self.page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def next_callback(self, interaction: discord.Interaction):
        self.page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def sort_callback(self, interaction: discord.Interaction):
        self.sort_by_latency = not self.sort_by_latency
        self.page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.make_embed(), view=self)

    async def delete_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()
        if self.message:
            await self.message.delete()

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except Exception:
                pass


class Shards(commands.Cog):
    def __init__(self, bot: commands.AutoShardedBot):
        self.bot = bot

    @commands.command(name="shards", aliases=["shard", "shardinfo"])
    @commands.guild_only()
    async def shards_command(self, ctx: commands.Context):
        """Display statistics for all bot shards."""
        try:
            shard_count = self.bot.shard_count or 1
            now = time.time()
            uptime_secs = now - self.bot.start_time

            try:
                import psutil
                proc = psutil.Process()
                total_mem = proc.memory_info().rss / (1024 ** 2)
                cpu_total = psutil.cpu_percent(interval=None)
            except Exception:
                total_mem = 0.0
                cpu_total = 0.0

            per_shard_mem = round(total_mem / shard_count, 2)
            per_shard_cpu = round(cpu_total / shard_count, 4)

            view = ShardsView(
                bot=self.bot,
                author_id=ctx.author.id,
                uptime_secs=uptime_secs,
                per_shard_mem=per_shard_mem,
                per_shard_cpu=per_shard_cpu,
            )
            embed = view.make_embed()
            msg = await ctx.send(embed=embed, view=view)
            view.message = msg

        except Exception as e:
            import traceback
            traceback.print_exc()
            await ctx.send(f"Error: {e}")


async def setup(bot: commands.AutoShardedBot):
    await bot.add_cog(Shards(bot))
