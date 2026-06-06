"""
advancedlog.py — Zyn Advanced Logging System
Per-guild logging for voice, members, channels, roles, messages, server events.
Slash commands (admin/owner only) to configure each log type channel.
Auto-creates a channel if none is provided.
"""

from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands
import aiosqlite
import asyncio
from datetime import datetime, timezone
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import CHECK, CROSS, INFO, ENABLED, DISABLED, GEARS, LOADING

# ── Database ──────────────────────────────────────────────────────────────────
DB_PATH = Path("db/logging.db")

# All supported log types: key → (human name, emoji)
LOG_TYPES: dict[str, tuple[str, str]] = {
    "member_join":    ("Member Join",    "<:logs:1512032814705545267>"),
    "member_leave":   ("Member Leave",   "<:logs:1512032814705545267>"),
    "member_update":  ("Member Update",  "<:logs:1512032814705545267>"),
    "member_ban":     ("Member Ban",     "<:logs:1512032814705545267>"),
    "member_unban":   ("Member Unban",   "<:logs:1512032814705545267>"),
    "voice_state":    ("Voice Activity", "<:logs:1512032814705545267>"),
    "message_delete": ("Message Delete", "<:logs:1512032814705545267>"),
    "message_edit":   ("Message Edit",   "<:logs:1512032814705545267>"),
    "channel_create": ("Channel Create", "<:logs:1512032814705545267>"),
    "channel_delete": ("Channel Delete", "<:logs:1512032814705545267>"),
    "channel_update": ("Channel Update", ""),
    "role_create":    ("Role Create",    "<:logs:1512032814705545267>"),
    "role_delete":    ("Role Delete",    "<:logs:1512032814705545267>"),
    "role_update":    ("Role Update",    "<:logs:1512032814705545267>"),
    "server_update":  ("Server Update",  "<:logs:1512032814705545267>"),
    "invite_create":  ("Invite Create",  "<:logs:1512032814705545267>"),
    "invite_delete":  ("Invite Delete",  "<:logs:1512032814705545267>"),
}

# Embed colours per log type
LOG_COLORS: dict[str, int] = {
    "member_join":    0x000000,  # green
    "member_leave":   0x000000,  # red
    "member_update":  0x000000,  # yellow
    "member_ban":     0x000000,  # bright red
    "member_unban":   0x000000,  # green
    "voice_state":    0x000000,  # blurple
    "message_delete": 0x000000,  # pink
    "message_edit":   0x000000,  # yellow
    "channel_create": 0x000000,
    "channel_delete": 0x000000,
    "channel_update": 0x000000,
    "role_create":    0x000000,
    "role_delete":    0x000000,
    "role_update":    0x000000,
    "server_update":  0x000000,
    "invite_create":  0x000000,
    "invite_delete":  0x000000,
}


# ── Cog ───────────────────────────────────────────────────────────────────────

class AdvancedLog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        # cache: {guild_id: {log_type: channel_id}}
        self._cache: dict[int, dict[str, int]] = {}
        # Build the slash group as an instance attribute so reloads don't hit
        # CommandAlreadyRegistered from a stale class-level definition.
        self.log_group = app_commands.Group(
            name="log",
            description="⚙️ Configure advanced logging channels for this server.",
            default_permissions=discord.Permissions(administrator=True),
            guild_only=True,
        )
        self._register_log_subcommands()

    # ── DB helpers ───────────────────────────────────────────────────────────

    async def _init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS adv_log_channels (
                    guild_id   INTEGER NOT NULL,
                    log_type   TEXT    NOT NULL,
                    channel_id INTEGER NOT NULL,
                    PRIMARY KEY (guild_id, log_type)
                )
            """)
            await db.commit()

    async def _set_channel(self, guild_id: int, log_type: str, channel_id: int):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT OR REPLACE INTO adv_log_channels VALUES (?,?,?)",
                (guild_id, log_type, channel_id)
            )
            await db.commit()
        self._cache.setdefault(guild_id, {})[log_type] = channel_id

    async def _remove_channel(self, guild_id: int, log_type: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "DELETE FROM adv_log_channels WHERE guild_id=? AND log_type=?",
                (guild_id, log_type)
            )
            await db.commit()
        self._cache.get(guild_id, {}).pop(log_type, None)

    async def _load_cache(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT guild_id, log_type, channel_id FROM adv_log_channels") as cur:
                rows = await cur.fetchall()
        for guild_id, log_type, channel_id in rows:
            self._cache.setdefault(guild_id, {})[log_type] = channel_id

    async def _get_channel(self, guild_id: int, log_type: str) -> discord.TextChannel | None:
        ch_id = self._cache.get(guild_id, {}).get(log_type)
        if not ch_id:
            return None
        return self.bot.get_channel(ch_id)  # type: ignore

    # ── Auto-create channel helper ────────────────────────────────────────────

    async def _ensure_channel(
        self,
        guild: discord.Guild,
        log_type: str,
        provided: discord.TextChannel | None
    ) -> discord.TextChannel | None:
        """Return the provided channel, or auto-create one inside a Zyn Logs category."""
        if provided:
            await self._set_channel(guild.id, log_type, provided.id)
            return provided

        channel_name = f"zyn-{log_type.replace('_', '-')}-logs"
        try:
            category = discord.utils.get(guild.categories, name="📋 Zyn Logs")
            if not category:
                category = await guild.create_category(
                    "📋 Zyn Logs",
                    overwrites={
                        guild.default_role: discord.PermissionOverwrite(
                            send_messages=False, view_channel=True
                        )
                    }
                )
            ch = await guild.create_text_channel(channel_name, category=category)
            await self._set_channel(guild.id, log_type, ch.id)
            return ch
        except discord.Forbidden:
            return None

    # ── Embed sender ─────────────────────────────────────────────────────────

    async def _log(self, guild_id: int, log_type: str, embed: discord.Embed):
        ch = await self._get_channel(guild_id, log_type)
        if not ch:
            return
        embed.color = LOG_COLORS.get(log_type, 0x5865F2)
        embed.timestamp = datetime.now(timezone.utc)
        embed.set_footer(text=f"Zyn Advanced Logs  •  {LOG_TYPES[log_type][0]}")
        try:
            await ch.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            pass

    # ── Cog load / ready ─────────────────────────────────────────────────────

    def _register_log_subcommands(self):
        """Attach all sub-commands to self.log_group at init time."""

        # ── /log status ───────────────────────────────────────────────────────
        @self.log_group.command(name="status", description="📋 View all configured log channels for this server.")
        async def log_status(interaction: discord.Interaction):
            if not await self._admin_check(interaction):
                return await interaction.response.send_message(
                    f"{CROSS} You need **Administrator** permission to use this.", ephemeral=True
                )
            guild_cfg = self._cache.get(interaction.guild_id, {})
            enabled, disabled = [], []
            for ltype, (lname, lemoji) in LOG_TYPES.items():
                ch_id = guild_cfg.get(ltype)
                if ch_id:
                    enabled.append(f"{lemoji} **{lname}** → <#{ch_id}>")
                else:
                    disabled.append(f"{DISABLED} **{lname}**")
            embed = discord.Embed(title="📋 Advanced Logging — Status", color=0x5865F2, timestamp=datetime.now(timezone.utc))
            embed.set_thumbnail(url=interaction.guild.icon.url if interaction.guild.icon else None)
            if enabled:
                embed.add_field(name=f"{ENABLED} Active ({len(enabled)})", value="\n".join(enabled), inline=False)
            if disabled:
                embed.add_field(name=f"{DISABLED} Inactive ({len(disabled)})", value="\n".join(disabled), inline=False)
            if not enabled and not disabled:
                embed.description = "No log channels configured yet. Use `/log <type>` to set them up."
            embed.set_footer(text="Zyn Advanced Logs  •  Use /log <type> to configure each channel.")
            await interaction.response.send_message(embed=embed, ephemeral=True)

        # ── /log disable ─────────────────────────────────────────────────────
        @self.log_group.command(name="disable", description="🔕 Disable a specific log type.")
        @app_commands.describe(log_type="Which log type to disable")
        @app_commands.choices(log_type=[
            app_commands.Choice(name=f"{v[1]} {v[0]}", value=k)
            for k, v in LOG_TYPES.items()
        ])
        async def log_disable(interaction: discord.Interaction, log_type: str):
            if not await self._admin_check(interaction):
                return await interaction.response.send_message(
                    f"{CROSS} You need **Administrator** permission.", ephemeral=True
                )
            await self._remove_channel(interaction.guild_id, log_type)
            lname, lemoji = LOG_TYPES[log_type]
            await interaction.response.send_message(
                f"{CHECK} **{lemoji} {lname}** logging has been **disabled**.", ephemeral=True
            )

        # ── /log disable-all ─────────────────────────────────────────────────
        @self.log_group.command(name="disable-all", description="🚫 Disable ALL logging for this server.")
        async def log_disable_all(interaction: discord.Interaction):
            if not await self._admin_check(interaction):
                return await interaction.response.send_message(
                    f"{CROSS} You need **Administrator** permission.", ephemeral=True
                )
            await interaction.response.defer(ephemeral=True)
            for ltype in list(self._cache.get(interaction.guild_id, {}).keys()):
                await self._remove_channel(interaction.guild_id, ltype)
            await interaction.followup.send(
                f"{CHECK} All advanced logging has been **disabled** for this server.", ephemeral=True
            )

        async def _setup_cmd_inner(interaction: discord.Interaction, log_type: str, channel):
            if not await self._admin_check(interaction):
                return await interaction.response.send_message(
                    f"{CROSS} You need **Administrator** permission.", ephemeral=True
                )
            await interaction.response.defer(ephemeral=True)
            ch = await self._ensure_channel(interaction.guild, log_type, channel)
            if not ch:
                return await interaction.followup.send(
                    f"{CROSS} Couldn't create or access a channel. Make sure I have **Manage Channels** permission.",
                    ephemeral=True
                )
            lname, lemoji = LOG_TYPES[log_type]
            action = "set to" if channel else "auto-created as"
            await interaction.followup.send(
                f"{CHECK} **{lemoji} {lname}** logs will now be sent to {ch.mention} *(channel {action} {ch.mention})*.",
                ephemeral=True
            )

        # ── Per-type setup commands ───────────────────────────────────────────
        per_type_cmds = [
            ("member-join",    "member_join",    "📥 Set the log channel for members joining the server."),
            ("member-leave",   "member_leave",   "📤 Set the log channel for members leaving the server."),
            ("member-update",  "member_update",  "✏️ Set the log channel for member updates."),
            ("member-ban",     "member_ban",     "🔨 Set the log channel for member bans."),
            ("member-unban",   "member_unban",   "🔓 Set the log channel for member unbans."),
            ("voice",          "voice_state",    "🔊 Set the log channel for voice activity."),
            ("message-delete", "message_delete", "🗑️ Set the log channel for deleted messages."),
            ("message-edit",   "message_edit",   "📝 Set the log channel for edited messages."),
            ("channel-create", "channel_create", "➕ Set the log channel for channel creations."),
            ("channel-delete", "channel_delete", "➖ Set the log channel for channel deletions."),
            ("channel-update", "channel_update", "🔧 Set the log channel for channel updates."),
            ("role-create",    "role_create",    "🏷️ Set the log channel for role creations."),
            ("role-delete",    "role_delete",    "🗑️ Set the log channel for role deletions."),
            ("role-update",    "role_update",    "🔧 Set the log channel for role updates."),
            ("server-update",  "server_update",  "⚙️ Set the log channel for server setting changes."),
            ("invite-create",  "invite_create",  "🔗 Set the log channel for invite creations."),
            ("invite-delete",  "invite_delete",  "❌ Set the log channel for invite deletions."),
        ]

        def _make_setup_cmd(ltype: str):
            @app_commands.describe(channel="Log channel (leave empty to auto-create one)")
            async def _cmd(interaction: discord.Interaction, channel: discord.TextChannel = None):
                await _setup_cmd_inner(interaction, ltype, channel)
            return _cmd

        for cmd_name, log_type_key, desc in per_type_cmds:
            fn = _make_setup_cmd(log_type_key)
            fn.__name__ = cmd_name.replace("-", "_")
            self.log_group.command(name=cmd_name, description=desc)(fn)

    async def cog_load(self):
        """Register the slash group with the bot tree when the cog loads."""
        self.bot.tree.remove_command("log")
        self.bot.tree.add_command(self.log_group)

    async def cog_unload(self):
        self.bot.tree.remove_command("log")

    @commands.Cog.listener()
    async def on_ready(self):
        await self._init_db()
        await self._load_cache()

    # ── Permission check ─────────────────────────────────────────────────────

    async def _admin_check(self, interaction: discord.Interaction) -> bool:
        member = interaction.user
        if not isinstance(member, discord.Member):
            return False
        return (
            member.guild_permissions.administrator
            or member.id == interaction.guild.owner_id
            or await self.bot.is_owner(member)
        )

    # ═══════════════════════════════════════════════════════════════════════════
    #  EVENT LISTENERS
    # ═══════════════════════════════════════════════════════════════════════════

    # ── Member Join ───────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        embed = discord.Embed(title="📥 Member Joined")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member",          value=f"{member.mention} (`{member}`)", inline=True)
        embed.add_field(name="ID",              value=f"`{member.id}`",                 inline=True)
        embed.add_field(name="Account Created", value=f"<t:{int(member.created_at.timestamp())}:R>", inline=True)
        embed.add_field(name="Member Count",    value=f"`{member.guild.member_count}`", inline=True)
        await self._log(member.guild.id, "member_join", embed)

    # ── Member Leave ──────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        embed = discord.Embed(title="📤 Member Left")
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"`{member}`",    inline=True)
        embed.add_field(name="ID",     value=f"`{member.id}`", inline=True)
        roles = [r.mention for r in member.roles if r.name != "@everyone"]
        embed.add_field(
            name=f"Roles ({len(roles)})",
            value=" ".join(roles[:10]) or "*None*",
            inline=False
        )
        embed.add_field(
            name="Joined Server",
            value=f"<t:{int(member.joined_at.timestamp())}:R>" if member.joined_at else "*Unknown*",
            inline=True
        )
        await self._log(member.guild.id, "member_leave", embed)

    # ── Member Update ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        changes = []

        if before.nick != after.nick:
            changes.append(f"**Nickname:** `{before.nick or 'None'}` → `{after.nick or 'None'}`")

        added_roles   = [r for r in after.roles  if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]
        if added_roles:
            changes.append(f"**Roles Added:** {' '.join(r.mention for r in added_roles)}")
        if removed_roles:
            changes.append(f"**Roles Removed:** {' '.join(r.mention for r in removed_roles)}")

        if before.timed_out_until != after.timed_out_until:
            if after.timed_out_until:
                changes.append(f"**Timed Out Until:** <t:{int(after.timed_out_until.timestamp())}:F>")
            else:
                changes.append("**Timeout Removed**")

        if not changes:
            return

        embed = discord.Embed(title="✏️ Member Updated")
        embed.set_thumbnail(url=after.display_avatar.url)
        embed.add_field(name="Member",  value=f"{after.mention} (`{after}`)", inline=True)
        embed.add_field(name="ID",      value=f"`{after.id}`",                inline=True)
        embed.add_field(name="Changes", value="\n".join(changes),             inline=False)
        await self._log(after.guild.id, "member_update", embed)

    # ── Member Ban ────────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔨 Member Banned")
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=True)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.ban):
                if entry.target.id == user.id:
                    embed.add_field(name="Reason",    value=entry.reason or "*No reason*", inline=True)
                    embed.add_field(name="Banned By", value=f"`{entry.user}`",             inline=True)
                    break
        except discord.Forbidden:
            pass
        await self._log(guild.id, "member_ban", embed)

    # ── Member Unban ──────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User):
        embed = discord.Embed(title="🔓 Member Unbanned")
        embed.set_thumbnail(url=user.display_avatar.url)
        embed.add_field(name="User", value=f"`{user}` (`{user.id}`)", inline=True)
        try:
            async for entry in guild.audit_logs(limit=5, action=discord.AuditLogAction.unban):
                if entry.target.id == user.id:
                    embed.add_field(name="Unbanned By", value=f"`{entry.user}`", inline=True)
                    break
        except discord.Forbidden:
            pass
        await self._log(guild.id, "member_unban", embed)

    # ── Voice State ───────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState
    ):
        embed = discord.Embed()
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.add_field(name="Member", value=f"{member.mention} (`{member}`)", inline=True)
        embed.add_field(name="ID",     value=f"`{member.id}`",                 inline=True)

        if before.channel is None and after.channel:
            embed.title = "🔊 Joined Voice Channel"
            embed.add_field(name="Channel", value=after.channel.mention, inline=True)

        elif before.channel and after.channel is None:
            embed.title = "🔇 Left Voice Channel"
            embed.add_field(name="Channel", value=before.channel.mention, inline=True)

        elif before.channel and after.channel and before.channel != after.channel:
            embed.title = "🔀 Moved Voice Channels"
            embed.add_field(name="From", value=before.channel.mention, inline=True)
            embed.add_field(name="To",   value=after.channel.mention,  inline=True)

        else:
            # Mute / deafen / stream state changes
            changes = []
            if before.self_mute  != after.self_mute:
                changes.append(f"**Self Mute:** {'On' if after.self_mute else 'Off'}")
            if before.self_deaf  != after.self_deaf:
                changes.append(f"**Self Deaf:** {'On' if after.self_deaf else 'Off'}")
            if before.mute       != after.mute:
                changes.append(f"**Server Mute:** {'On' if after.mute else 'Off'}")
            if before.deaf       != after.deaf:
                changes.append(f"**Server Deaf:** {'On' if after.deaf else 'Off'}")
            if before.self_stream != after.self_stream:
                changes.append(f"**Streaming:** {'Started' if after.self_stream else 'Stopped'}")
            if not changes:
                return
            embed.title = "🎙️ Voice State Changed"
            embed.add_field(name="Changes", value="\n".join(changes), inline=False)
            if after.channel:
                embed.add_field(name="Channel", value=after.channel.mention, inline=True)

        await self._log(member.guild.id, "voice_state", embed)

    # ── Message Delete ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message):
        if not message.guild or message.author.bot:
            return
        embed = discord.Embed(title="🗑️ Message Deleted")
        embed.set_thumbnail(url=message.author.display_avatar.url)
        embed.add_field(name="Author",  value=f"{message.author.mention} (`{message.author}`)", inline=True)
        embed.add_field(name="Channel", value=message.channel.mention,                          inline=True)
        content = message.content[:1000] if message.content else "*No text content*"
        embed.add_field(name="Content", value=f"```{content}```", inline=False)
        if message.attachments:
            embed.add_field(
                name=f"Attachments ({len(message.attachments)})",
                value="\n".join(a.filename for a in message.attachments),
                inline=False
            )
        await self._log(message.guild.id, "message_delete", embed)

    # ── Message Edit ──────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message):
        if not after.guild or after.author.bot:
            return
        if before.content == after.content:
            return
        embed = discord.Embed(title="📝 Message Edited")
        embed.set_thumbnail(url=after.author.display_avatar.url)
        embed.add_field(name="Author",  value=f"{after.author.mention} (`{after.author}`)", inline=True)
        embed.add_field(name="Channel", value=after.channel.mention,                        inline=True)
        embed.add_field(name="Jump",    value=f"[Go to message]({after.jump_url})",         inline=True)
        embed.add_field(name="Before",  value=f"```{before.content[:500] or 'Empty'}```",   inline=False)
        embed.add_field(name="After",   value=f"```{after.content[:500]  or 'Empty'}```",   inline=False)
        await self._log(after.guild.id, "message_edit", embed)

    # ── Channel Create ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(title="➕ Channel Created")
        embed.add_field(name="Name",     value=f"`{channel.name}`",                                              inline=True)
        embed.add_field(name="Type",     value=f"`{str(channel.type).replace('_', ' ').title()}`",               inline=True)
        embed.add_field(name="Category", value=f"`{channel.category}`" if channel.category else "*None*",        inline=True)
        embed.add_field(name="ID",       value=f"`{channel.id}`",                                                inline=True)
        try:
            async for entry in channel.guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_create):
                embed.add_field(name="Created By", value=f"`{entry.user}`", inline=True)
                break
        except discord.Forbidden:
            pass
        await self._log(channel.guild.id, "channel_create", embed)

    # ── Channel Delete ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: discord.abc.GuildChannel):
        embed = discord.Embed(title="➖ Channel Deleted")
        embed.add_field(name="Name",     value=f"`{channel.name}`",                                        inline=True)
        embed.add_field(name="Type",     value=f"`{str(channel.type).replace('_', ' ').title()}`",         inline=True)
        embed.add_field(name="Category", value=f"`{channel.category}`" if channel.category else "*None*",  inline=True)
        embed.add_field(name="ID",       value=f"`{channel.id}`",                                          inline=True)
        try:
            async for entry in channel.guild.audit_logs(limit=3, action=discord.AuditLogAction.channel_delete):
                embed.add_field(name="Deleted By", value=f"`{entry.user}`", inline=True)
                break
        except discord.Forbidden:
            pass
        await self._log(channel.guild.id, "channel_delete", embed)

    # ── Channel Update ────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: discord.abc.GuildChannel, after: discord.abc.GuildChannel):
        changes = []
        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if getattr(before, "topic", None) != getattr(after, "topic", None):
            changes.append(f"**Topic:** `{getattr(before, 'topic', None) or 'None'}` → `{getattr(after, 'topic', None) or 'None'}`")
        if getattr(before, "slowmode_delay", None) != getattr(after, "slowmode_delay", None):
            changes.append(f"**Slowmode:** `{getattr(before, 'slowmode_delay', 0)}s` → `{getattr(after, 'slowmode_delay', 0)}s`")
        if getattr(before, "nsfw", None) != getattr(after, "nsfw", None):
            changes.append(f"**NSFW:** `{getattr(before, 'nsfw', False)}` → `{getattr(after, 'nsfw', False)}`")
        if before.category != after.category:
            changes.append(f"**Category:** `{before.category}` → `{after.category}`")
        if not changes:
            return

        embed = discord.Embed(title="🔧 Channel Updated")
        embed.add_field(
            name="Channel",
            value=after.mention if isinstance(after, discord.TextChannel) else f"`{after.name}`",
            inline=True
        )
        embed.add_field(name="ID",      value=f"`{after.id}`",       inline=True)
        embed.add_field(name="Changes", value="\n".join(changes),    inline=False)
        await self._log(after.guild.id, "channel_update", embed)

    # ── Role Create ───────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role):
        embed = discord.Embed(title="🏷️ Role Created")
        embed.add_field(name="Name",        value=f"`{role.name}`",        inline=True)
        embed.add_field(name="Color",       value=f"`{role.color}`",       inline=True)
        embed.add_field(name="ID",          value=f"`{role.id}`",          inline=True)
        embed.add_field(name="Mentionable", value=f"`{role.mentionable}`", inline=True)
        embed.add_field(name="Hoisted",     value=f"`{role.hoist}`",       inline=True)
        try:
            async for entry in role.guild.audit_logs(limit=3, action=discord.AuditLogAction.role_create):
                embed.add_field(name="Created By", value=f"`{entry.user}`", inline=True)
                break
        except discord.Forbidden:
            pass
        await self._log(role.guild.id, "role_create", embed)

    # ── Role Delete ───────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role):
        embed = discord.Embed(title="🗑️ Role Deleted")
        embed.add_field(name="Name",    value=f"`{role.name}`",        inline=True)
        embed.add_field(name="Color",   value=f"`{role.color}`",       inline=True)
        embed.add_field(name="ID",      value=f"`{role.id}`",          inline=True)
        embed.add_field(name="Members", value=f"`{len(role.members)}`", inline=True)
        try:
            async for entry in role.guild.audit_logs(limit=3, action=discord.AuditLogAction.role_delete):
                embed.add_field(name="Deleted By", value=f"`{entry.user}`", inline=True)
                break
        except discord.Forbidden:
            pass
        await self._log(role.guild.id, "role_delete", embed)

    # ── Role Update ───────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role):
        changes = []
        if before.name        != after.name:        changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color       != after.color:       changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.hoist       != after.hoist:       changes.append(f"**Hoisted:** `{before.hoist}` → `{after.hoist}`")
        if before.mentionable != after.mentionable: changes.append(f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`")
        if before.permissions != after.permissions: changes.append("**Permissions changed**")
        if not changes:
            return

        embed = discord.Embed(title="🔧 Role Updated")
        embed.add_field(name="Role",    value=f"{after.mention} (`{after.name}`)", inline=True)
        embed.add_field(name="ID",      value=f"`{after.id}`",                     inline=True)
        embed.add_field(name="Changes", value="\n".join(changes),                  inline=False)
        await self._log(after.guild.id, "role_update", embed)

    # ── Server Update ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild):
        changes = []
        if before.name                   != after.name:                   changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.icon                   != after.icon:                   changes.append("**Icon changed**")
        if before.banner                 != after.banner:                 changes.append("**Banner changed**")
        if before.description            != after.description:            changes.append(f"**Description:** `{before.description or 'None'}` → `{after.description or 'None'}`")
        if before.verification_level     != after.verification_level:     changes.append(f"**Verification Level:** `{before.verification_level}` → `{after.verification_level}`")
        if before.explicit_content_filter != after.explicit_content_filter: changes.append(f"**Content Filter:** `{before.explicit_content_filter}` → `{after.explicit_content_filter}`")
        if before.default_notifications  != after.default_notifications:  changes.append(f"**Notifications:** `{before.default_notifications}` → `{after.default_notifications}`")
        if not changes:
            return

        embed = discord.Embed(title="⚙️ Server Updated")
        if after.icon:
            embed.set_thumbnail(url=after.icon.url)
        embed.add_field(name="Server",  value=f"`{after.name}`",  inline=True)
        embed.add_field(name="Changes", value="\n".join(changes), inline=False)
        await self._log(after.id, "server_update", embed)

    # ── Invite Create ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_invite_create(self, invite: discord.Invite):
        embed = discord.Embed(title="🔗 Invite Created")
        embed.add_field(name="Code",       value=f"`{invite.code}`",                                               inline=True)
        embed.add_field(name="Channel",    value=invite.channel.mention if invite.channel else "*Unknown*",        inline=True)
        embed.add_field(name="Created By", value=f"`{invite.inviter}`" if invite.inviter else "*Unknown*",         inline=True)
        embed.add_field(name="Max Uses",   value=f"`{invite.max_uses or '∞'}`",                                    inline=True)
        embed.add_field(
            name="Expires",
            value=f"<t:{int(invite.expires_at.timestamp())}:R>" if invite.expires_at else "`Never`",
            inline=True
        )
        await self._log(invite.guild.id, "invite_create", embed)

    # ── Invite Delete ─────────────────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_invite_delete(self, invite: discord.Invite):
        embed = discord.Embed(title="❌ Invite Deleted")
        embed.add_field(name="Code",    value=f"`{invite.code}`",                                         inline=True)
        embed.add_field(name="Channel", value=invite.channel.mention if invite.channel else "*Unknown*",  inline=True)
        await self._log(invite.guild.id, "invite_delete", embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(AdvancedLog(bot))
