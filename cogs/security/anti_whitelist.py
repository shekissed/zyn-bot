"""
antinuke_whitelist_v2.py
Handles: .an wl @user — whitelist with per-filter toggle UI like ZEON's panel.
Shows toggle states for all filters; user can bulk-enable or pick individual ones.
"""

import discord
from discord.ext import commands
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import (
    CHECK, CROSS, ENABLED, DISABLED, AN_ARROW, AN_SHIELD,
    AN_WHITELIST, AN_LOCK_CLOSED
)

# All whitelistable filters — key matches DB column name
FILTER_META = {
    "ban":       "Ban",
    "kick":      "Kick",
    "prune":     "Prune",
    "memup":     "Member Update",
    "rlcr":      "Role Create",
    "rldl":      "Role Delete",
    "rlup":      "Role Update",
    "chcr":      "Channel Create",
    "chdl":      "Channel Delete",
    "chup":      "Channel Update",
    "webhookcr": "Webhook Create",
    "webhookdl": "Webhook Delete",
    "webhookup": "Webhook Update",
    "botadd":    "Bot Add",
    "serverup":  "Guild Update",
    "meneve":    "Mention Spam",
}

FILTERS_ROW1 = ["ban", "kick", "prune", "memup", "rlcr", "rldl", "rlup", "chcr"]
FILTERS_ROW2 = ["chdl", "chup", "webhookcr", "webhookdl", "webhookup", "botadd", "serverup", "meneve"]


def _toggle(state: bool) -> str:
    return ENABLED if state else DISABLED


def _build_wl_display(target: discord.Member, state_map: dict, count: int) -> str:
    """Build the whitelist filter embed description in ZEON's style."""
    def line(k):
        return f"{AN_ARROW} **{FILTER_META[k]} :** {_toggle(state_map.get(k, False))}"

    r1 = "\n".join(line(k) for k in FILTERS_ROW1)
    r2 = "\n".join(line(k) for k in FILTERS_ROW2)
    return (
        f"*Manage **{target.mention}'s** whitelist for the **Antinuke Filter** "
        f"to make them immune*\n\n"
        f"**Whitelisted Filters [{count}] :**\n{r1}\n\n"
        f"**Whitelisted Filters [2] :**\n{r2}"
    )


class WhitelistFilterSelect(discord.ui.Select):
    def __init__(self, db, guild_id: int, user_id: int, state_map: dict):
        self.db = db
        self.guild_id = guild_id
        self.user_id = user_id
        self.state_map = dict(state_map)

        options = [
            discord.SelectOption(
                label=FILTER_META[k],
                description=f"Toggle {FILTER_META[k].lower()} whitelist.",
                value=k,
                emoji="▶️",
                default=state_map.get(k, False)
            )
            for k in FILTER_META
        ]
        super().__init__(
            placeholder="Select filters to whitelist…",
            min_values=1,
            max_values=len(options),
            options=options,
            custom_id="wl_filter_select"
        )

    async def callback(self, interaction: discord.Interaction):
        selected = set(self.values)
        for k in FILTER_META:
            self.state_map[k] = k in selected

        cols = ", ".join(f"{k} = ?" for k in FILTER_META)
        vals = [self.state_map[k] for k in FILTER_META]
        await self.db.execute(
            f"UPDATE antinuke_whitelist SET {cols} WHERE guild_id = ? AND user_id = ?",
            vals + [self.guild_id, self.user_id]
        )
        await self.db.commit()

        member = interaction.guild.get_member(self.user_id)
        enabled_count = sum(1 for v in self.state_map.values() if v)
        embed = interaction.message.embeds[0]
        embed.description = _build_wl_display(member, self.state_map, enabled_count)
        await interaction.response.edit_message(embed=embed, view=self.view)


class WhitelistView(discord.ui.View):
    def __init__(self, db, guild_id: int, target: discord.Member, state_map: dict):
        super().__init__(timeout=90)
        self.db = db
        self.guild_id = guild_id
        self.target = target
        self.state_map = dict(state_map)
        self.select = WhitelistFilterSelect(db, guild_id, target.id, state_map)
        self.add_item(self.select)

    @discord.ui.button(label="Enable All", style=discord.ButtonStyle.success, custom_id="wl_all_on", row=1)
    async def all_on(self, interaction: discord.Interaction, button: discord.ui.Button):
        for k in FILTER_META:
            self.state_map[k] = True

        cols = ", ".join(f"{k} = ?" for k in FILTER_META)
        await self.db.execute(
            f"UPDATE antinuke_whitelist SET {cols} WHERE guild_id = ? AND user_id = ?",
            [True] * len(FILTER_META) + [self.guild_id, self.target.id]
        )
        await self.db.commit()

        enabled_count = sum(1 for v in self.state_map.values() if v)
        embed = interaction.message.embeds[0]
        embed.description = _build_wl_display(self.target, self.state_map, enabled_count)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Disable All", style=discord.ButtonStyle.danger, custom_id="wl_all_off", row=1)
    async def all_off(self, interaction: discord.Interaction, button: discord.ui.Button):
        for k in FILTER_META:
            self.state_map[k] = False

        cols = ", ".join(f"{k} = ?" for k in FILTER_META)
        await self.db.execute(
            f"UPDATE antinuke_whitelist SET {cols} WHERE guild_id = ? AND user_id = ?",
            [False] * len(FILTER_META) + [self.guild_id, self.target.id]
        )
        await self.db.commit()

        embed = interaction.message.embeds[0]
        embed.description = _build_wl_display(self.target, self.state_map, 0)
        await interaction.response.edit_message(embed=embed, view=self)

    async def on_timeout(self):
        pass


class AntiNukeWhitelistV2(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._init_db())

    async def _init_db(self):
        self.db = await aiosqlite.connect("db/anti.db")
        filter_cols = " ".join(f"{k} BOOLEAN DEFAULT FALSE," for k in FILTER_META)
        await self.db.execute(f"""
            CREATE TABLE IF NOT EXISTS antinuke_whitelist (
                guild_id INTEGER,
                user_id  INTEGER,
                {filter_cols.rstrip(',')}
                PRIMARY KEY (guild_id, user_id)
            )
        """)
        await self.db.commit()

    async def _is_authorized(self, ctx) -> bool:
        if ctx.author.id == ctx.guild.owner_id:
            return True
        async with self.db.execute(
            "SELECT owner_id FROM extraowners WHERE guild_id = ? AND owner_id = ?",
            (ctx.guild.id, ctx.author.id)
        ) as cur:
            return bool(await cur.fetchone())

    async def _get_state(self, guild_id: int, user_id: int) -> dict:
        async with self.db.execute(
            "SELECT * FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id)
        ) as cur:
            row = await cur.fetchone()
            if not row:
                return {k: False for k in FILTER_META}
            cols = [d[0] for d in cur.description]
        return {k: bool(row[cols.index(k)]) for k in FILTER_META if k in cols}

    # ── .an wl @user ──────────────────────────────────────────

    @commands.group(name="an", invoke_without_command=True, hidden=True)
    @commands.guild_only()
    async def an_group(self, ctx):
        await ctx.send_help(ctx.command)

    @an_group.command(name="wl", aliases=["whitelist"], help="Manage antinuke whitelist for a user.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def an_whitelist(self, ctx, member: discord.Member = None):
        if not await self._is_authorized(ctx):
            embed = discord.Embed(
                color=0x2B2D31,
                description=(
                    f"{AN_LOCK_CLOSED} **Access Restricted**\n"
                    "> Only the **Server Owner** or an **Extra Owner** can use this command."
                )
            )
            return await ctx.send(embed=embed)

        async with self.db.execute("SELECT status FROM antinuke WHERE guild_id = ?", (ctx.guild.id,)) as cur:
            row = await cur.fetchone()
        if not row or not row[0]:
            embed = discord.Embed(
                color=0x2B2D31,
                description=(
                    f"{CROSS} Antinuke is not enabled.\n"
                    f"> Use `{ctx.prefix}antinuke enable` first."
                )
            )
            return await ctx.send(embed=embed)

        if not member:
            embed = discord.Embed(
                title=f"{AN_SHIELD}  Antinuke Whitelist",
                color=0x2B2D31,
                description=(
                    f"**Adding a user to the whitelist** means no action will be taken "
                    f"against them even if they trigger an Antinuke filter.\n\n"
                    f"**Usage:** `{ctx.prefix}an wl @user`\n"
                    f"**Remove:** `{ctx.prefix}an unwl @user`\n"
                    f"**View:** `{ctx.prefix}an wlist`"
                )
            )
            embed.set_thumbnail(url=self.bot.user.display_avatar.url)
            return await ctx.send(embed=embed)

        if member.id == ctx.guild.owner_id:
            return await ctx.send(f"{CROSS} The server owner is always whitelisted.")
        if member.bot:
            return await ctx.send(f"{CROSS} You cannot whitelist a bot.")

        # Insert or ensure row exists
        await self.db.execute(
            "INSERT OR IGNORE INTO antinuke_whitelist (guild_id, user_id) VALUES (?, ?)",
            (ctx.guild.id, member.id)
        )
        await self.db.commit()

        state_map = await self._get_state(ctx.guild.id, member.id)
        enabled_count = sum(1 for v in state_map.values() if v)

        embed = discord.Embed(
            title=f"{AN_SHIELD}  Antinuke Whitelist !",
            color=0x2B2D31,
            description=_build_wl_display(member, state_map, enabled_count)
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.set_footer(
            text=f"Requested by {ctx.author}",
            icon_url=ctx.author.display_avatar.url
        )

        view = WhitelistView(self.db, ctx.guild.id, member, state_map)
        await ctx.send(embed=embed, view=view)

    @an_group.command(name="unwl", aliases=["unwhitelist"], help="Remove a user from the antinuke whitelist.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def an_unwhitelist(self, ctx, member: discord.Member = None):
        if not await self._is_authorized(ctx):
            embed = discord.Embed(
                color=0x2B2D31,
                description=f"{AN_LOCK_CLOSED} **Access Restricted**\n> Only the Server Owner or Extra Owner can use this."
            )
            return await ctx.send(embed=embed)

        if not member:
            return await ctx.send(f"{CROSS} Please mention a user to remove from the whitelist.")

        async with self.db.execute(
            "SELECT user_id FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id)
        ) as cur:
            row = await cur.fetchone()

        if not row:
            return await ctx.send(f"{CROSS} **{member}** is not whitelisted.")

        await self.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ? AND user_id = ?",
            (ctx.guild.id, member.id)
        )
        await self.db.commit()

        embed = discord.Embed(
            color=0x2B2D31,
            description=f"{CHECK} Removed **{member.mention}** from the antinuke whitelist."
        )
        await ctx.send(embed=embed)

    @an_group.command(name="wlist", aliases=["whitelisted"], help="View all whitelisted users.")
    @commands.cooldown(1, 5, commands.BucketType.user)
    @commands.guild_only()
    async def an_wlist(self, ctx):
        if not await self._is_authorized(ctx):
            embed = discord.Embed(
                color=0x2B2D31,
                description=f"{AN_LOCK_CLOSED} **Access Restricted**\n> Only the Server Owner or Extra Owner can use this."
            )
            return await ctx.send(embed=embed)

        async with self.db.execute(
            "SELECT user_id FROM antinuke_whitelist WHERE guild_id = ?",
            (ctx.guild.id,)
        ) as cur:
            rows = await cur.fetchall()

        if not rows:
            return await ctx.send(f"{CROSS} No whitelisted users found.")

        mentions = []
        for (uid,) in rows:
            user = ctx.guild.get_member(uid) or self.bot.get_user(uid)
            if user:
                mentions.append(f"▶️ {user.mention}")
            else:
                mentions.append(f"▶️ `{uid}` *(left server)*")

        embed = discord.Embed(
            title=f"{AN_SHIELD}  Whitelisted Users",
            color=0x2B2D31,
            description="\n".join(mentions)
        )
        embed.set_footer(text=f"{ctx.guild.name} • {len(mentions)} user(s)")
        await ctx.send(embed=embed)

    @an_group.command(name="wlreset", help="Remove ALL users from the antinuke whitelist.")
    @commands.cooldown(1, 10, commands.BucketType.user)
    @commands.guild_only()
    async def an_wlreset(self, ctx):
        if not await self._is_authorized(ctx):
            embed = discord.Embed(
                color=0x2B2D31,
                description=f"{AN_LOCK_CLOSED} **Access Restricted**\n> Only the Server Owner or Extra Owner can use this."
            )
            return await ctx.send(embed=embed)

        await self.db.execute(
            "DELETE FROM antinuke_whitelist WHERE guild_id = ?", (ctx.guild.id,)
        )
        await self.db.commit()

        embed = discord.Embed(
            color=0x2B2D31,
            description=f"{CHECK} Cleared the entire antinuke whitelist for **{ctx.guild.name}**."
        )
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(AntiNukeWhitelistV2(bot))
