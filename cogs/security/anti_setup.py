"""
antinuke_setup.py
Handles: .antinuke enable/disable + the interactive filter enable UI
Similar style to ZEON's antinuke panel but with your bot's branding.
"""

import discord
from discord.ext import commands
import aiosqlite
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import (
    CHECK, CROSS, ENABLED, DISABLED, GEARS, INFO,
    AN_SHIELD, AN_ARROW, AN_WARN, AN_LOCK_CLOSED,
    AN_RECOVERY, AN_LOG
)

# All supported antinuke filter keys and their display names
FILTER_META = {
    "ban":        "Ban",
    "kick":       "Kick",
    "prune":      "Prune",
    "memup":      "Member Update",
    "rlcr":       "Role Create",
    "rldl":       "Role Delete",
    "rlup":       "Role Update",
    "chcr":       "Channel Create",
    "chdl":       "Channel Delete",
    "chup":       "Channel Update",
    "webhookcr":  "Webhook Create",
    "webhookdl":  "Webhook Delete",
    "webhookup":  "Webhook Update",
    "botadd":     "Bot Add",
    "serverup":   "Guild Update",
    "meneve":     "Mention Spam",
}

# Filters split into two rows for the embed display
FILTERS_ROW1 = ["ban", "kick", "prune", "memup", "rlcr", "rldl", "rlup", "chcr"]
FILTERS_ROW2 = ["chdl", "chup", "webhookcr", "webhookdl", "webhookup", "botadd", "serverup", "meneve"]


def _toggle_emoji(state: bool) -> str:
    return ENABLED if state else DISABLED


def _build_filter_display(enabled_map: dict) -> str:
    """Build the Filters [1] / Filters [2] text block."""
    def line(key):
        return f"{AN_ARROW} **{FILTER_META[key]} :** {_toggle_emoji(enabled_map.get(key, False))}"

    block1 = "\n".join(line(k) for k in FILTERS_ROW1)
    block2 = "\n".join(line(k) for k in FILTERS_ROW2)
    return f"**Filters [1]:**\n{block1}\n\n**Filters [2]:**\n{block2}"


class FilterEnableSelect(discord.ui.Select):
    def __init__(self, db, guild_id: int, enabled_map: dict):
        self.db = db
        self.guild_id = guild_id
        self.enabled_map = dict(enabled_map)

        options = [
            discord.SelectOption(
                label=FILTER_META[k],
                description=f"Enable the {FILTER_META[k].lower()} filter.",
                value=k,
                default=enabled_map.get(k, False)
            )
            for k in FILTER_META
        ]
        super().__init__(
            placeholder="Select filters to enable…",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id="enable_filters_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        for key in FILTER_META:
            self.enabled_map[key] = key in selected

        # Persist to DB
        cols = ", ".join(f"{k} = ?" for k in FILTER_META)
        vals = [self.enabled_map[k] for k in FILTER_META] + [self.guild_id]
        await self.db.execute(
            f"INSERT OR REPLACE INTO antinuke_filters (guild_id, {', '.join(FILTER_META)}) "
            f"VALUES ({', '.join(['?'] * (len(FILTER_META) + 1))})",
            [self.guild_id] + [self.enabled_map[k] for k in FILTER_META]
        )
        await self.db.commit()

        embed = interaction.message.embeds[0]
        embed.description = _build_filter_display(self.enabled_map)
        await interaction.response.edit_message(embed=embed, view=self.view)


class FilterEnableView(discord.ui.View):
    def __init__(self, db, guild_id: int, enabled_map: dict, bot_avatar: str, prefix: str):
        super().__init__(timeout=90)
        self.db = db
        self.guild_id = guild_id
        self.enabled_map = dict(enabled_map)
        self.bot_avatar = bot_avatar
        self.prefix = prefix
        self.select = FilterEnableSelect(db, guild_id, enabled_map)
        self.add_item(self.select)

    @discord.ui.button(label="✅  Save & Done", style=discord.ButtonStyle.success, custom_id="save_filters_done")
    async def save_done(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.response.edit_message(
            content=f"{CHECK} Antinuke filters saved successfully!",
            embed=None,
            view=None
        )

    async def on_timeout(self):
        pass


class AntiNukeSetup(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._init_db())

    async def _init_db(self):
        self.db = await aiosqlite.connect("db/anti.db")

        # Core enable/disable table
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke (
                guild_id INTEGER PRIMARY KEY,
                status   BOOLEAN DEFAULT FALSE
            )
        """)

        # Per-filter enable/disable table
        filter_cols = " ".join(f"{k} BOOLEAN DEFAULT FALSE," for k in FILTER_META)
        await self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS antinuke_filters (
                guild_id INTEGER PRIMARY KEY,
                {filter_cols.rstrip(',')}
            )
        """)

        await self.db.commit()

    # ── helpers ──────────────────────────────────────────────

    async def _is_authorized(self, ctx) -> bool:
        """Server owner or extra owner."""
        if ctx.author.id == ctx.guild.owner_id:
            return True
        async with self.db.execute(
            "SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?",
            (ctx.guild.id, ctx.author.id)
        ) as cur:
            return bool(await cur.fetchone())

    async def _get_status(self, guild_id: int) -> bool:
        async with self.db.execute(
            "SELECT status FROM antinuke WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        return bool(row and row[0])

    async def _get_filter_map(self, guild_id: int) -> dict:
        async with self.db.execute(
            "SELECT * FROM antinuke_filters WHERE guild_id = ?", (guild_id,)
        ) as cur:
            row = await cur.fetchone()
        if not row:
            return {k: False for k in FILTER_META}
        cols = [d[0] for d in cur.description]
        return {k: bool(row[cols.index(k)]) for k in FILTER_META if k in cols}

    # ── access denied embed ───────────────────────────────────

    async def _send_access_denied(self, ctx):
        embed = discord.Embed(
            color=0x2B2D31,
            description=(
                f"{AN_LOCK_CLOSED} **Access Restricted**\n"
                "> Only the **Server Owner** or an **Extra Owner** can use this command."
            )
        )
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=embed)

    # ── main command ─────────────────────────────────────────

    @commands.group(
        name="antinuke",
        aliases=["security", "anti"],
        invoke_without_command=True,
        help="Manage the antinuke security system."
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.guild_only()
    async def antinuke(self, ctx):
        """Shows antinuke status and available subcommands."""
        if not await self._is_authorized(ctx):
            return await self._send_access_denied(ctx)

        pre = ctx.prefix
        active = await self._get_status(ctx.guild.id)
        filter_map = await self._get_filter_map(ctx.guild.id)

        embed = discord.Embed(
            title=f"{AN_SHIELD}  Setup Antinuke !",
            color=0x2B2D31,
            description=(
                f"*Your bot's Antinuke is one of the most advanced protection systems available. "
                f"Use `{pre}antinuke wizard` if you want the best default settings, "
                f"or configure manually with the commands below.*\n\n"
                + _build_filter_display(filter_map)
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text=f"Status: {'Enabled' if active else 'Disabled'} • Use {pre}antinuke enable/disable")

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="Enable Antinuke Filters",
            style=discord.ButtonStyle.secondary,
            custom_id="open_filter_select",
            emoji="🛡️"
        ))
        view.add_item(discord.ui.Button(
            label="Setup Done ✅",
            style=discord.ButtonStyle.success,
            custom_id="setup_done_btn",
            disabled=not active
        ))
        view.add_item(discord.ui.Button(
            label="Show Rules 🔗",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/yourserver"  # replace with your support server
        ))

        await ctx.send(embed=embed, view=view)

    # ── subcommands ───────────────────────────────────────────

    @antinuke.command(name="enable", help="Enable and configure antinuke on the server.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def enable(self, ctx):
        # ── strict owner/extra-owner gate ────────────────────
        if not await self._is_authorized(ctx):
            return await self._send_access_denied(ctx)

        pre      = ctx.prefix
        guild    = ctx.guild
        guild_id = guild.id
        me       = guild.me
        active   = await self._get_status(guild_id)

        # ── already enabled → just show current panel ────────
        if active:
            filter_map = await self._get_filter_map(guild_id)
            embed = discord.Embed(
                color=0x2B2D31,
                title=f"{AN_SHIELD}  Setup Antinuke !",
                description=(
                    f"*Antinuke is already active on **{guild.name}**.*\n\n"
                    + _build_filter_display(filter_map)
                )
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(text=f"To disable use {pre}antinuke disable")
            return await ctx.send(embed=embed)

        ROLE_NAME = "Unbypassable Security [Z+]"

        # ── track each step result separately (no growing description) ──
        # We keep a list of (ok, text) and rebuild the embed each edit
        # so we never hit the 2000-char limit mid-setup.
        steps_done: list[tuple[bool, str]] = []

        async def step(text: str, ok: bool = True) -> None:
            steps_done.append((ok, text))
            lines = "\n".join(
                f"{CHECK if s else CROSS} {t}" for s, t in steps_done
            )
            prog.description = lines
            try:
                await msg.edit(embed=prog)
            except discord.HTTPException:
                pass
            await asyncio.sleep(0.9)

        prog = discord.Embed(
            title=f"{GEARS}  Initializing Antinuke…",
            description="",
            color=0x2B2D31
        )
        msg = await ctx.send(embed=prog)

        # ── 1. permission check ───────────────────────────────
        await step("Starting quick setup!")

        if not me.guild_permissions.administrator:
            await step("Setup failed — I need the **Administrator** permission.", ok=False)
            return

        await step("Verified bot permissions.")

        # ── 2. delete old security role if it exists ─────────
        # Search by name; remove ALL copies in case there are duplicates
        old_roles = [r for r in guild.roles if r.name == ROLE_NAME]
        if old_roles:
            for old in old_roles:
                try:
                    await old.delete(reason="Antinuke re-setup — removing old security role")
                    await asyncio.sleep(0.3)   # small gap to avoid rate-limit
                except (discord.Forbidden, discord.HTTPException):
                    pass
            await step(f"Removed {len(old_roles)} existing **{ROLE_NAME}** role(s).")
        else:
            await step("No existing security role found — fresh install.")

        # ── 3. check current bot role position vs @everyone ──
        # @everyone is always position 0. The bot's top role must be
        # above position 0 for it to do anything useful.
        everyone_role = guild.default_role  # position 0, always
        bot_top       = me.top_role

        if bot_top.position > everyone_role.position:
            await step(
                f"Role hierarchy OK — currently sitting at position **{bot_top.position}**."
            )
        else:
            await step(
                "My highest role is at position 0 (@everyone). "
                "The new security role will fix this.",
                ok=False
            )

        # ── 4. create the security role ───────────────────────
        await step(f"Crafting the **{ROLE_NAME}** role…")

        try:
            security_role = await guild.create_role(
                name=ROLE_NAME,
                color=0x2B2D31,
                permissions=discord.Permissions(administrator=True),
                hoist=False,
                mentionable=False,
                reason=f"Antinuke setup — {ROLE_NAME}"
            )
        except discord.Forbidden:
            await step("Setup failed — missing permission to create roles.", ok=False)
            return
        except discord.HTTPException as e:
            await step(f"Setup failed — Discord error: {e}", ok=False)
            return

        # ── 5. move role to the highest possible position ─────
        # The highest slot we can place a role is (our current top role position - 1).
        # After we get the new role we re-fetch our top role because the new role
        # was just created at the bottom.
        await asyncio.sleep(0.5)   # let Discord settle the role cache

        # Reload member to get fresh role list
        try:
            me = await guild.fetch_member(guild.me.id)
        except Exception:
            me = guild.me

        # Best position = just below the bot's current top role
        # (Discord won't let a role move above its creator's top role)
        best_position = me.top_role.position - 1
        if best_position < 1:
            best_position = 1   # must always be above @everyone (pos 0)

        try:
            await guild.edit_role_positions(
                positions={security_role: best_position},
                reason="Antinuke — hoisting security role to top"
            )
            await step(
                f"Positioned **{ROLE_NAME}** at slot **{best_position}** "
                f"(above **@everyone** and all member roles)."
            )
        except (discord.Forbidden, discord.HTTPException) as e:
            await step(
                f"Couldn't auto-position the role ({e}). "
                f"Please drag **{ROLE_NAME}** to the top manually.",
                ok=False
            )

        # ── 6. assign role to the bot ─────────────────────────
        try:
            await me.add_roles(security_role, reason="Antinuke — assigning security role to bot")
            await step(f"Assigned **{ROLE_NAME}** to myself.")
        except (discord.Forbidden, discord.HTTPException):
            await step(
                f"Couldn't assign **{ROLE_NAME}** to myself — please do it manually.",
                ok=False
            )

        # ── 7. save to DB ─────────────────────────────────────
        await self.db.execute(
            "INSERT OR REPLACE INTO antinuke (guild_id, status) VALUES (?, ?)",
            (guild_id, True)
        )
        await self.db.commit()
        await step("Configuration saved to database.")

        await step("All antinuke modules activated — server is now protected! 🛡️")

        # ── 8. delete progress embed, send final panel ────────
        await asyncio.sleep(1)
        try:
            await msg.delete()
        except discord.HTTPException:
            pass

        filter_map = await self._get_filter_map(guild_id)
        embed = discord.Embed(
            title=f"{AN_SHIELD}  Setup Antinuke !",
            color=0x2B2D31,
            description=(
                f"*Your bot's Antinuke is one of the most advanced protection systems "
                f"available. Use `{pre}antinuke wizard` to auto-apply best settings, "
                f"or configure filters manually below.*\n\n"
                + _build_filter_display(filter_map)
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(
            text=f"Keep '{ROLE_NAME}' above all member roles for full protection."
        )

        view = discord.ui.View(timeout=None)
        view.add_item(discord.ui.Button(
            label="Enable Antinuke Filters",
            style=discord.ButtonStyle.secondary,
            custom_id="open_filter_select",
            emoji="🛡️"
        ))
        view.add_item(discord.ui.Button(
            label="Setup Done ✅",
            style=discord.ButtonStyle.success,
            custom_id="setup_done_btn"
        ))
        view.add_item(discord.ui.Button(
            label="Show Rules 🔗",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/yourserver"
        ))
        await ctx.send(embed=embed, view=view)

    @antinuke.command(name="disable", help="Disable antinuke on the server.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def disable(self, ctx):
        if not await self._is_authorized(ctx):
            return await self._send_access_denied(ctx)

        guild_id = ctx.guild.id
        active = await self._get_status(guild_id)
        pre = ctx.prefix

        if not active:
            embed = discord.Embed(
                color=0x2B2D31,
                description=(
                    f"{CROSS} **Antinuke is not enabled** on **{ctx.guild.name}**.\n"
                    f"> Current Status: {DISABLED}\n"
                    f"> To enable use `{pre}antinuke enable`"
                )
            )
            return await ctx.send(embed=embed)

        await self.db.execute("DELETE FROM antinuke WHERE guild_id = ?", (guild_id,))
        await self.db.execute("DELETE FROM antinuke_filters WHERE guild_id = ?", (guild_id,))
        await self.db.commit()

        embed = discord.Embed(
            color=0x2B2D31,
            description=(
                f"{CHECK} **Antinuke disabled** for **{ctx.guild.name}**.\n"
                f"> Current Status: {DISABLED}\n"
                f"> To re-enable use `{pre}antinuke enable`"
            )
        )
        embed.set_footer(text=ctx.guild.name, icon_url=ctx.guild.icon.url if ctx.guild.icon else None)
        await ctx.send(embed=embed)

    @antinuke.command(name="filters", aliases=["filter"], help="Open the filter enable/disable panel.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def filters(self, ctx):
        if not await self._is_authorized(ctx):
            return await self._send_access_denied(ctx)

        active = await self._get_status(ctx.guild.id)
        if not active:
            embed = discord.Embed(
                color=0x2B2D31,
                description=f"{CROSS} Antinuke is not enabled. Use `{ctx.prefix}antinuke enable` first."
            )
            return await ctx.send(embed=embed)

        filter_map = await self._get_filter_map(ctx.guild.id)
        embed = discord.Embed(
            title="🛡️  Enable Antinuke Filters",
            description=_build_filter_display(filter_map),
            color=0x2B2D31
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="Select filters below • Changes save automatically")

        view = FilterEnableView(
            self.db, ctx.guild.id, filter_map,
            self.bot.user.display_avatar.url, ctx.prefix
        )
        await ctx.send(embed=embed, view=view)

    @antinuke.command(name="wizard", help="Apply recommended antinuke settings automatically.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def wizard(self, ctx):
        if not await self._is_authorized(ctx):
            return await self._send_access_denied(ctx)

        # Enable all filters with recommended defaults
        all_on = {k: True for k in FILTER_META}
        all_on["prune"] = False   # prune off by default (too noisy for most servers)
        all_on["botadd"] = False  # bot add off by default

        await self.db.execute(
            f"INSERT OR REPLACE INTO antinuke_filters (guild_id, {', '.join(FILTER_META)}) "
            f"VALUES ({', '.join(['?'] * (len(FILTER_META) + 1))})",
            [ctx.guild.id] + [all_on[k] for k in FILTER_META]
        )
        await self.db.execute(
            "INSERT OR REPLACE INTO antinuke (guild_id, status) VALUES (?, ?)",
            (ctx.guild.id, True)
        )
        await self.db.commit()

        embed = discord.Embed(
            title=f"{AN_SHIELD}  Antinuke Wizard Complete!",
            color=0x2B2D31,
            description=(
                f"{CHECK} Applied recommended settings for **{ctx.guild.name}**.\n\n"
                + _build_filter_display(all_on)
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(text="You can fine-tune with .antinuke filters or .antinuke limit")
        await ctx.send(embed=embed)

    # ── button interaction listener ───────────────────────────

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        cid = interaction.data.get("custom_id", "")

        if cid == "open_filter_select":
            if interaction.user.id != interaction.guild.owner_id:
                async with self.db.execute(
                    "SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?",
                    (interaction.guild.id, interaction.user.id)
                ) as cur:
                    if not await cur.fetchone():
                        return await interaction.response.send_message(
                            f"{CROSS} Only the server owner or extra owners can do this.",
                            ephemeral=True
                        )

            filter_map = await self._get_filter_map(interaction.guild.id)
            embed = discord.Embed(
                title="🛡️  Enable Antinuke Filters",
                description=_build_filter_display(filter_map),
                color=0x2B2D31
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            embed.set_footer(text="Select at least 1 filter to enable")

            view = FilterEnableView(
                self.db, interaction.guild.id, filter_map,
                self.bot.user.display_avatar.url, "."
            )
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        elif cid == "setup_done_btn":
            await interaction.response.send_message(
                f"{CHECK} Antinuke setup is complete! Your server is now protected.",
                ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(AntiNukeSetup(bot))
