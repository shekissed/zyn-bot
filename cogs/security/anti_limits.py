"""
antinuke_limits.py
Handles: .antinuke limit — view & set per-filter action limits (minute, hour, heat).
Mirrors ZEON's limit panel with your bot's styling.
"""

import discord
from discord.ext import commands
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import (
    CHECK, CROSS, AN_ARROW, AN_SHIELD, AN_HEAT, AN_CLOCK,
    AN_LOCK_CLOSED, ENABLED, DISABLED
)

# Default limits: (minute_limit, hour_limit, heat_points)
DEFAULT_LIMITS = {
    "ban":       (1, 1, 45),
    "kick":      (1, 1, 35),
    "memup":     (1, 1, 20),
    "rlcr":      (1, 1, 25),
    "rldl":      (1, 1, 40),
    "rlup":      (1, 1, 30),
    "chcr":      (1, 1, 25),
    "chdl":      (1, 1, 40),
    "chup":      (1, 1, 30),
    "webhookcr": (1, 1, 50),
    "webhookdl": (1, 1, 50),
    "webhookup": (1, 1, 45),
    "serverup":  (1, 1, 75),
    "meneve":    (1, 1, 50),
}

FILTER_DISPLAY = {
    "ban":       "Ban",
    "kick":      "Kick",
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
    "serverup":  "Guild Update",
    "meneve":    "Mention Spam",
}


def _format_limits_display(limits: dict) -> str:
    """Format all filter limits in ZEON's style: Name : ( min, hr, heat )"""
    lines = []
    for key, label in FILTER_DISPLAY.items():
        ml, hl, hp = limits.get(key, DEFAULT_LIMITS.get(key, (1, 1, 30)))
        lines.append(f"{AN_ARROW} **{label} :** `( {ml} , {hl} , {hp} )`")
    return "\n".join(lines)


class SetLimitModal(discord.ui.Modal, title="Set Action Limits"):
    minute_limit = discord.ui.TextInput(
        label="Minute Limit",
        placeholder="e.g. 1",
        required=True,
        max_length=3
    )
    hour_limit = discord.ui.TextInput(
        label="Hour Limit",
        placeholder="e.g. 1",
        required=True,
        max_length=3
    )
    heat_per_action = discord.ui.TextInput(
        label="Heat Per Action",
        placeholder="e.g. 35",
        required=True,
        max_length=3
    )

    def __init__(self, db, guild_id: int, filter_key: str, filter_label: str, current: tuple):
        super().__init__()
        self.db = db
        self.guild_id = guild_id
        self.filter_key = filter_key
        self.filter_label = filter_label
        self.minute_limit.default = str(current[0])
        self.hour_limit.default = str(current[1])
        self.heat_per_action.default = str(current[2])

    async def on_submit(self, interaction: discord.Interaction):
        try:
            ml = max(1, min(60, int(self.minute_limit.value)))
            hl = max(1, min(24, int(self.hour_limit.value)))
            hp = max(1, min(100, int(self.heat_per_action.value)))
        except ValueError:
            return await interaction.response.send_message(
                f"{CROSS} Invalid values — all fields must be numbers.", ephemeral=True
            )

        await self.db.execute(
            """INSERT INTO antinuke_limits (guild_id, filter_key, minute_limit, hour_limit, heat_points)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(guild_id, filter_key) DO UPDATE SET
                   minute_limit = excluded.minute_limit,
                   hour_limit   = excluded.hour_limit,
                   heat_points  = excluded.heat_points""",
            (self.guild_id, self.filter_key, ml, hl, hp)
        )
        await self.db.commit()

        await interaction.response.send_message(
            f"{CHECK} **{self.filter_label}** limits updated → "
            f"`( {ml} , {hl} , {hp} )`",
            ephemeral=True
        )


class FilterSelectForLimit(discord.ui.Select):
    def __init__(self, db, guild_id: int, limits: dict):
        self.db = db
        self.guild_id = guild_id
        self.limits = limits

        options = [
            discord.SelectOption(
                label=label,
                description=f"Configure limits for {label.lower()}.",
                value=key,
                emoji="▶️"
            )
            for key, label in FILTER_DISPLAY.items()
        ]
        super().__init__(
            placeholder="Select a filter to configure…",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="limit_filter_select"
        )

    async def callback(self, interaction: discord.Interaction):
        key = self.values[0]
        label = FILTER_DISPLAY[key]
        current = self.limits.get(key, DEFAULT_LIMITS.get(key, (1, 1, 30)))
        modal = SetLimitModal(self.db, self.guild_id, key, label, current)
        await interaction.response.send_modal(modal)


class LimitView(discord.ui.View):
    def __init__(self, db, guild_id: int, limits: dict):
        super().__init__(timeout=120)
        self.add_item(FilterSelectForLimit(db, guild_id, limits))


class AntiNukeLimits(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.bot.loop.create_task(self._init_db())

    async def _init_db(self):
        self.db = await aiosqlite.connect("db/anti.db")
        await self.db.execute("""
            CREATE TABLE IF NOT EXISTS antinuke_limits (
                guild_id     INTEGER,
                filter_key   TEXT,
                minute_limit INTEGER DEFAULT 1,
                hour_limit   INTEGER DEFAULT 1,
                heat_points  INTEGER DEFAULT 30,
                PRIMARY KEY (guild_id, filter_key)
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

    async def _get_limits(self, guild_id: int) -> dict:
        async with self.db.execute(
            "SELECT filter_key, minute_limit, hour_limit, heat_points FROM antinuke_limits WHERE guild_id = ?",
            (guild_id,)
        ) as cur:
            rows = await cur.fetchall()
        result = {k: DEFAULT_LIMITS[k] for k in DEFAULT_LIMITS}
        for key, ml, hl, hp in rows:
            result[key] = (ml, hl, hp)
        return result

    @commands.command(
        name="antilimit",
        aliases=["anlimit"],
        help="View and configure antinuke action limits."
    )
    @commands.cooldown(1, 4, commands.BucketType.user)
    @commands.guild_only()
    async def antilimit(self, ctx):
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

        limits = await self._get_limits(ctx.guild.id)

        embed = discord.Embed(
            title=f"{AN_SHIELD}  Antinuke Limits !",
            color=0x2B2D31,
            description=(
                f"*Format : ( Minute Limit , Hour Limit , Heat Points )*\n\n"
                + _format_limits_display(limits)
            )
        )
        embed.set_thumbnail(url=self.bot.user.display_avatar.url)
        embed.set_footer(
            text=f"Select a filter below to edit its limits • Requested by {ctx.author}",
            icon_url=ctx.author.display_avatar.url
        )

        view = LimitView(self.db, ctx.guild.id, limits)

        # Filter quick-jump button
        view.add_item(discord.ui.Button(
            label="Ban",
            style=discord.ButtonStyle.secondary,
            custom_id="quickjump_ban",
            emoji="▶️",
            row=1
        ))
        await ctx.send(embed=embed, view=view)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        cid = interaction.data.get("custom_id", "")
        if cid == "quickjump_ban":
            # Directly open Ban limit modal
            limits = await self._get_limits(interaction.guild.id)
            current = limits.get("ban", DEFAULT_LIMITS["ban"])
            modal = SetLimitModal(self.db, interaction.guild.id, "ban", "Ban", current)
            await interaction.response.send_modal(modal)


async def setup(bot):
    await bot.add_cog(AntiNukeLimits(bot))
