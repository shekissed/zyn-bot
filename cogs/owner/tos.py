from __future__ import annotations

import discord
from discord.ext import commands
from discord.ui import LayoutView, Container, Section, TextDisplay, Separator, Thumbnail, ActionRow, Button
import aiosqlite
from pathlib import Path

from emojis import EMOJIES

DB_PATH = Path("db/core.db")


async def has_accepted_tos(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM tos_accepted WHERE user_id = ?", (user_id,)
        ) as cursor:
            return await cursor.fetchone() is not None


async def set_tos_accepted(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO tos_accepted (user_id) VALUES (?)", (user_id,)
        )
        await db.commit()


# ─── TOS View ──────────────────────────────────────────────────────────────

class TosView(LayoutView):
    def __init__(self, bot: commands.Bot, user: discord.User | discord.Member):
        super().__init__(timeout=120)
        self.bot = bot
        self.user = user
        self.message: discord.Message | None = None

        container = Container()

        header_text = TextDisplay(
            "## 📋 Before using **Zyn**, you must accept these terms.\n"
            "-# This confirmation is only required once."
        )
        if bot.user and bot.user.avatar:
            container.add_item(Section(header_text, accessory=Thumbnail(bot.user.avatar.url)))
        else:
            container.add_item(header_text)

        container.add_item(Separator(spacing=discord.SeparatorSpacing.large))

        container.add_item(TextDisplay(
            "### 🛡️ Responsible Usage\n"
            "> Do not abuse commands, spam features, exploit bugs, or use Zyn for harmful activity.\n\n"
            "### 🔒 Server Safety\n"
            "> You are responsible for the permissions granted to the bot and how commands are used in your server.\n\n"
            "### 🗄️ Data Storage\n"
            "> Zyn may store required IDs and settings such as your user ID, guild ID, command preferences, and TOS confirmation.\n\n"
            "### ⚙️ Service Notice\n"
            "> Zyn is provided as-is. Features may change, break, or be removed at any time without prior notice.\n\n"
            "### ✅ Confirmation Required\n"
            "> Press **Confirm** to accept the Terms & Conditions and unlock all commands."
        ))

        container.add_item(Separator(spacing=discord.SeparatorSpacing.small))
        container.add_item(TextDisplay(
            "⚠️ If you press **Cancel** or dismiss this message, all commands will remain locked."
        ))
        container.add_item(Separator(spacing=discord.SeparatorSpacing.small))

        confirm_btn = Button(label="Confirm", style=discord.ButtonStyle.success)
        cancel_btn  = Button(label="Cancel",  style=discord.ButtonStyle.danger)
        confirm_btn.callback = self._confirm
        cancel_btn.callback  = self._cancel

        container.add_item(ActionRow(confirm_btn, cancel_btn))
        container.add_item(ActionRow(
            Button(label="Support Server", style=discord.ButtonStyle.link, url=bot.support_link),
        ))
        self.add_item(container)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                f"{EMOJIES['cross']} This isn't your TOS prompt.", ephemeral=True
            )
            return False
        return True

    async def _confirm(self, interaction: discord.Interaction):
        await set_tos_accepted(interaction.user.id)
        container = Container()
        container.add_item(TextDisplay(
            f"### {EMOJIES['check']} Terms Accepted\n"
            f"-# You're all set, {interaction.user.display_name}! All Zyn commands are now unlocked."
        ))
        view = LayoutView(timeout=None)
        view.add_item(container)
        await interaction.response.edit_message(view=view)
        self.stop()

    async def _cancel(self, interaction: discord.Interaction):
        container = Container()
        container.add_item(TextDisplay(
            f"### {EMOJIES['cross']} Terms Declined\n"
            f"-# Commands remain locked. Run any command again to see this prompt."
        ))
        view = LayoutView(timeout=None)
        view.add_item(container)
        await interaction.response.edit_message(view=view)
        self.stop()


# ─── Cog ───────────────────────────────────────────────────────────────────

class TosCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Register as a global bot check — fires BEFORE any command runs
        bot.add_check(self._tos_global_check)

    def cog_unload(self):
        self.bot.remove_check(self._tos_global_check)

    async def _tos_global_check(self, ctx: commands.Context) -> bool:
        """
        Runs before every command. If the user hasn't accepted TOS,
        sends the TOS view and raises CheckFailure to block the command.
        Returning False here prevents the command from executing at all.
        """
        # Skip DMs and bots
        if not ctx.guild or ctx.author.bot:
            return True

        if await has_accepted_tos(ctx.author.id):
            return True

        # Send TOS and block command
        view = TosView(self.bot, ctx.author)
        msg = await ctx.send(view=view)
        view.message = msg
        return False  # blocks the command silently — no double message

    @commands.Cog.listener()
    async def on_ready(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS tos_accepted "
                "(user_id INTEGER PRIMARY KEY, accepted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
            )
            await db.commit()

    # Suppress the CheckFailure that discord.py raises when check returns False
    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CheckFailure):
            # Only suppress if TOS is the reason (user hasn't accepted)
            if ctx.guild and not ctx.author.bot:
                if not await has_accepted_tos(ctx.author.id):
                    return  # TOS view already sent, swallow the error
        # All other CheckFailures (missing perms etc.) bubble up normally


async def setup(bot: commands.Bot):
    await bot.add_cog(TosCog(bot))
