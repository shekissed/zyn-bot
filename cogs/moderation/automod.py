"""
cogs/automod.py — Advanced AutoMod System
ZEON-style UI: per-filter toggles, heat values, punishment settings,
select menus, settings panel with all filter status and heat values.

Filters:
  Anti spam, Anti caps, Anti link, Anti invites, Anti mass mention,
  Anti emoji spam, Anti NSFW link, Anti attachment spam, Anti zalgo spam,
  Similar message spam, Character limit spam, New line spam, Blacklist word

Detection logic preserved from original; UI completely reworked to match
ZEON-style embeds (filter list with toggle icons, master settings panel).
"""

from __future__ import annotations

import asyncio
import re
import sys
from collections import defaultdict
from datetime import timedelta, timezone, datetime
from pathlib import Path

import discord
from discord.ext import commands
import aiosqlite

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import (
    ENABLED, DISABLED, DISABLED_OFF,
    CHECK as CHECK_EMOJI, CROSS as CROSS_EMOJI, INFO,
    VERIFIED_CHECK,
)

DB = "db/automod.db"

# ─── Filter catalogue ─────────────────────────────────────────────────────────

ALL_FILTERS = [
    "Anti spam",
    "Anti caps",
    "Anti link",
    "Anti invites",
    "Anti mass mention",
    "Anti emoji spam",
    "Anti NSFW link",
    "Anti attachment spam",
    "Anti zalgo spam",
    "Similar message spam",
    "Character limit spam",
    "New line spam",
    "Blacklist word",
]

FILTER_DESCRIPTIONS = {
    "Anti spam":           "Detects rapid messages from a user.",
    "Anti caps":           "Detects messages with excessive capital letters.",
    "Anti link":           "Detects unauthorized links.",
    "Anti invites":        "Detects Discord server invites.",
    "Anti mass mention":   "Detects messages with too many mentions.",
    "Anti emoji spam":     "Detects messages with too many emojis.",
    "Anti NSFW link":      "Detects NSFW links and keywords.",
    "Anti attachment spam":"Detects messages with too many attachments.",
    "Anti zalgo spam":     "Detects messages with excessive Zalgo text.",
    "Similar message spam":"Detects users sending very similar messages.",
    "Character limit spam":"Detects messages that exceed a character limit.",
    "New line spam":       "Detects messages with excessive blank lines.",
    "Blacklist word":      "Detects messages containing blacklisted words.",
}

# Default heat values per filter
DEFAULT_HEAT = {
    "Anti spam":           15,
    "Anti caps":           0.12,
    "Anti link":           100,
    "Anti invites":        100,
    "Anti mass mention":   20,
    "Anti emoji spam":     12,
    "Anti NSFW link":      100,
    "Anti attachment spam":20,
    "Anti zalgo spam":     1.5,
    "Similar message spam":22,
    "Character limit spam":0.08,
    "New line spam":       5,
    "Blacklist word":      100,
}

RULES_TEXT = {
    "Anti spam":           "Triggers if more than 5 messages are sent in 10 seconds.\nPunishment: Auto Mute",
    "Anti caps":           "Triggers if >70% of message is capital letters (min 45 chars).\nPunishment: Auto Mute",
    "Anti link":           "Triggers if message contains an unauthorized link.\nPunishment: Auto Mute",
    "Anti invites":        "Triggers if message contains a Discord server invite.\nPunishment: Auto Mute",
    "Anti mass mention":   "Triggers if message contains 5 or more mentions.\nPunishment: Auto Mute",
    "Anti emoji spam":     "Triggers if message contains more than 5 emojis.\nPunishment: Auto Mute",
    "Anti NSFW link":      "Blocks messages containing NSFW keywords.\nPunishment: Block message (fixed)",
    "Anti attachment spam":"Triggers if message has too many attachments.\nPunishment: Auto Mute",
    "Anti zalgo spam":     "Deletes messages with excessive Zalgo/corrupted text.\nPunishment: Delete message",
    "Similar message spam":"Triggers if a user sends near-identical messages repeatedly.\nPunishment: Auto Mute",
    "Character limit spam":"Triggers if message exceeds the character limit.\nPunishment: Auto Mute",
    "New line spam":       "Deletes messages with excessive blank/empty lines.\nPunishment: Delete message",
    "Blacklist word":      "Deletes messages containing blacklisted words.\nPunishment: Auto Mute",
}


# ─── DB helpers ───────────────────────────────────────────────────────────────

async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.executescript("""
            CREATE TABLE IF NOT EXISTS automod (
                guild_id INTEGER PRIMARY KEY,
                enabled  INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS automod_filters (
                guild_id   INTEGER,
                filter     TEXT,
                enabled    INTEGER DEFAULT 0,
                punishment TEXT DEFAULT 'Auto Mute',
                heat       REAL DEFAULT 15,
                PRIMARY KEY (guild_id, filter)
            );
            CREATE TABLE IF NOT EXISTS automod_ignored (
                guild_id INTEGER,
                type     TEXT,
                id       INTEGER,
                PRIMARY KEY (guild_id, type, id)
            );
            CREATE TABLE IF NOT EXISTS automod_logging (
                guild_id    INTEGER PRIMARY KEY,
                log_channel INTEGER
            );
            CREATE TABLE IF NOT EXISTS automod_blacklist (
                guild_id INTEGER,
                word     TEXT,
                PRIMARY KEY (guild_id, word)
            );
            CREATE TABLE IF NOT EXISTS automod_similar_cache (
                guild_id   INTEGER,
                user_id    INTEGER,
                content    TEXT,
                timestamp  REAL,
                PRIMARY KEY (guild_id, user_id)
            );
        """)
        await db.commit()


async def is_enabled(guild_id: int) -> bool:
    async with aiosqlite.connect(DB) as db:
        async with db.execute("SELECT enabled FROM automod WHERE guild_id=?", (guild_id,)) as c:
            r = await c.fetchone()
            return r is not None and r[0] == 1


async def get_filter_row(guild_id: int, filter_name: str):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT enabled, punishment, heat FROM automod_filters WHERE guild_id=? AND filter=?",
            (guild_id, filter_name)
        ) as c:
            return await c.fetchone()


async def filter_enabled(guild_id: int, filter_name: str) -> bool:
    row = await get_filter_row(guild_id, filter_name)
    return row is not None and row[0] == 1


async def get_all_filter_data(guild_id: int) -> dict:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT filter, enabled, punishment, heat FROM automod_filters WHERE guild_id=?",
            (guild_id,)
        ) as c:
            rows = await c.fetchall()
    existing = {r[0]: {"enabled": bool(r[1]), "punishment": r[2], "heat": r[3]} for r in rows}
    result = {}
    for f in ALL_FILTERS:
        result[f] = existing.get(f, {
            "enabled": False,
            "punishment": "Auto Mute",
            "heat": DEFAULT_HEAT.get(f, 15),
        })
    return result


async def set_filter(guild_id: int, filter_name: str, enabled: bool = None,
                     punishment: str = None, heat: float = None):
    async with aiosqlite.connect(DB) as db:
        row = await get_filter_row(guild_id, filter_name)
        if row is None:
            cur_enabled    = True if enabled is not None else False
            cur_punishment = punishment or "Auto Mute"
            cur_heat       = heat if heat is not None else DEFAULT_HEAT.get(filter_name, 15)
        else:
            cur_enabled    = enabled    if enabled is not None    else bool(row[0])
            cur_punishment = punishment if punishment is not None else row[1]
            cur_heat       = heat       if heat is not None       else row[2]

        await db.execute(
            "INSERT OR REPLACE INTO automod_filters (guild_id, filter, enabled, punishment, heat) "
            "VALUES (?,?,?,?,?)",
            (guild_id, filter_name, int(cur_enabled), cur_punishment, cur_heat)
        )
        await db.commit()


async def get_ignored(guild_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT type, id FROM automod_ignored WHERE guild_id=?", (guild_id,)
        ) as c:
            rows = await c.fetchall()
    channels = {r[1] for r in rows if r[0] == "channel"}
    roles    = {r[1] for r in rows if r[0] == "role"}
    return channels, roles


async def get_log_channel(guild_id: int):
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT log_channel FROM automod_logging WHERE guild_id=?", (guild_id,)
        ) as c:
            r = await c.fetchone()
            return r[0] if r else None


async def get_blacklist(guild_id: int) -> list:
    async with aiosqlite.connect(DB) as db:
        async with db.execute(
            "SELECT word FROM automod_blacklist WHERE guild_id=?", (guild_id,)
        ) as c:
            return [r[0] for r in await c.fetchall()]


# ─── Embed builders ───────────────────────────────────────────────────────────

def _toggle(enabled: bool) -> str:
    return "<:wickk:1506950253545394257>" if not enabled else ENABLED


def _build_main_embed(filter_data: dict) -> discord.Embed:
    e = discord.Embed(title="<:config:1511944430104608939> Automod Configuration", color=0x000000)
    lines = "\n".join(
        f"<:white_arrow:1512065044454838412> **{f}** → {_toggle(filter_data[f]['enabled'])}"
        for f in ALL_FILTERS
    )
    e.description = lines
    return e


def _build_settings_embed(filter_data: dict) -> discord.Embed:
    e = discord.Embed(title="<:zbat:1511945397172703254> Automod Master Settings", color=0x000000)
    lines = []
    for f in ALL_FILTERS:
        d    = filter_data[f]
        pun  = d["punishment"]
        heat = d["heat"]
        max_note = " (Max)" if heat >= 100 else ""
        lines.append(f"▶ **{f}** → Punishment: `{pun}` | Heat: `{heat}`{max_note}")
    e.description = "\n".join(lines)
    return e


# ─── UI Views / Selects ───────────────────────────────────────────────────────

class FilterToggleSelect(discord.ui.Select):
    """Select filters to enable/disable."""
    def __init__(self, guild_id: int, filter_data: dict, author_id: int):
        self.guild_id  = guild_id
        self.author_id = author_id
        options = [
            discord.SelectOption(
                label=f,
                description=FILTER_DESCRIPTIONS.get(f, ""),
                value=f,
                emoji="<:Enabled:1509858724226007101>" if filter_data[f]["enabled"] else "<:disabled:1509859361638322307>",
            )
            for f in ALL_FILTERS
        ]
        super().__init__(
            placeholder="Select filters to toggle…",
            min_values=1,
            max_values=len(options),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)

        current = await get_all_filter_data(self.guild_id)
        for f in self.values:
            new_state = not current[f]["enabled"]
            await set_filter(self.guild_id, f, enabled=new_state)

        updated = await get_all_filter_data(self.guild_id)
        embed   = _build_main_embed(updated)
        await interaction.response.edit_message(embed=embed, view=self.view)


class PunishmentSelect(discord.ui.Select):
    """Select a filter, then choose its punishment."""
    def __init__(self, guild_id: int, filter_data: dict, author_id: int):
        self.guild_id  = guild_id
        self.author_id = author_id
        options = [
            discord.SelectOption(
                label=f,
                description=f"Current: {filter_data[f]['punishment']}",
                value=f,
            )
            for f in ALL_FILTERS if f != "Anti NSFW link"  # NSFW is always block
        ]
        super().__init__(placeholder="Select a filter to configure…", options=options)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("Not your menu.", ephemeral=True)

        filter_name = self.values[0]
        modal = PunishmentModal(self.guild_id, filter_name, interaction.user.id)
        await interaction.response.send_modal(modal)


class PunishmentModal(discord.ui.Modal, title="Settings for Filter"):
    def __init__(self, guild_id: int, filter_name: str, author_id: int):
        super().__init__(title=f"Settings for {filter_name}"[:45])
        self.guild_id    = guild_id
        self.filter_name = filter_name
        self.author_id   = author_id

        self.pun_input = discord.ui.TextInput(
            label="Punishment Type (Auto Mute / Kick / Ban / Delete)",
            placeholder="Auto Mute",
            default="Auto Mute",
            required=True,
            max_length=10,
        )
        self.heat_input = discord.ui.TextInput(
            label="Heat Value",
            placeholder="e.g. 15",
            required=True,
            max_length=6,
        )
        self.mute_input = discord.ui.TextInput(
            label="Mute Duration (e.g. 10m) — ONLY IF MUTE",
            placeholder="Required if Mute is selected",
            required=False,
            max_length=10,
        )
        self.add_item(self.pun_input)
        self.add_item(self.heat_input)
        self.add_item(self.mute_input)

    async def on_submit(self, interaction: discord.Interaction):
        pun_raw = self.pun_input.value.strip()
        valid   = {"Auto Mute": "Auto Mute", "Kick": "Kick", "Ban": "Ban", "Delete": "Delete",
                   "auto mute": "Auto Mute", "mute": "Auto Mute", "kick": "Kick",
                   "ban": "Ban", "delete": "Delete"}
        pun = valid.get(pun_raw)
        if not pun:
            return await interaction.response.send_message(
                "Invalid punishment. Choose: `Auto Mute`, `Kick`, `Ban`, or `Delete`.",
                ephemeral=True,
            )

        try:
            heat = float(self.heat_input.value.strip())
        except ValueError:
            return await interaction.response.send_message("Heat must be a number.", ephemeral=True)

        await set_filter(self.guild_id, self.filter_name, punishment=pun, heat=heat)

        await interaction.response.send_message(
            f"{CHECK_EMOJI} **{self.filter_name}** updated → Punishment: `{pun}` | Heat: `{heat}`",
            ephemeral=True,
        )


# ─── Shared punishment executor ───────────────────────────────────────────────

_MUTE_DURATIONS = {
    "Anti spam":           12,
    "Anti caps":           1,
    "Anti link":           7,
    "Anti invites":        12,
    "Anti mass mention":   3,
    "Anti emoji spam":     1,
    "Anti attachment spam":5,
    "Anti zalgo spam":     0,
    "Similar message spam":5,
    "Character limit spam":2,
    "New line spam":       0,
    "Blacklist word":      5,
    "AI Content Filter":   10,
}


async def _punish(member: discord.Member, channel: discord.TextChannel,
                  message, punishment: str, reason: str,
                  bot: commands.Bot, guild: discord.Guild, filter_name: str):
    try:
        if message:
            try:
                await message.delete()
            except discord.HTTPException:
                pass

        action_taken = None

        if punishment == "Auto Mute":
            mins = _MUTE_DURATIONS.get(filter_name, 5)
            if mins > 0:
                await member.edit(
                    timed_out_until=discord.utils.utcnow() + timedelta(minutes=mins),
                    reason=reason,
                )
                action_taken = f"Muted for {mins}m"
            else:
                action_taken = "Message deleted"
        elif punishment == "Kick":
            await member.kick(reason=reason)
            action_taken = "Kicked"
        elif punishment == "Ban":
            await member.ban(reason=reason)
            action_taken = "Banned"
        elif punishment == "Delete":
            action_taken = "Message deleted"

        if action_taken:
            e = discord.Embed(color=0x000000)
            e.description = (
                f"{CHECK_EMOJI} {member.mention} — **{action_taken}**\n"
                f"-# Reason: {reason}"
            )
            await channel.send(embed=e, delete_after=20)

        log_ch_id = await get_log_channel(guild.id)
        if log_ch_id:
            log_ch = guild.get_channel(log_ch_id)
            if log_ch:
                log_embed = discord.Embed(
                    title=f"AutoMod — {filter_name}",
                    color=0x000000,
                    timestamp=datetime.now(timezone.utc),
                )
                log_embed.add_field(name="User",    value=f"{member.mention} (`{member.id}`)", inline=True)
                log_embed.add_field(name="Channel", value=channel.mention,                    inline=True)
                log_embed.add_field(name="Action",  value=action_taken or "Deleted",          inline=True)
                log_embed.add_field(name="Reason",  value=reason,                             inline=False)
                log_embed.set_thumbnail(url=member.display_avatar.url)
                log_embed.set_footer(text=f"User ID: {member.id}")
                await log_ch.send(embed=log_embed)

    except (discord.Forbidden, discord.HTTPException):
        pass


async def _should_check(message: discord.Message, filter_name: str) -> bool:
    if not message.guild or message.author.bot:
        return False
    if not await is_enabled(message.guild.id):
        return False
    if not await filter_enabled(message.guild.id, filter_name):
        return False
    if message.author == message.guild.owner:
        return False
    ignored_ch, ignored_rl = await get_ignored(message.guild.id)
    if message.channel.id in ignored_ch:
        return False
    if any(r.id in ignored_rl for r in message.author.roles):
        return False
    return True


def _footer(embed: discord.Embed, ctx) -> discord.Embed:
    embed.set_footer(
        text=f'"{ctx.command.qualified_name}" · {ctx.author}',
        icon_url=ctx.author.display_avatar.url,
    )
    return embed


def _not_enabled(ctx) -> discord.Embed:
    e = discord.Embed(
        title=f"Automod — {ctx.guild.name}",
        description=(
            f"AutoMod is not enabled on this server.\n\n"
            f"Status: {DISABLED_OFF} Disabled\n"
            f"Enable it with `{ctx.prefix}automod enable`"
        ),
        color=0x000000,
    )
    e.set_thumbnail(url=ctx.bot.user.avatar.url)
    return _footer(e, ctx)


# ─── Main Cog ─────────────────────────────────────────────────────────────────

class AutoMod(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._spam_cache:    dict = defaultdict(list)
        self._similar_cache: dict = defaultdict(list)
        bot.loop.create_task(init_db())

    def _role_check(self, ctx) -> bool:
        return (
            ctx.author == ctx.guild.owner
            or ctx.author.top_role.position >= ctx.guild.me.top_role.position
        )

    # ─── Commands ─────────────────────────────────────────────────────────────

    @commands.group(name="automod", aliases=["am"], invoke_without_command=True)
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def automod(self, ctx):
        """AutoMod management commands."""
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    # enable
    @automod.command(name="enable")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def enable(self, ctx):
        """Enable automod on the server."""
        if not self._role_check(ctx):
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS_EMOJI} Your top role must be equal to or higher than my top role.",
                color=0x363836,
            ))
        if await is_enabled(ctx.guild.id):
            e = discord.Embed(
                description=f"{INFO} AutoMod is already enabled. Use `{ctx.prefix}automod manage` to configure filters.",
                color=0x363836,
            )
            return await ctx.send(embed=e)

        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT OR REPLACE INTO automod (guild_id, enabled) VALUES (?,1)", (ctx.guild.id,)
            )
            for f in ALL_FILTERS:
                await db.execute(
                    "INSERT OR IGNORE INTO automod_filters (guild_id, filter, enabled, punishment, heat) "
                    "VALUES (?,?,0,'Auto Mute',?)",
                    (ctx.guild.id, f, DEFAULT_HEAT.get(f, 15))
                )
            await db.commit()

        filter_data = await get_all_filter_data(ctx.guild.id)
        embed = _build_main_embed(filter_data)

        sel  = FilterToggleSelect(ctx.guild.id, filter_data, ctx.author.id)
        view = discord.ui.View(timeout=120)
        view.add_item(sel)

        done_btn  = discord.ui.Button(label="Setup Done", style=discord.ButtonStyle.success, emoji=CHECK_EMOJI)
        rules_btn = discord.ui.Button(label="Show Rules", style=discord.ButtonStyle.secondary, emoji="📋")

        async def _done(inter: discord.Interaction):
            if inter.user.id != ctx.author.id:
                return await inter.response.send_message("Not your menu.", ephemeral=True)
            for item in view.children:
                item.disabled = True
            await inter.response.edit_message(view=view)

        async def _rules(inter: discord.Interaction):
            lines = "\n\n".join(
                f"**{f}**\n{RULES_TEXT.get(f, '')}" for f in ALL_FILTERS
            )
            re = discord.Embed(title="AutoMod Rules", description=lines[:4000], color=0x363836)
            await inter.response.send_message(embed=re, ephemeral=True)

        done_btn.callback  = _done
        rules_btn.callback = _rules
        view.add_item(done_btn)
        view.add_item(rules_btn)

        await ctx.send(embed=embed, view=view)

    # disable
    @automod.command(name="disable")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def disable(self, ctx):
        """Disable automod on the server."""
        if not self._role_check(ctx):
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS_EMOJI} Insufficient role position.",
                color=0x000000,
            ))
        if not await is_enabled(ctx.guild.id):
            return await ctx.send(embed=_not_enabled(ctx))

        view = discord.ui.View(timeout=30)
        yes_btn = discord.ui.Button(label="Yes, disable", style=discord.ButtonStyle.danger)
        no_btn  = discord.ui.Button(label="Cancel",       style=discord.ButtonStyle.secondary)

        async def _yes(inter: discord.Interaction):
            if inter.user.id != ctx.author.id:
                return await inter.response.send_message("Not your menu.", ephemeral=True)
            async with aiosqlite.connect(DB) as db:
                for tbl in ("automod", "automod_filters", "automod_ignored", "automod_logging"):
                    await db.execute(f"DELETE FROM {tbl} WHERE guild_id=?", (ctx.guild.id,))
                await db.commit()
            for item in view.children:
                item.disabled = True
            e = discord.Embed(
                description=f"{CHECK_EMOJI} AutoMod has been **disabled** for **{ctx.guild.name}**.",
                color=0x000000,
            )
            await inter.response.edit_message(embed=e, view=view)

        async def _no(inter: discord.Interaction):
            if inter.user.id != ctx.author.id:
                return await inter.response.send_message("Not your menu.", ephemeral=True)
            for item in view.children:
                item.disabled = True
            await inter.response.edit_message(content="Cancelled.", embed=None, view=view)

        yes_btn.callback = _yes
        no_btn.callback  = _no
        view.add_item(yes_btn)
        view.add_item(no_btn)

        e = discord.Embed(
            title="Disable AutoMod?",
            description="This will remove all filter settings and ignored channels/roles.\nAre you sure?",
            color=0x363836,
        )
        await ctx.send(embed=e, view=view)

    # manage (toggle filters)
    @automod.command(name="manage", aliases=["filters", "toggle"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def manage(self, ctx):
        """Toggle individual automod filters on or off."""
        if not self._role_check(ctx):
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS_EMOJI} Insufficient role position.",
                color=0x363836,
            ))
        if not await is_enabled(ctx.guild.id):
            return await ctx.send(embed=_not_enabled(ctx))

        filter_data = await get_all_filter_data(ctx.guild.id)
        embed = _build_main_embed(filter_data)

        sel  = FilterToggleSelect(ctx.guild.id, filter_data, ctx.author.id)
        view = discord.ui.View(timeout=120)
        view.add_item(sel)
        _footer(embed, ctx)
        await ctx.send(embed=embed, view=view)

    # settings (master panel with heat values)
    @automod.command(name="settings", aliases=["config", "panel"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def settings(self, ctx):
        """View the master settings panel showing all filters, punishments, and heat values."""
        if not self._role_check(ctx):
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS_EMOJI} Insufficient role position.",
                color=0x363836,
            ))
        if not await is_enabled(ctx.guild.id):
            return await ctx.send(embed=_not_enabled(ctx))

        filter_data = await get_all_filter_data(ctx.guild.id)
        embed = _build_settings_embed(filter_data)

        sel  = PunishmentSelect(ctx.guild.id, filter_data, ctx.author.id)
        view = discord.ui.View(timeout=120)
        view.add_item(sel)
        _footer(embed, ctx)
        await ctx.send(embed=embed, view=view)

    # reset
    @automod.command(name="reset")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def reset(self, ctx):
        """Reset (delete) the automod configuration for this server."""
        if not self._role_check(ctx):
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS_EMOJI} Insufficient role position.",
                color=0x363836,
            ))
        async with aiosqlite.connect(DB) as db:
            for tbl in ("automod", "automod_filters", "automod_ignored",
                        "automod_logging", "automod_blacklist"):
                await db.execute(f"DELETE FROM {tbl} WHERE guild_id=?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(
            description=f"{CHECK_EMOJI} AutoMod configuration has been reset for **{ctx.guild.name}**.",
            color=0x000000,
        ))

    # logging
    @automod.command(name="logging", aliases=["log"])
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def logging_cmd(self, ctx, channel: discord.TextChannel = None):
        """Set the logging channel for automod events."""
        if not self._role_check(ctx):
            return await ctx.send(embed=discord.Embed(
                description=f"{CROSS_EMOJI} Insufficient role position.",
                color=0x363836,
            ))
        if not await is_enabled(ctx.guild.id):
            return await ctx.send(embed=_not_enabled(ctx))
        if channel is None:
            return await ctx.send(embed=discord.Embed(
                description=f"{INFO} Usage: `{ctx.prefix}automod logging #channel`",
                color=0x363836,
            ))
        async with aiosqlite.connect(DB) as db:
            await db.execute(
                "INSERT OR REPLACE INTO automod_logging (guild_id, log_channel) VALUES (?,?)",
                (ctx.guild.id, channel.id)
            )
            await db.commit()
        e = discord.Embed(
            description=f"{VERIFIED_CHECK} Logging channel set to {channel.mention}.",
            color=0x000000,
        )
        await ctx.send(embed=_footer(e, ctx))

    # whitelist
    @automod.group(name="whitelist", aliases=["wl", "ignore", "exempt"], invoke_without_command=True)
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def whitelist(self, ctx):
        """Manage automod whitelist (ignored channels and roles)."""
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @whitelist.command(name="channel")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def wl_channel(self, ctx, channel: discord.TextChannel):
        if not self._role_check(ctx): return await ctx.send(embed=discord.Embed(description=f"{CROSS_EMOJI} Insufficient role position.", color=0x363836))
        if not await is_enabled(ctx.guild.id): return await ctx.send(embed=_not_enabled(ctx))
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT 1 FROM automod_ignored WHERE guild_id=? AND type='channel' AND id=?", (ctx.guild.id, channel.id)) as c:
                if await c.fetchone():
                    return await ctx.send(embed=discord.Embed(description=f"{DISABLED} {channel.mention} is already whitelisted.", color=0x363836))
            await db.execute("INSERT OR IGNORE INTO automod_ignored VALUES (?,'channel',?)", (ctx.guild.id, channel.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"{CHECK_EMOJI} {channel.mention} added to the whitelist.", color=0x000000))

    @whitelist.command(name="role")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def wl_role(self, ctx, role: discord.Role):
        if not self._role_check(ctx): return await ctx.send(embed=discord.Embed(description=f"{CROSS_EMOJI} Insufficient role position.", color=0x363836))
        if not await is_enabled(ctx.guild.id): return await ctx.send(embed=_not_enabled(ctx))
        async with aiosqlite.connect(DB) as db:
            async with db.execute("SELECT 1 FROM automod_ignored WHERE guild_id=? AND type='role' AND id=?", (ctx.guild.id, role.id)) as c:
                if await c.fetchone():
                    return await ctx.send(embed=discord.Embed(description=f"{DISABLED} {role.mention} is already whitelisted.", color=0x363836))
            await db.execute("INSERT OR IGNORE INTO automod_ignored VALUES (?,'role',?)", (ctx.guild.id, role.id))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"{CHECK_EMOJI} {role.mention} added to the whitelist.", color=0x000000))

    @whitelist.command(name="show", aliases=["list", "view"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def wl_show(self, ctx):
        if not await is_enabled(ctx.guild.id): return await ctx.send(embed=_not_enabled(ctx))
        ignored_ch, ignored_rl = await get_ignored(ctx.guild.id)
        e = discord.Embed(title=f"AutoMod Whitelist — {ctx.guild.name}", color=0x000000)
        e.add_field(name="Channels", value="\n".join(f"<#{c}>" for c in ignored_ch) or "None", inline=False)
        e.add_field(name="Roles",    value="\n".join(f"<@&{r}>" for r in ignored_rl) or "None",  inline=False)
        await ctx.send(embed=_footer(e, ctx))

    @whitelist.command(name="reset", aliases=["clear"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def wl_reset(self, ctx):
        if not self._role_check(ctx): return await ctx.send(embed=discord.Embed(description=f"{CROSS_EMOJI} Insufficient role position.", color=0x363836))
        async with aiosqlite.connect(DB) as db:
            await db.execute("DELETE FROM automod_ignored WHERE guild_id=?", (ctx.guild.id,))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"{CHECK_EMOJI} Whitelist cleared.", color=0x000000))

    # blacklist (word filter)
    @automod.group(name="blacklist", aliases=["bl", "wordfilter", "words"], invoke_without_command=True)
    @commands.cooldown(1, 4, commands.BucketType.user)
    async def blacklist(self, ctx):
        """Manage the blacklisted words list."""
        if ctx.subcommand_passed is None:
            await ctx.send_help(ctx.command)
            ctx.command.reset_cooldown(ctx)

    @blacklist.command(name="add")
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def bl_add(self, ctx, *, word: str):
        if not await is_enabled(ctx.guild.id): return await ctx.send(embed=_not_enabled(ctx))
        async with aiosqlite.connect(DB) as db:
            await db.execute("INSERT OR IGNORE INTO automod_blacklist (guild_id, word) VALUES (?,?)", (ctx.guild.id, word.lower()))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"{CHECK_EMOJI} Added `{word}` to the blacklist.", color=0x000000))

    @blacklist.command(name="remove", aliases=["del", "rm"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def bl_remove(self, ctx, *, word: str):
        async with aiosqlite.connect(DB) as db:
            await db.execute("DELETE FROM automod_blacklist WHERE guild_id=? AND word=?", (ctx.guild.id, word.lower()))
            await db.commit()
        await ctx.send(embed=discord.Embed(description=f"{CHECK_EMOJI} Removed `{word}` from the blacklist.", color=0x000000))

    @blacklist.command(name="list", aliases=["show", "view"])
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def bl_list(self, ctx):
        words = await get_blacklist(ctx.guild.id)
        e = discord.Embed(
            title=f"Blacklisted Words — {ctx.guild.name}",
            description=", ".join(f"`{w}`" for w in words) if words else "No words blacklisted.",
            color=0x000000,
        )
        await ctx.send(embed=_footer(e, ctx))

    # ─── Detection listeners ──────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        await asyncio.gather(
            self._check_spam(message),
            self._check_caps(message),
            self._check_link(message),
            self._check_invites(message),
            self._check_mass_mention(message),
            self._check_emoji_spam(message),
            self._check_attachment_spam(message),
            self._check_zalgo(message),
            self._check_similar(message),
            self._check_charlimit(message),
            self._check_newline(message),
            self._check_blacklist(message),
        )

    # ─── Regexes ──────────────────────────────────────────────────────────────

    _LINK_RE    = re.compile(r"https?://\S+")
    _INVITE_RE  = re.compile(r"(https?://)?(www\.)?(discord\.(gg|io|me|li)|discordapp\.com/invite|discord\.com/invite)/\S+")
    _GIF_RE     = re.compile(r"(\.gif$|https://(tenor\.com|giphy\.com|cdn\.discordapp\.com|media\.discordapp\.net))")
    _SPOTIFY_RE = re.compile(r"https://open\.spotify\.com/")
    _EMOJI_RE   = re.compile(
        r"<a?:[a-zA-Z0-9_]+:[0-9]+>|"
        r"[\U0001F600-\U0001F64F]|[\U0001F300-\U0001F5FF]|[\U0001F680-\U0001F6FF]|"
        r"[\U0001F700-\U0001FAFF]|[\U00002700-\U000027BF]|[\U0001F1E6-\U0001F1FF]"
    )
    _ZALGO_RE   = re.compile(r"[\u0300-\u036f\u0489]{3,}")
    _NSFW_WORDS = [
        "porn", "xxx", "adult", "nsfw", "xnxx", "onlyfans",
        "brazzers", "xhamster", "xvideos", "pornhub", "redtube",
    ]

    # ─── Individual detectors ─────────────────────────────────────────────────

    async def _check_spam(self, msg: discord.Message):
        if not await _should_check(msg, "Anti spam"):
            return
        now   = msg.created_at.timestamp()
        cache = self._spam_cache[msg.author.id]
        cache[:] = [t for t in cache if now - t < 10]
        cache.append(now)
        if len(cache) > 5:
            row = await get_filter_row(msg.guild.id, "Anti spam")
            pun = row[1] if row else "Auto Mute"
            await _punish(msg.author, msg.channel, msg, pun, "Spam", self.bot, msg.guild, "Anti spam")

    async def _check_caps(self, msg: discord.Message):
        if len(msg.content) < 45:
            return
        if not await _should_check(msg, "Anti caps"):
            return
        letters = [c for c in msg.content if c.isalpha()]
        if not letters:
            return
        if sum(1 for c in letters if c.isupper()) / len(letters) > 0.70:
            row = await get_filter_row(msg.guild.id, "Anti caps")
            pun = row[1] if row else "Auto Mute"
            await _punish(msg.author, msg.channel, msg, pun, "Excessive caps", self.bot, msg.guild, "Anti caps")

    async def _check_link(self, msg: discord.Message):
        if not self._LINK_RE.search(msg.content):
            return
        if not await _should_check(msg, "Anti link"):
            return
        if self._INVITE_RE.search(msg.content): return
        if self._GIF_RE.search(msg.content):    return
        if self._SPOTIFY_RE.search(msg.content): return
        row = await get_filter_row(msg.guild.id, "Anti link")
        pun = row[1] if row else "Auto Mute"
        await _punish(msg.author, msg.channel, msg, pun, "Unauthorized link", self.bot, msg.guild, "Anti link")

    async def _check_invites(self, msg: discord.Message):
        if not self._INVITE_RE.search(msg.content):
            return
        if not await _should_check(msg, "Anti invites"):
            return
        code = self._INVITE_RE.search(msg.content).group(0).split("/")[-1]
        try:
            guild_invites = await msg.guild.invites()
            if any(inv.code == code for inv in guild_invites):
                return
        except discord.Forbidden:
            pass
        row = await get_filter_row(msg.guild.id, "Anti invites")
        pun = row[1] if row else "Auto Mute"
        await _punish(msg.author, msg.channel, msg, pun, "Server invite", self.bot, msg.guild, "Anti invites")

    async def _check_mass_mention(self, msg: discord.Message):
        if msg.content.count("<@") < 5:
            return
        if not await _should_check(msg, "Anti mass mention"):
            return
        row = await get_filter_row(msg.guild.id, "Anti mass mention")
        pun = row[1] if row else "Auto Mute"
        await _punish(msg.author, msg.channel, msg, pun, f"Mass mention", self.bot, msg.guild, "Anti mass mention")

    async def _check_emoji_spam(self, msg: discord.Message):
        if not await _should_check(msg, "Anti emoji spam"):
            return
        if len(self._EMOJI_RE.findall(msg.content)) > 5:
            row = await get_filter_row(msg.guild.id, "Anti emoji spam")
            pun = row[1] if row else "Auto Mute"
            await _punish(msg.author, msg.channel, msg, pun, "Emoji spam", self.bot, msg.guild, "Anti emoji spam")

    async def _check_attachment_spam(self, msg: discord.Message):
        if len(msg.attachments) < 4:
            return
        if not await _should_check(msg, "Anti attachment spam"):
            return
        row = await get_filter_row(msg.guild.id, "Anti attachment spam")
        pun = row[1] if row else "Auto Mute"
        await _punish(msg.author, msg.channel, msg, pun, "Attachment spam", self.bot, msg.guild, "Anti attachment spam")

    async def _check_zalgo(self, msg: discord.Message):
        if not await _should_check(msg, "Anti zalgo spam"):
            return
        if self._ZALGO_RE.search(msg.content):
            await _punish(msg.author, msg.channel, msg, "Delete", "Zalgo text", self.bot, msg.guild, "Anti zalgo spam")

    async def _check_similar(self, msg: discord.Message):
        if not await _should_check(msg, "Similar message spam"):
            return
        key   = (msg.guild.id, msg.author.id)
        now   = msg.created_at.timestamp()
        cache = self._similar_cache[key]
        cache[:] = [(c, t) for c, t in cache if now - t < 30]

        content = msg.content.lower().strip()
        if not content:
            return

        matches = sum(1 for c, _ in cache if len(set(c) & set(content)) / max(len(set(c) | set(content)), 1) > 0.85)
        cache.append((content, now))

        if matches >= 3:
            row = await get_filter_row(msg.guild.id, "Similar message spam")
            pun = row[1] if row else "Auto Mute"
            await _punish(msg.author, msg.channel, msg, pun, "Similar message spam", self.bot, msg.guild, "Similar message spam")

    async def _check_charlimit(self, msg: discord.Message):
        if len(msg.content) < 1500:
            return
        if not await _should_check(msg, "Character limit spam"):
            return
        row = await get_filter_row(msg.guild.id, "Character limit spam")
        pun = row[1] if row else "Auto Mute"
        await _punish(msg.author, msg.channel, msg, pun, "Character limit exceeded", self.bot, msg.guild, "Character limit spam")

    async def _check_newline(self, msg: discord.Message):
        if not await _should_check(msg, "New line spam"):
            return
        if msg.content.count("\n") > 10:
            await _punish(msg.author, msg.channel, msg, "Delete", "Newline spam", self.bot, msg.guild, "New line spam")

    async def _check_blacklist(self, msg: discord.Message):
        if not msg.guild or msg.author.bot:
            return
        if not await is_enabled(msg.guild.id):
            return
        if not await filter_enabled(msg.guild.id, "Blacklist word"):
            return
        words = await get_blacklist(msg.guild.id)
        if not words:
            return
        content_lower = msg.content.lower()
        ignored_ch, ignored_rl = await get_ignored(msg.guild.id)
        if msg.channel.id in ignored_ch:
            return
        if any(r.id in ignored_rl for r in msg.author.roles):
            return
        for word in words:
            if word in content_lower:
                row = await get_filter_row(msg.guild.id, "Blacklist word")
                pun = row[1] if row else "Auto Mute"
                await _punish(msg.author, msg.channel, msg, pun, f"Blacklisted word", self.bot, msg.guild, "Blacklist word")
                return

    # ─── Guild cleanup ────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: discord.Guild):
        async with aiosqlite.connect(DB) as db:
            for tbl in ("automod", "automod_filters", "automod_ignored",
                        "automod_logging", "automod_blacklist", "automod_similar_cache"):
                await db.execute(f"DELETE FROM {tbl} WHERE guild_id=?", (guild.id,))
            await db.commit()


async def setup(bot: commands.Bot):
    await bot.add_cog(AutoMod(bot))
