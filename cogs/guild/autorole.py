import discord
from discord.ext import commands
from discord import app_commands
import aiosqlite
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import CHECK, CROSS, INFO

DB_PATH = "db/autorole.db"

# ─────────────────────────────────────────────────────────────────
#  DB HELPERS
# ─────────────────────────────────────────────────────────────────

async def _init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """CREATE TABLE IF NOT EXISTS autoroles (
                guild_id   INTEGER NOT NULL,
                role_id    INTEGER NOT NULL,
                type       TEXT    NOT NULL CHECK(type IN ('human', 'bot')),
                added_by   INTEGER NOT NULL,
                PRIMARY KEY (guild_id, role_id, type)
            )"""
        )
        await db.commit()


async def _add_role(guild_id: int, role_id: int, kind: str, added_by: int) -> bool:
    """Returns True if inserted, False if already existed."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM autoroles WHERE guild_id=? AND role_id=? AND type=?",
            (guild_id, role_id, kind)
        ) as cur:
            if await cur.fetchone():
                return False
        await db.execute(
            "INSERT INTO autoroles (guild_id, role_id, type, added_by) VALUES (?,?,?,?)",
            (guild_id, role_id, kind, added_by)
        )
        await db.commit()
    return True


async def _remove_role(guild_id: int, role_id: int, kind: str) -> bool:
    """Returns True if deleted, False if didn't exist."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM autoroles WHERE guild_id=? AND role_id=? AND type=?",
            (guild_id, role_id, kind)
        ) as cur:
            if not await cur.fetchone():
                return False
        await db.execute(
            "DELETE FROM autoroles WHERE guild_id=? AND role_id=? AND type=?",
            (guild_id, role_id, kind)
        )
        await db.commit()
    return True


async def _list_roles(guild_id: int, kind: str) -> list[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT role_id FROM autoroles WHERE guild_id=? AND type=?",
            (guild_id, kind)
        ) as cur:
            rows = await cur.fetchall()
    return [r[0] for r in rows]


# ─────────────────────────────────────────────────────────────────
#  EMBED BUILDERS  (match reference screenshots exactly)
# ─────────────────────────────────────────────────────────────────

def _list_embed(guild: discord.Guild, kind: str, roles: list[discord.Role]) -> discord.Embed:
    """
    Matches Image 1 style:
      Title : Bot autoroles [N]  /  Human autoroles [N]
      Lines : 01. :@. <role> - by <user>
      Footer: Page 1/1 | Requested by <user>   (static for now)
    """
    label = "Bot" if kind == "bot" else "Human"
    title = f"{label} autoroles [{len(roles)}]"

    lines = []
    for i, role in enumerate(roles, start=1):
        lines.append(f"`{i:02d}.` {role.mention}")

    description = "\n".join(lines) if lines else "*No autoroles configured.*"

    embed = discord.Embed(
        title=title,
        description=description,
        color=0x2b2d31
    )
    return embed


# ─────────────────────────────────────────────────────────────────
#  CORE LOGIC  (shared between prefix + slash)
# ─────────────────────────────────────────────────────────────────

async def _do_add(
    guild: discord.Guild,
    role: discord.Role,
    kind: str,
    invoker: discord.Member,
    respond
):
    inserted = await _add_role(guild.id, role.id, kind, invoker.id)
    label = "Human" if kind == "human" else "Bot"
    if inserted:
        embed = discord.Embed(
            description=f"{CHECK} **Autorole {label} Added**\n▶ Role {role.mention} has been added to {kind} autoroles.",
            color=0x57f287
        )
    else:
        embed = discord.Embed(
            description=f"{CROSS} Role {role.mention} is already in {kind} autoroles.",
            color=0xed4245
        )
    await respond(embed=embed)


async def _do_remove(
    guild: discord.Guild,
    role: discord.Role,
    kind: str,
    respond
):
    deleted = await _remove_role(guild.id, role.id, kind)
    label = "Human" if kind == "human" else "Bot"
    if deleted:
        embed = discord.Embed(
            description=f"{CHECK} **Autorole {label} Removed**\n▶ Role {role.mention} has been removed from {kind} autoroles.",
            color=0x57f287
        )
    else:
        embed = discord.Embed(
            description=f"{CROSS} Role {role.mention} is not in {kind} autoroles.",
            color=0xed4245
        )
    await respond(embed=embed)


async def _do_show(guild: discord.Guild, kind: str, invoker: discord.Member, respond):
    role_ids = await _list_roles(guild.id, kind)
    roles = [r for rid in role_ids if (r := guild.get_role(rid))]
    label = "Bot" if kind == "bot" else "Human"

    if not roles:
        embed = discord.Embed(
            description=f"{INFO} No {kind} autoroles are configured.",
            color=0x2b2d31
        )
        return await respond(embed=embed)

    title = f"{label} autoroles [{len(roles)}]"
    lines = [f"`{i:02d}.` {role.mention}" for i, role in enumerate(roles, 1)]
    embed = discord.Embed(title=title, description="\n".join(lines), color=0x2b2d31)
    embed.set_footer(text=f"Page 1/1 | Requested by {invoker.display_name}")
    await respond(embed=embed)


# ─────────────────────────────────────────────────────────────────
#  on_member_join  listener
# ─────────────────────────────────────────────────────────────────

class Autorole(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        bot.loop.create_task(_init_db())

        # Register slash command group once the cog loads
        self._add_slash_commands()

    # ── listener ─────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        kind = "bot" if member.bot else "human"
        role_ids = await _list_roles(member.guild.id, kind)
        for rid in role_ids:
            role = member.guild.get_role(rid)
            if role and role < member.guild.me.top_role:
                try:
                    await member.add_roles(role, reason=f"Autorole ({kind})")
                except discord.Forbidden:
                    pass

    # ══════════════════════════════════════════════════════════════
    #  PREFIX COMMANDS
    # ══════════════════════════════════════════════════════════════

    @commands.group(name="autorole", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def autorole(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    # ── humans ───────────────────────────────────────────────────

    @autorole.group(name="humans", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def autorole_humans(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @autorole_humans.command(name="add")
    @commands.has_permissions(administrator=True)
    async def autorole_humans_add(self, ctx: commands.Context, role: discord.Role):
        await _do_add(ctx.guild, role, "human", ctx.author,
                      lambda **kw: ctx.send(**kw))

    @autorole_humans.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def autorole_humans_remove(self, ctx: commands.Context, role: discord.Role):
        await _do_remove(ctx.guild, role, "human",
                         lambda **kw: ctx.send(**kw))

    @autorole_humans.command(name="show", aliases=["list"])
    @commands.has_permissions(administrator=True)
    async def autorole_humans_show(self, ctx: commands.Context):
        await _do_show(ctx.guild, "human", ctx.author,
                       lambda **kw: ctx.send(**kw))

    # ── bots ─────────────────────────────────────────────────────

    @autorole.group(name="bots", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def autorole_bots(self, ctx: commands.Context):
        await ctx.send_help(ctx.command)

    @autorole_bots.command(name="add")
    @commands.has_permissions(administrator=True)
    async def autorole_bots_add(self, ctx: commands.Context, role: discord.Role):
        await _do_add(ctx.guild, role, "bot", ctx.author,
                      lambda **kw: ctx.send(**kw))

    @autorole_bots.command(name="remove")
    @commands.has_permissions(administrator=True)
    async def autorole_bots_remove(self, ctx: commands.Context, role: discord.Role):
        await _do_remove(ctx.guild, role, "bot",
                         lambda **kw: ctx.send(**kw))

    @autorole_bots.command(name="show", aliases=["list"])
    @commands.has_permissions(administrator=True)
    async def autorole_bots_show(self, ctx: commands.Context):
        await _do_show(ctx.guild, "bot", ctx.author,
                       lambda **kw: ctx.send(**kw))

    # ══════════════════════════════════════════════════════════════
    #  SLASH COMMANDS  (mirror prefix exactly)
    # ══════════════════════════════════════════════════════════════

    def _add_slash_commands(self):
        """Build and register slash command tree manually so they sync with the bot tree."""

        autorole_group = app_commands.Group(
            name="autorole",
            description="Configure automatic role assignment on member join.",
            default_permissions=discord.Permissions(administrator=True),
        )

        # ── /autorole humans add ──────────────────────────────────
        humans_group = app_commands.Group(
            name="humans",
            description="Autorole settings for human members.",
            parent=autorole_group,
        )

        @humans_group.command(name="add", description="Add a role to be given to humans on join.")
        @app_commands.describe(role="The role to auto-assign to humans.")
        async def slash_humans_add(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer()
            await _do_add(
                interaction.guild, role, "human", interaction.user,
                lambda **kw: interaction.followup.send(**kw)
            )

        @humans_group.command(name="remove", description="Remove a role from human autoroles.")
        @app_commands.describe(role="The role to remove from human autoroles.")
        async def slash_humans_remove(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer()
            await _do_remove(
                interaction.guild, role, "human",
                lambda **kw: interaction.followup.send(**kw)
            )

        @humans_group.command(name="show", description="List all human autoroles.")
        async def slash_humans_show(interaction: discord.Interaction):
            await interaction.response.defer()
            await _do_show(
                interaction.guild, "human", interaction.user,
                lambda **kw: interaction.followup.send(**kw)
            )

        # ── /autorole bots ────────────────────────────────────────
        bots_group = app_commands.Group(
            name="bots",
            description="Autorole settings for bots.",
            parent=autorole_group,
        )

        @bots_group.command(name="add", description="Add a role to be given to bots on join.")
        @app_commands.describe(role="The role to auto-assign to bots.")
        async def slash_bots_add(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer()
            await _do_add(
                interaction.guild, role, "bot", interaction.user,
                lambda **kw: interaction.followup.send(**kw)
            )

        @bots_group.command(name="remove", description="Remove a role from bot autoroles.")
        @app_commands.describe(role="The role to remove from bot autoroles.")
        async def slash_bots_remove(interaction: discord.Interaction, role: discord.Role):
            await interaction.response.defer()
            await _do_remove(
                interaction.guild, role, "bot",
                lambda **kw: interaction.followup.send(**kw)
            )

        @bots_group.command(name="show", description="List all bot autoroles.")
        async def slash_bots_show(interaction: discord.Interaction):
            await interaction.response.defer()
            await _do_show(
                interaction.guild, "bot", interaction.user,
                lambda **kw: interaction.followup.send(**kw)
            )

        # Register the full tree into the bot's app_commands tree
        self.bot.tree.add_command(autorole_group)


async def setup(bot: commands.Bot):
    await bot.add_cog(Autorole(bot))
