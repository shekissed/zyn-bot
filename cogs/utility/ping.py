import discord
from discord.ext import commands
from discord.ui import LayoutView, Container, Section, TextDisplay, Separator, Thumbnail, ActionRow, Button
import time
import aiosqlite


class PingCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db_path = "db/utility.db"

    async def get_db_latency(self):
        start = time.perf_counter()
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("SELECT 1")
        except Exception:
            return None
        end = time.perf_counter()
        return round((end - start) * 1000, 2)

    def get_status_label(self, ping):
        if ping < 150:
            return "● Online"
        elif ping < 350:
            return "● Degraded"
        elif ping < 600:
            return "● Slow"
        else:
            return "● Critical"

    @commands.command(name="ping", help="Checks the bot's latency.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def ping_command(self, ctx):
        await self.send_ping_ui(ctx)

    async def send_ping_ui(self, target, interaction=None):
        try:
            # Measure latencies
            ws_latency = round(self.bot.latency * 1000)

            start = time.perf_counter()
            db_latency = await self.get_db_latency()
            bot_latency = round((time.perf_counter() - start) * 1000)

            overall = round((ws_latency + bot_latency) / 2)
            status = self.get_status_label(overall)

            uptime_secs = int(time.time() - self.bot.start_time) if hasattr(self.bot, "start_time") else 0
            uptime_str = f"{uptime_secs // 3600}h {(uptime_secs % 3600) // 60}m {uptime_secs % 60}s"

            db_str = f"{db_latency}ms" if db_latency else "N/A"

            # ── Layout ──
            container = Container()

            # Row 1: API LATENCY | BOT LATENCY | Bot logo + name + status
            avatar_url = self.bot.user.avatar.url if self.bot.user and self.bot.user.avatar else None

            latency_text = (
                f"**API LATENCY**\n"
                f"# {ws_latency}ms\n"
                f"-# WebSocket heartbeat\n"
                f"\u200b\n"
                f"**BOT LATENCY**\n"
                f"# {bot_latency}ms\n"
                f"-# Internal processing"
            )

            bot_info_text = (
                f"**DB LATENCY**\n"
                f"# {db_str}\n"
                f"-# Database round-trip\n"
                f"\u200b\n"
                f"**STATUS**\n"
                f"### {status}\n"
                f"-# Overall health"
            )

            if avatar_url:
                container.add_item(
                    Section(
                        TextDisplay(latency_text),
                        accessory=Thumbnail(avatar_url)
                    )
                )
            else:
                container.add_item(TextDisplay(latency_text))

            container.add_item(Separator(spacing=discord.SeparatorSpacing.small))
            container.add_item(TextDisplay(bot_info_text))
            container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

            # Footer
            container.add_item(TextDisplay(
                f"-# **Powered By Zyn Development** · System Uptime: {uptime_str}"
            ))

            # Refresh button
            refresh_btn = Button(label="Refresh", style=discord.ButtonStyle.gray)
            req_by = target.author if isinstance(target, commands.Context) else target.user

            async def refresh_callback(inter: discord.Interaction):
                if inter.user.id != req_by.id:
                    return await inter.response.send_message(
                        "You cannot refresh someone else's ping.", ephemeral=True
                    )
                await self.send_ping_ui(inter, interaction=inter)

            refresh_btn.callback = refresh_callback
            container.add_item(ActionRow(refresh_btn))

            view = LayoutView(timeout=60)
            view.add_item(container)

            if interaction:
                await interaction.response.edit_message(view=view)
            else:
                await target.send(view=view)

        except Exception as e:
            print(f"[PingCog] Error: {e}")


async def setup(bot):
    await bot.add_cog(PingCog(bot))
