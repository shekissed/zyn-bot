"""
guild_join.py — Welcome messages on bot join.

DM to server owner  : Thanks for adding + prefix info + Support / Website / Go to <Server> buttons
Server message      : Same info + auto-sends the full help menu below it
"""

from __future__ import annotations

import discord
from discord.ext import commands
from discord.ui import (
    LayoutView, Container, Section, TextDisplay,
    Separator, Thumbnail, ActionRow, Button
)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from main import DEFAULT_PREFIX, SUPPORT_LINK, INVITE_LINK

# Re-use the HelpView from help.py
from cogs.utility.help import HelpView


# ─── DM View ───────────────────────────────────────────────────────────────

class WelcomeDMView(LayoutView):
    """Sent to the server owner via DM."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild

        container = Container()

        # Header section with bot avatar thumbnail
        header = TextDisplay(
            f"• **Thanks for adding !**\n\n"
            f"• My default prefix is `{DEFAULT_PREFIX}`\n"
            f"• Use `{DEFAULT_PREFIX}help` in the server for commands\n"
            f"• For questions or details join **Support server**"
        )
        if bot.user and bot.user.avatar:
            container.add_item(
                Section(header, accessory=Thumbnail(bot.user.avatar.url))
            )
        else:
            container.add_item(header)

        container.add_item(Separator(spacing=discord.SeparatorSpacing.small))

        # Buttons row 1: Support + Website
        container.add_item(ActionRow(
            Button(label="Support Server", style=discord.ButtonStyle.link, url=SUPPORT_LINK),
            Button(label="Website",        style=discord.ButtonStyle.link, url=INVITE_LINK),
        ))
        # Button row 2: Go to <Server>
        # Build a guild invite URL — we pass the guild object so we can try to get a vanity
        # Falls back to just showing the server name without a link if no invite available
        container.add_item(ActionRow(
            Button(
                label=f"Go to  {guild.name}",
                style=discord.ButtonStyle.link,
                url=f"https://discord.com/channels/{guild.id}"
            ),
        ))

        self.add_item(container)


# ─── Server View ───────────────────────────────────────────────────────────

class WelcomeServerView(LayoutView):
    """Posted in the first available channel in the server."""

    def __init__(self, bot: commands.Bot, guild: discord.Guild):
        super().__init__(timeout=None)
        self.bot = bot
        self.guild = guild

        container = Container()

        header = TextDisplay(
            f"• **Thanks for adding Zyn !**\n\n"
            f"• My default prefix is `{DEFAULT_PREFIX}`\n"
            f"• Use `{DEFAULT_PREFIX}help` or mention me for commands\n"
            f"• For questions or details join our **Support server**"
        )
        if bot.user and bot.user.avatar:
            container.add_item(
                Section(header, accessory=Thumbnail(bot.user.avatar.url))
            )
        else:
            container.add_item(header)

        container.add_item(Separator(spacing=discord.SeparatorSpacing.small))

        # Buttons row 1: Support + Website
        container.add_item(ActionRow(
            Button(label="Support Server", style=discord.ButtonStyle.link, url=SUPPORT_LINK),
            Button(label="Website",        style=discord.ButtonStyle.link, url=INVITE_LINK),
        ))
        # Button row 2: Run help (non-link, triggers help via on_interaction)
        run_help_btn = Button(
            label=f"Run {DEFAULT_PREFIX}help",
            style=discord.ButtonStyle.primary,
            custom_id=f"guild_welcome_help_{guild.id}"
        )
        run_help_btn.callback = self._run_help
        container.add_item(ActionRow(run_help_btn))

        self.add_item(container)

    async def _run_help(self, interaction: discord.Interaction):
        """Send the full help menu as a follow-up when the button is pressed."""
        help_view = HelpView(self.bot, interaction.user)
        await interaction.response.send_message(view=help_view)


# ─── Cog ───────────────────────────────────────────────────────────────────

class GuildJoinCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # Re-register the server welcome view for persistence across restarts
        # (the run-help button stays alive)
        # We can't pre-register without guild IDs, so we rely on the button
        # custom_id being handled globally — discord.py will route it via on_interaction

    @commands.Cog.listener()
    async def on_guild_join(self, guild: discord.Guild):
        # ── 1. DM the server owner ──────────────────────────────────────────
        owner = guild.owner
        if owner:
            try:
                dm_view = WelcomeDMView(self.bot, guild)
                await owner.send(view=dm_view)
            except discord.Forbidden:
                pass  # Owner has DMs closed — that's fine
            except Exception:
                pass

        # ── 2. Post in the server ───────────────────────────────────────────
        target_channel = self._find_channel(guild)
        if not target_channel:
            return

        try:
            server_view = WelcomeServerView(self.bot, guild)
            welcome_msg = await target_channel.send(view=server_view)

            # Auto-send the help menu directly below the welcome message
            help_view = HelpView(self.bot, guild.me)
            await target_channel.send(view=help_view)
        except discord.Forbidden:
            pass
        except Exception:
            pass

    def _find_channel(self, guild: discord.Guild) -> discord.TextChannel | None:
        """Find the best channel to post the welcome message in."""
        me = guild.me
        if not me:
            return None

        # Priority 1: channel named general / welcome / bot / commands
        priority_names = ("general", "welcome", "bot-commands", "commands", "bot", "chat")
        for name in priority_names:
            ch = discord.utils.find(
                lambda c: isinstance(c, discord.TextChannel)
                and name in c.name.lower()
                and c.permissions_for(me).send_messages,
                guild.channels
            )
            if ch:
                return ch

        # Priority 2: system channel
        if guild.system_channel and guild.system_channel.permissions_for(me).send_messages:
            return guild.system_channel

        # Priority 3: first text channel we can send in
        for ch in guild.text_channels:
            if ch.permissions_for(me).send_messages:
                return ch

        return None


async def setup(bot: commands.Bot):
    await bot.add_cog(GuildJoinCog(bot))
