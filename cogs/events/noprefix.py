# events/noprefix.py
import discord
from discord.ext import commands
from discord.ui import Select, View
import asyncio
import aiosqlite
import sys
from pathlib import Path
from datetime import datetime, timedelta

sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import TICK, ERROR_X, CHECK, CROSS_MARK, INFO, EMOJIES, TIMER
from main import CORE_DB, DEVELOPER_IDS, OWNER_IDS

# ---------- CONFIG ----------
LOG_CHANNEL_ID = 1408261262084931664

# days=None means Lifetime (never expires)
PLANS = {
    "3 Days":    {"days": 3},
    "1 Week":    {"days": 7},
    "1 Month":   {"days": 30},
    "3 Months":  {"days": 90},
    "Lifetime":  {"days": None},
}
# ----------------------------

LIFETIME_SENTINEL = "9999-12-31T23:59:59"  # stored in DB for lifetime rows


def iso_now():
    return datetime.utcnow().isoformat()

def parse_iso(s):
    return datetime.fromisoformat(s)

def is_lifetime(plan: str) -> bool:
    return plan == "Lifetime"


class PlanSelect(Select):
    def __init__(self, bot: commands.Bot, target_member: discord.Member, invoker: discord.Member):
        options = []
        for plan, info in PLANS.items():
            desc = "Never expires" if info["days"] is None else f"{info['days']} days"
            options.append(discord.SelectOption(label=plan, description=desc))

        super().__init__(
            placeholder="Choose a NoPrefix plan...",
            min_values=1, max_values=1,
            options=options
        )
        self.bot = bot
        self.target_member = target_member
        self.invoker = invoker

    async def callback(self, interaction: discord.Interaction):
        chosen = self.values[0]
        info = PLANS[chosen]

        if info["days"] is None:
            expires_str = LIFETIME_SENTINEL
            expires_display = "Never"
        else:
            expires_dt = datetime.utcnow() + timedelta(days=info["days"])
            expires_str = expires_dt.isoformat()
            expires_display = expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC")

        async with aiosqlite.connect(CORE_DB) as db:
            await db.execute(
                "INSERT OR REPLACE INTO noprefix (user_id, plan, added_by, added_at, expires) VALUES (?, ?, ?, ?, ?)",
                (self.target_member.id, chosen, self.invoker.id, iso_now(), expires_str)
            )
            await db.commit()

        # DM the user
        try:
            days_text = "forever (Lifetime)" if info["days"] is None else f"{info['days']} days"
            await self.target_member.send(
                embed=discord.Embed(
                    title="NoPrefix Granted",
                    description=f"You were given **{chosen}** NoPrefix for **{days_text}**.",
                    color=0x525252,
                    timestamp=datetime.utcnow()
                )
            )
        except Exception:
            pass

        # Log to channel
        log_ch = self.bot.get_channel(LOG_CHANNEL_ID) or await safe_fetch_channel(self.bot, LOG_CHANNEL_ID)
        if log_ch:
            embed = discord.Embed(title="NoPrefix Added", color=0x525252, timestamp=datetime.utcnow())
            embed.add_field(name="User",    value=f"{self.target_member} (`{self.target_member.id}`)", inline=False)
            embed.add_field(name="Plan",    value=chosen,          inline=True)
            embed.add_field(name="Expires", value=expires_display, inline=True)
            embed.add_field(name="Added by", value=f"{self.invoker} (`{self.invoker.id}`)", inline=False)
            await safe_send(log_ch, embed=embed)

        await interaction.response.edit_message(
            content=f"{CHECK} {self.target_member.mention} added with **{chosen}**",
            view=None
        )


class PlanView(View):
    def __init__(self, bot, member, invoker, timeout=60):
        super().__init__(timeout=timeout)
        self.add_item(PlanSelect(bot, member, invoker))


# ── helpers ──────────────────────────────────────────────────────
async def safe_fetch_channel(bot, cid):
    try:
        return await bot.fetch_channel(cid)
    except Exception:
        return None

async def safe_send(channel, *args, **kwargs):
    try:
        return await channel.send(*args, **kwargs)
    except Exception:
        return None


# ── Main manager ─────────────────────────────────────────────────
class NPManager:
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._expiry_task = None

    def is_dev(self, user_id: int):
        return user_id in DEVELOPER_IDS or user_id in OWNER_IDS

    async def start(self):
        self.bot.add_listener(self._on_message, "on_message")
        self._expiry_task = self.bot.loop.create_task(self._expiry_loop())

    async def stop(self):
        if self._expiry_task:
            self._expiry_task.cancel()
            self._expiry_task = None
        try:
            self.bot.remove_listener(self._on_message, "on_message")
        except Exception:
            pass

    async def _expiry_loop(self):
        await self.bot.wait_until_ready()
        while not self.bot.is_closed():
            try:
                await self._check_expired()
            except Exception:
                pass
            await asyncio.sleep(60)

    async def _check_expired(self):
        async with aiosqlite.connect(CORE_DB) as db:
            async with db.execute("SELECT user_id, plan, expires FROM noprefix") as cursor:
                rows = await cursor.fetchall()

        now = datetime.utcnow()
        for uid, plan, expires_str in rows:
            # Lifetime entries never expire
            if is_lifetime(plan) or expires_str == LIFETIME_SENTINEL:
                continue

            try:
                expires = parse_iso(expires_str)
            except Exception:
                # Malformed entry → remove
                async with aiosqlite.connect(CORE_DB) as db:
                    await db.execute("DELETE FROM noprefix WHERE user_id = ?", (uid,))
                    await db.commit()
                continue

            if expires <= now:
                async with aiosqlite.connect(CORE_DB) as db:
                    await db.execute("DELETE FROM noprefix WHERE user_id = ?", (uid,))
                    await db.commit()

                user = self.bot.get_user(uid)
                if user:
                    try:
                        await user.send(embed=discord.Embed(
                            title="NoPrefix Expired",
                            description=f"Your **{plan}** NoPrefix has expired.",
                            color=0x525252,
                            timestamp=datetime.utcnow()
                        ))
                    except Exception:
                        pass

                log_ch = self.bot.get_channel(LOG_CHANNEL_ID) or await safe_fetch_channel(self.bot, LOG_CHANNEL_ID)
                if log_ch:
                    embed = discord.Embed(title="NoPrefix Expired", color=0x525252, timestamp=datetime.utcnow())
                    embed.add_field(name="User", value=f"{user} (`{uid}`)" if user else str(uid), inline=False)
                    embed.add_field(name="Plan", value=plan, inline=True)
                    await safe_send(log_ch, embed=embed)

    async def _on_message(self, message: discord.Message):
        if message.author.bot:
            return

        content = message.content.strip()
        for m in (f"<@{self.bot.user.id}>", f"<@!{self.bot.user.id}>"):
            if content.startswith(m):
                content = content[len(m):].strip()
                break
        if content.startswith(";"):
            content = content[1:].strip()
        lowered = content.lower()

        if lowered.startswith("np") or lowered.startswith("noprefix"):
            args = content.split()
            if len(args) == 1:
                if not self.is_dev(message.author.id):
                    await message.channel.send(f"{CROSS_MARK} You are not a developer.")
                    return
                await message.channel.send("Usage: `np add @user` | `np remove @user` | `np list`")
                return

            sub = args[1].lower()

            # ── np add ───────────────────────────────────────────
            if sub == "add":
                if not self.is_dev(message.author.id):
                    await message.channel.send(f"{CROSS_MARK} You are not a developer.")
                    return

                target = None
                if message.mentions:
                    target = message.mentions[0]
                elif len(args) >= 3:
                    try:
                        uid = int(args[2])
                        target = message.guild.get_member(uid) or await self.bot.fetch_user(uid)
                    except Exception:
                        pass

                if not target:
                    await message.channel.send(f"{CROSS_MARK} Provide a user mention or ID. Example: `np add @User`")
                    return

                view = PlanView(self.bot, target, message.author, timeout=60)
                await message.channel.send(f"Choose a plan for {target.mention} — (60s to select)", view=view)
                return

            # ── np remove ────────────────────────────────────────
            if sub == "remove":
                if not self.is_dev(message.author.id):
                    await message.channel.send(f"{CROSS_MARK} You are not a developer.")
                    return

                target = None
                if message.mentions:
                    target = message.mentions[0]
                elif len(args) >= 3:
                    try:
                        uid = int(args[2])
                        target = message.guild.get_member(uid) or await self.bot.fetch_user(uid)
                    except Exception:
                        pass

                if not target:
                    await message.channel.send(f"{CROSS_MARK} Provide a user mention or ID. Example: `np remove @User`")
                    return

                async with aiosqlite.connect(CORE_DB) as db:
                    async with db.execute("SELECT plan FROM noprefix WHERE user_id = ?", (target.id,)) as cursor:
                        row = await cursor.fetchone()
                    if not row:
                        await message.channel.send(f"{CROSS_MARK} {target.mention} does not have NoPrefix.")
                        return
                    await db.execute("DELETE FROM noprefix WHERE user_id = ?", (target.id,))
                    await db.commit()

                plan = row[0]
                try:
                    await target.send(embed=discord.Embed(
                        title=f"{CHECK} NoPrefix Removed",
                        description=f"Your **{plan}** NoPrefix has been removed.",
                        color=0x525252,
                        timestamp=datetime.utcnow()
                    ))
                except Exception:
                    pass

                await message.channel.send(f"{CHECK} Removed NoPrefix from {target.mention}")

                log_ch = self.bot.get_channel(LOG_CHANNEL_ID) or await safe_fetch_channel(self.bot, LOG_CHANNEL_ID)
                if log_ch:
                    embed = discord.Embed(title="NoPrefix Removed", color=0x525252, timestamp=datetime.utcnow())
                    embed.add_field(name="User",       value=f"{target} (`{target.id}`)", inline=False)
                    embed.add_field(name="Plan",       value=plan,               inline=True)
                    embed.add_field(name="Removed by", value=f"{message.author} (`{message.author.id}`)", inline=False)
                    await safe_send(log_ch, embed=embed)
                return

            # ── np list ──────────────────────────────────────────
            if sub == "list":
                if not self.is_dev(message.author.id):
                    await message.channel.send(f"{CROSS_MARK} You are not a developer.")
                    return

                async with aiosqlite.connect(CORE_DB) as db:
                    async with db.execute("SELECT user_id, plan, expires FROM noprefix") as cursor:
                        rows = await cursor.fetchall()

                if not rows:
                    await message.channel.send("No active NoPrefix users.")
                    return

                embed = discord.Embed(title="Active NoPrefix Users", color=0x525252, timestamp=datetime.utcnow())
                for uid, plan, expires_str in rows:
                    user_obj = self.bot.get_user(uid)
                    name = user_obj.mention if user_obj else str(uid)

                    if is_lifetime(plan) or expires_str == LIFETIME_SENTINEL:
                        rem_text = "Lifetime (never expires)"
                    else:
                        try:
                            remaining = (parse_iso(expires_str) - datetime.utcnow()).days
                            rem_text = f"{remaining} days left"
                        except Exception:
                            rem_text = "unknown"

                    embed.add_field(
                        name=f"{plan} — {name}",
                        value=rem_text,
                        inline=False
                    )
                await message.channel.send(embed=embed)
                return

        # ── Allow NP users to run commands without prefix ────────
        async with aiosqlite.connect(CORE_DB) as db:
            async with db.execute("SELECT plan, expires FROM noprefix WHERE user_id = ?", (message.author.id,)) as cursor:
                row = await cursor.fetchone()

        if row:
            plan, expires_str = row

            # Lifetime — always valid
            if not is_lifetime(plan) and expires_str != LIFETIME_SENTINEL:
                try:
                    if parse_iso(expires_str) <= datetime.utcnow():
                        async with aiosqlite.connect(CORE_DB) as db:
                            await db.execute("DELETE FROM noprefix WHERE user_id = ?", (message.author.id,))
                            await db.commit()
                        try:
                            await message.author.send(embed=discord.Embed(
                                title="NoPrefix Expired",
                                description="Your NoPrefix has expired.",
                                color=0x525252,
                                timestamp=datetime.utcnow()
                            ))
                        except Exception:
                            pass
                        return
                except Exception:
                    return

            ctx = await self.bot.get_context(message)
            if ctx.valid:
                return

            try:
                prefix = await self.bot.get_prefix(message)
                if isinstance(prefix, (list, tuple)):
                    prefix = prefix[0]
            except Exception:
                prefix = ";"

            message.content = f"{prefix}{message.content}"
            await self.bot.process_commands(message)


async def setup(bot: commands.Bot):
    manager = NPManager(bot)
    await manager.start()
