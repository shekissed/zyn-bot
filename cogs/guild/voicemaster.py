import discord
from discord.ext import commands, tasks
import aiosqlite
import os
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import CHECK, CROSS, LOCK, UNLOCK, GHOST, UNGHOST, CROWN

DB_PATH = "db/voicemaster.db"
os.makedirs("db", exist_ok=True)

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS voicemaster (
                guild_id INTEGER PRIMARY KEY,
                category_id INTEGER,
                interface_id INTEGER,
                joinvc_id INTEGER,
                panel_msg_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vc_owners (
                channel_id INTEGER PRIMARY KEY,
                owner_id INTEGER
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vc_trusted (
                channel_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vc_blocked (
                channel_id INTEGER,
                user_id INTEGER,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        await db.commit()

from discord import ui

# ─────────────────────────────────────────────
#  Modals
# ─────────────────────────────────────────────

class RenameModal(ui.Modal, title="Rename Your Voice Channel"):
    name_input = ui.TextInput(label="Channel Name", placeholder="Enter new name...", min_length=1, max_length=15)
    def __init__(self, vc):
        super().__init__()
        self.vc = vc
    async def on_submit(self, interaction: discord.Interaction):
        await self.vc.edit(name=self.name_input.value)
        await interaction.response.send_message(f"{CHECK} Channel renamed to **{self.name_input.value}**.", ephemeral=True)

class LimitModal(ui.Modal, title="Set User Limit"):
    limit_input = ui.TextInput(label="Limit (0-99)", placeholder="0 = No limit", min_length=1, max_length=2)
    def __init__(self, vc):
        super().__init__()
        self.vc = vc
    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.limit_input.value)
            if 0 <= val <= 99:
                await self.vc.edit(user_limit=val)
                await interaction.response.send_message(f"{CHECK} User limit set to **{val}**.", ephemeral=True)
            else:
                await interaction.response.send_message(f"{CROSS} Enter a number between 0 and 99.", ephemeral=True)
        except ValueError:
            await interaction.response.send_message(f"{CROSS} Invalid number.", ephemeral=True)

# ─────────────────────────────────────────────
#  Member select (for kick/trust/untrust/block/unblock/transfer/invite)
# ─────────────────────────────────────────────

def _vc_member_options(vc: discord.VoiceChannel, exclude_id: int) -> list[discord.SelectOption]:
    return [
        discord.SelectOption(label=m.display_name, value=str(m.id))
        for m in vc.members if m.id != exclude_id
    ]

def _guild_member_options(guild: discord.Guild, exclude_id: int) -> list[discord.SelectOption]:
    """Used for invite — all online/idle members not in the VC."""
    return [
        discord.SelectOption(label=m.display_name, value=str(m.id))
        for m in guild.members
        if m.id != exclude_id and not m.bot and m.status != discord.Status.offline
    ][:25]

class MemberSelectView(ui.View):
    def __init__(self, options: list[discord.SelectOption], action: str, vc, callback_fn):
        super().__init__(timeout=30)
        self.callback_fn = callback_fn
        select = ui.Select(
            placeholder=f"Choose a member to {action}...",
            options=options if options else [discord.SelectOption(label="No members available", value="none")]
        )
        select.callback = self._on_select
        self.select = select
        self.add_item(select)
        self.vc = vc

    async def _on_select(self, interaction: discord.Interaction):
        if self.select.values[0] == "none":
            return await interaction.response.send_message(f"{CROSS} No valid members to choose from.", ephemeral=True)
        member = interaction.guild.get_member(int(self.select.values[0]))
        if not member:
            return await interaction.response.send_message(f"{CROSS} Member not found.", ephemeral=True)
        await self.callback_fn(interaction, self.vc, member)

# ─────────────────────────────────────────────
#  Region select
# ─────────────────────────────────────────────

REGIONS = [
    ("Automatic", ""),
    ("Brazil", "brazil"),
    ("Hong Kong", "hongkong"),
    ("India", "india"),
    ("Japan", "japan"),
    ("Rotterdam", "rotterdam"),
    ("Russia", "russia"),
    ("Singapore", "singapore"),
    ("South Africa", "southafrica"),
    ("Sydney", "sydney"),
    ("US Central", "us-central"),
    ("US East", "us-east"),
    ("US South", "us-south"),
    ("US West", "us-west"),
]

class RegionSelectView(ui.View):
    def __init__(self, vc):
        super().__init__(timeout=30)
        self.vc = vc
        select = ui.Select(
            placeholder="Choose a region...",
            options=[discord.SelectOption(label=name, value=val or "auto") for name, val in REGIONS]
        )
        select.callback = self._on_select
        self.add_item(select)

    async def _on_select(self, interaction: discord.Interaction):
        val = self.select.values[0]
        region = None if val == "auto" else val
        try:
            await self.vc.edit(rtc_region=region)
            label = next((n for n, v in REGIONS if (v or "auto") == val), val)
            await interaction.response.send_message(f"{CHECK} Region set to **{label}**.", ephemeral=True)
        except Exception:
            await interaction.response.send_message(f"{CROSS} Failed to change region.", ephemeral=True)

# ─────────────────────────────────────────────
#  Main View
# ─────────────────────────────────────────────

class VoiceMasterView(ui.LayoutView):
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot

        container = ui.Container(accent_color=0x525252)
        container.add_item(ui.TextDisplay("## VoiceMaster Interface"))
        container.add_item(ui.Separator())
        container.add_item(ui.MediaGallery(
            discord.MediaGalleryItem(media="https://cdn.discordapp.com/attachments/1396458155902505011/1510548564076527747/IMG_20260531_130856.png?ex=6a1d377a&is=6a1be5fa&hm=a4f0f00e64e1a3862653f10edefef549125f14498a73b06377f5392005fdf770&")
        ))
        self.add_item(container)

        # ── Row 1: Privacy ──────────────────────────────
        row1 = ui.ActionRow()
        for emoji, cid, cb in [
            (LOCK,   "vm_lock",   self.lock_callback),
            (UNLOCK, "vm_unlock", self.unlock_callback),
            (GHOST,  "vm_hide",   self.hide_callback),
            (UNGHOST,"vm_unhide", self.unhide_callback),
        ]:
            btn = ui.Button(emoji=emoji, style=discord.ButtonStyle.gray, custom_id=cid)
            btn.callback = cb
            row1.add_item(btn)
        # Waiting Room toggle
        wr_btn = ui.Button(emoji="<:clock:1509864852288704583>", style=discord.ButtonStyle.gray, custom_id="vm_waitingroom")
        wr_btn.callback = self.waitingroom_callback
        row1.add_item(wr_btn)
        self.add_item(row1)

        # ── Row 2: Channel settings ─────────────────────
        row2 = ui.ActionRow()
        for emoji, cid, cb in [
            ("<:write:1509865378547896350>",   "vm_rename", self.rename_callback),
            ("<:members:1509864852288704583>", "vm_limit",  self.limit_callback),
            ("<:whitecrown:1508476687560741044>", "vm_claim", self.claim_callback),
            ("🌐",                              "vm_region", self.region_callback),
            ("💬",                              "vm_chat",   self.chat_callback),
        ]:
            btn = ui.Button(emoji=emoji, style=discord.ButtonStyle.gray, custom_id=cid)
            btn.callback = cb
            row2.add_item(btn)
        self.add_item(row2)

        # ── Row 3: Trust / Untrust / Invite / Kick / Block ──
        row3 = ui.ActionRow()
        for emoji, cid, cb in [
            ("✅", "vm_trust",   self.trust_callback),
            ("❎", "vm_untrust", self.untrust_callback),
            ("📨", "vm_invite",  self.invite_callback),
            ("👢", "vm_kick",    self.kick_callback),
            ("🚫", "vm_block",   self.block_callback),
        ]:
            btn = ui.Button(emoji=emoji, style=discord.ButtonStyle.gray, custom_id=cid)
            btn.callback = cb
            row3.add_item(btn)
        self.add_item(row3)

        # ── Row 4: Unblock / Transfer / Delete ─────────────
        row4 = ui.ActionRow()
        for emoji, cid, cb, style in [
            ("🔓",                              "vm_unblock",  self.unblock_callback,  discord.ButtonStyle.gray),
            ("🔁",                              "vm_transfer", self.transfer_callback, discord.ButtonStyle.gray),
            ("<:delete:1409553551994261504>",   "vm_delete",   self.delete_callback,   discord.ButtonStyle.danger),
        ]:
            btn = ui.Button(emoji=emoji, style=style, custom_id=cid)
            btn.callback = cb
            row4.add_item(btn)
        self.add_item(row4)

    # ─────────────────────────────────────────────
    #  Shared checks
    # ─────────────────────────────────────────────

    async def _check(self, interaction: discord.Interaction):
        """Returns (vc, owner_id) or (None, None)."""
        member = interaction.user
        if not member.voice or not member.voice.channel:
            await interaction.response.send_message(f"{CROSS} You must be in a voice channel.", ephemeral=True)
            return None, None
        vc = member.voice.channel
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT owner_id FROM vc_owners WHERE channel_id=?", (vc.id,)) as cur:
                row = await cur.fetchone()
        if not row:
            await interaction.response.send_message(f"{CROSS} This is not a managed VoiceMaster channel.", ephemeral=True)
            return None, None
        return vc, row[0]

    async def _owner_check(self, interaction: discord.Interaction):
        """Returns vc if user is owner, else sends error and returns None."""
        vc, owner_id = await self._check(interaction)
        if not vc:
            return None
        if owner_id != interaction.user.id:
            await interaction.response.send_message(f"{CROSS} You don't own this channel.", ephemeral=True)
            return None
        return vc

    def _member_options(self, vc: discord.VoiceChannel, exclude_id: int):
        return _vc_member_options(vc, exclude_id)

    # ─────────────────────────────────────────────
    #  Privacy callbacks
    # ─────────────────────────────────────────────

    async def lock_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        await vc.set_permissions(interaction.guild.default_role, connect=False)
        await interaction.response.send_message(f"{LOCK} Channel locked.", ephemeral=True)

    async def unlock_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        await vc.set_permissions(interaction.guild.default_role, connect=True)
        await interaction.response.send_message(f"{UNLOCK} Channel unlocked.", ephemeral=True)

    async def hide_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        await vc.set_permissions(interaction.guild.default_role, view_channel=False)
        await interaction.response.send_message(f"{GHOST} Channel hidden.", ephemeral=True)

    async def unhide_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        await vc.set_permissions(interaction.guild.default_role, view_channel=True)
        await interaction.response.send_message(f"{UNGHOST} Channel visible.", ephemeral=True)

    async def waitingroom_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        current = vc.overwrites_for(interaction.guild.default_role)
        # Toggle: if they can connect but not speak → waiting room is on; else turn it on
        if current.speak is False:
            await vc.set_permissions(interaction.guild.default_role, speak=None)
            await interaction.response.send_message(f"🔔 Waiting room **disabled**. Members can now speak.", ephemeral=True)
        else:
            await vc.set_permissions(interaction.guild.default_role, speak=False)
            await interaction.response.send_message(f"⏳ Waiting room **enabled**. Members must be unmuted by you to speak.", ephemeral=True)

    # ─────────────────────────────────────────────
    #  Channel settings callbacks
    # ─────────────────────────────────────────────

    async def rename_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        await interaction.response.send_modal(RenameModal(vc))

    async def limit_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        await interaction.response.send_modal(LimitModal(vc))

    async def claim_callback(self, interaction: discord.Interaction):
        vc, owner_id = await self._check(interaction)
        if not vc: return
        if owner_id == interaction.user.id:
            return await interaction.response.send_message(f"{CROSS} You already own this channel.", ephemeral=True)
        owner = interaction.guild.get_member(owner_id)
        if owner and owner in vc.members:
            return await interaction.response.send_message(f"{CROSS} The owner is still in the channel.", ephemeral=True)
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute("UPDATE vc_owners SET owner_id=? WHERE channel_id=?", (interaction.user.id, vc.id))
            await db.commit()
        await interaction.response.send_message(f"{CROWN} You are now the owner of this channel!", ephemeral=True)

    async def region_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        view = RegionSelectView(vc)
        await interaction.response.send_message("🌐 Select a voice region:", view=view, ephemeral=True)

    async def chat_callback(self, interaction: discord.Interaction):
        vc, _ = await self._check(interaction)
        if not vc: return
        # Find any text channel linked to this VC (Discord stage/voice text feature)
        # We'll toggle the VC's text channel visibility for the user
        overwrite = vc.overwrites_for(interaction.user)
        if overwrite.send_messages is False:
            overwrite.send_messages = None
            await vc.set_permissions(interaction.user, overwrite=overwrite)
            await interaction.response.send_message("💬 Chat permissions **restored**.", ephemeral=True)
        else:
            await interaction.response.send_message(
                f"💬 Use the voice channel's built-in text chat directly inside the VC on Discord.",
                ephemeral=True
            )

    # ─────────────────────────────────────────────
    #  Member action callbacks (with select menus)
    # ─────────────────────────────────────────────

    async def trust_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        options = self._member_options(vc, interaction.user.id)
        if not options:
            return await interaction.response.send_message(f"{CROSS} No other members in the channel.", ephemeral=True)

        async def _do(inter, ch, member):
            await ch.set_permissions(member, connect=True, speak=True, view_channel=True)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR IGNORE INTO vc_trusted VALUES (?,?)", (ch.id, member.id))
                await db.commit()
            await inter.response.send_message(f"{CHECK} **{member.display_name}** is now trusted.", ephemeral=True)

        view = MemberSelectView(options, "trust", vc, _do)
        await interaction.response.send_message("✅ Who do you want to trust?", view=view, ephemeral=True)

    async def untrust_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        # Show trusted members only
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM vc_trusted WHERE channel_id=?", (vc.id,)) as cur:
                rows = await cur.fetchall()
        trusted_ids = {r[0] for r in rows}
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in vc.members if m.id in trusted_ids
        ]
        if not options:
            return await interaction.response.send_message(f"{CROSS} No trusted members to remove.", ephemeral=True)

        async def _do(inter, ch, member):
            await ch.set_permissions(member, overwrite=None)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM vc_trusted WHERE channel_id=? AND user_id=?", (ch.id, member.id))
                await db.commit()
            await inter.response.send_message(f"{CHECK} **{member.display_name}** is no longer trusted.", ephemeral=True)

        view = MemberSelectView(options, "untrust", vc, _do)
        await interaction.response.send_message("❎ Who do you want to untrust?", view=view, ephemeral=True)

    async def invite_callback(self, interaction: discord.Interaction):
        vc, _ = await self._check(interaction)
        if not vc: return
        options = _guild_member_options(interaction.guild, interaction.user.id)
        # Filter out people already in VC
        already_in = {m.id for m in vc.members}
        options = [o for o in options if int(o.value) not in already_in][:25]
        if not options:
            return await interaction.response.send_message(f"{CROSS} No available members to invite.", ephemeral=True)

        async def _do(inter, ch, member):
            try:
                invite = await ch.create_invite(max_uses=1, max_age=300, reason=f"VoiceMaster invite by {inter.user}")
                await member.send(f"📨 **{inter.user.display_name}** invited you to join their voice channel!\n{invite.url}")
                await inter.response.send_message(f"{CHECK} Invite sent to **{member.display_name}**.", ephemeral=True)
            except discord.Forbidden:
                await inter.response.send_message(f"{CROSS} Could not DM **{member.display_name}** (DMs may be closed).", ephemeral=True)

        view = MemberSelectView(options, "invite", vc, _do)
        await interaction.response.send_message("📨 Who do you want to invite?", view=view, ephemeral=True)

    async def kick_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        options = self._member_options(vc, interaction.user.id)
        if not options:
            return await interaction.response.send_message(f"{CROSS} No other members in the channel.", ephemeral=True)

        async def _do(inter, ch, member):
            try:
                await member.move_to(None)
                await inter.response.send_message(f"{CHECK} **{member.display_name}** was kicked from the channel.", ephemeral=True)
            except discord.Forbidden:
                await inter.response.send_message(f"{CROSS} Missing permission to move that member.", ephemeral=True)

        view = MemberSelectView(options, "kick", vc, _do)
        await interaction.response.send_message("👢 Who do you want to kick?", view=view, ephemeral=True)

    async def block_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        options = self._member_options(vc, interaction.user.id)
        if not options:
            return await interaction.response.send_message(f"{CROSS} No other members in the channel.", ephemeral=True)

        async def _do(inter, ch, member):
            await ch.set_permissions(member, connect=False, view_channel=False)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR IGNORE INTO vc_blocked VALUES (?,?)", (ch.id, member.id))
                await db.commit()
            try:
                await member.move_to(None)
            except discord.Forbidden:
                pass
            await inter.response.send_message(f"🚫 **{member.display_name}** has been blocked from the channel.", ephemeral=True)

        view = MemberSelectView(options, "block", vc, _do)
        await interaction.response.send_message("🚫 Who do you want to block?", view=view, ephemeral=True)

    async def unblock_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT user_id FROM vc_blocked WHERE channel_id=?", (vc.id,)) as cur:
                rows = await cur.fetchall()
        blocked_ids = {r[0] for r in rows}
        options = [
            discord.SelectOption(label=str(interaction.guild.get_member(uid) or uid), value=str(uid))
            for uid in blocked_ids
        ]
        options = [o for o in options if o][:25]
        if not options:
            return await interaction.response.send_message(f"{CROSS} No blocked members.", ephemeral=True)

        async def _do(inter, ch, member):
            await ch.set_permissions(member, overwrite=None)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM vc_blocked WHERE channel_id=? AND user_id=?", (ch.id, member.id))
                await db.commit()
            await inter.response.send_message(f"🔓 **{member.display_name}** has been unblocked.", ephemeral=True)

        view = MemberSelectView(options, "unblock", vc, _do)
        await interaction.response.send_message("🔓 Who do you want to unblock?", view=view, ephemeral=True)

    async def transfer_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return
        options = self._member_options(vc, interaction.user.id)
        if not options:
            return await interaction.response.send_message(f"{CROSS} No other members in the channel to transfer to.", ephemeral=True)

        async def _do(inter, ch, member):
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("UPDATE vc_owners SET owner_id=? WHERE channel_id=?", (member.id, ch.id))
                await db.commit()
            await inter.response.send_message(f"{CROWN} Ownership transferred to **{member.display_name}**.", ephemeral=True)

        view = MemberSelectView(options, "transfer ownership to", vc, _do)
        await interaction.response.send_message("🔁 Who do you want to transfer ownership to?", view=view, ephemeral=True)

    async def delete_callback(self, interaction: discord.Interaction):
        vc = await self._owner_check(interaction)
        if not vc: return

        class ConfirmView(ui.View):
            def __init__(self):
                super().__init__(timeout=15)
                self.confirmed = False

            @ui.button(label="Yes, delete it", style=discord.ButtonStyle.danger)
            async def confirm(self, inter: discord.Interaction, button):
                self.confirmed = True
                self.stop()
                try:
                    await vc.delete()
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("DELETE FROM vc_owners WHERE channel_id=?", (vc.id,))
                        await db.commit()
                    await inter.response.send_message(f"🗑️ Channel deleted.", ephemeral=True)
                except discord.Forbidden:
                    await inter.response.send_message(f"{CROSS} Missing permission to delete the channel.", ephemeral=True)

            @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
            async def cancel(self, inter: discord.Interaction, button):
                self.stop()
                await inter.response.send_message("Cancelled.", ephemeral=True)

        await interaction.response.send_message(
            "⚠️ Are you sure you want to **delete** this channel? This cannot be undone.",
            view=ConfirmView(),
            ephemeral=True
        )


# ─────────────────────────────────────────────
#  Cog
# ─────────────────────────────────────────────

class VoiceMaster(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        bot.add_view(VoiceMasterView(bot))
        self.cleanup_task.start()

    @commands.group(name="voicemaster", aliases=["vm"], invoke_without_command=True)
    async def voicemaster(self, ctx):
        await ctx.send("Use `;vm setup` or `;vm remove`.")

    @voicemaster.command(name="setup")
    @commands.has_permissions(administrator=True)
    async def setup(self, ctx):
        guild = ctx.guild
        required_perms = discord.Permissions(manage_channels=True, move_members=True, manage_permissions=True)
        if not guild.me.guild_permissions >= required_perms:
            return await ctx.send(f"{CROSS} Bot lacks required permissions: Manage Channels, Move Members, Manage Permissions.")
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT category_id FROM voicemaster WHERE guild_id=?", (guild.id,)) as cur:
                if await cur.fetchone():
                    return await ctx.send(f"{CROSS} VoiceMaster is already set up.")
        try:
            category  = await guild.create_category("Zyn | VoiceMaster")
            joinvc    = await category.create_voice_channel("Join 2 Create")
            interface = await category.create_text_channel(
                "interface",
                overwrites={guild.default_role: discord.PermissionOverwrite(send_messages=False)}
            )
            view = VoiceMasterView(self.bot)
            msg  = await interface.send(view=view)
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("INSERT OR REPLACE INTO voicemaster VALUES (?,?,?,?,?)",
                                 (guild.id, category.id, interface.id, joinvc.id, msg.id))
                await db.commit()
            await ctx.send(f"{CHECK} VoiceMaster setup complete.")
        except discord.Forbidden:
            await ctx.send(f"{CROSS} Bot lacks permission to create channels.")
        except Exception as e:
            await ctx.send(f"{CROSS} An error occurred: {e}")

    @voicemaster.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def remove(self, ctx):
        guild = ctx.guild
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT category_id, interface_id, joinvc_id FROM voicemaster WHERE guild_id=?", (guild.id,)) as cur:
                row = await cur.fetchone()
            if not row:
                return await ctx.send(f"{CROSS} VoiceMaster is not set up.")
            category_id, interface_id, joinvc_id = row
        try:
            for cid in [interface_id, joinvc_id, category_id]:
                ch = guild.get_channel(cid)
                if ch:
                    await ch.delete()
            async with aiosqlite.connect(DB_PATH) as db:
                await db.execute("DELETE FROM voicemaster WHERE guild_id=?", (guild.id,))
                await db.commit()
            await ctx.send(f"{CHECK} VoiceMaster removed.")
        except discord.Forbidden:
            await ctx.send(f"{CROSS} Bot lacks permission to delete channels.")

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        if before.channel == after.channel:
            return
        if after.channel:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT joinvc_id, category_id FROM voicemaster WHERE guild_id=?", (member.guild.id,)) as cur:
                    row = await cur.fetchone()
            if row and after.channel.id == row[0]:
                category = member.guild.get_channel(row[1])
                if not category:
                    return
                try:
                    new_vc = await category.create_voice_channel(f"{member.name}'s VC")
                    await member.move_to(new_vc)
                    async with aiosqlite.connect(DB_PATH) as db:
                        await db.execute("INSERT OR REPLACE INTO vc_owners VALUES (?,?)", (new_vc.id, member.id))
                        await db.commit()
                except (discord.Forbidden, Exception):
                    return
        if before.channel:
            async with aiosqlite.connect(DB_PATH) as db:
                async with db.execute("SELECT owner_id FROM vc_owners WHERE channel_id=?", (before.channel.id,)) as cur:
                    row = await cur.fetchone()
                if row and len(before.channel.members) == 0:
                    try:
                        await before.channel.delete()
                        await db.execute("DELETE FROM vc_owners WHERE channel_id=?", (before.channel.id,))
                        await db.execute("DELETE FROM vc_trusted WHERE channel_id=?", (before.channel.id,))
                        await db.execute("DELETE FROM vc_blocked WHERE channel_id=?", (before.channel.id,))
                        await db.commit()
                    except (discord.Forbidden, Exception):
                        pass

    @tasks.loop(hours=1.0)
    async def cleanup_task(self):
        async with aiosqlite.connect(DB_PATH) as db:
            async with db.execute("SELECT channel_id FROM vc_owners") as cur:
                rows = await cur.fetchall()
            for (channel_id,) in rows:
                channel = self.bot.get_channel(channel_id)
                if not channel or len(channel.members) == 0:
                    try:
                        if channel:
                            await channel.delete()
                        await db.execute("DELETE FROM vc_owners WHERE channel_id=?", (channel_id,))
                        await db.execute("DELETE FROM vc_trusted WHERE channel_id=?", (channel_id,))
                        await db.execute("DELETE FROM vc_blocked WHERE channel_id=?", (channel_id,))
                        await db.commit()
                    except Exception:
                        pass

    def cog_unload(self):
        self.cleanup_task.stop()


async def setup(bot):
    await init_db()
    await bot.add_cog(VoiceMaster(bot))
