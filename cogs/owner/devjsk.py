# cogs/devjsk.py - Enhanced Developer Commands (Owner Only)
import discord
from discord.ext import commands
import asyncio
import sys
import os
import time
import platform
import psutil
import inspect
import traceback
import aiosqlite
import subprocess
from pathlib import Path
from io import StringIO
from datetime import datetime, timezone

# Import DEVELOPER_IDS from main (single source of truth)
sys.path.insert(0, str(Path(__file__).parent.parent))
from main import DEVELOPER_IDS

def is_developer():
    async def predicate(ctx):
        return ctx.author.id in DEVELOPER_IDS
    return commands.check(predicate)


class DevJsk(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self._last_result = None

    # ──────────────────────────────────────────────
    # HELPERS
    # ──────────────────────────────────────────────

    def cleanup_code(self, content: str) -> str:
        if content.startswith("```") and content.endswith("```"):
            content = "\n".join(content.split("\n")[1:-1])
        return content.strip("`\n ")

    async def send_paginated(self, ctx, text: str, prefix="```", suffix="```"):
        """Send long output in paginated code blocks."""
        limit = 1990 - len(prefix) - len(suffix)
        pages = [text[i:i+limit] for i in range(0, len(text), limit)]
        for page in pages:
            await ctx.send(f"{prefix}{page}{suffix}")

    # ──────────────────────────────────────────────
    # HELP MENU
    # ──────────────────────────────────────────────

    @commands.command(name="devjsk")
    @is_developer()
    async def devjsk(self, ctx):
        """DevJsk: Full list of developer commands (Owner Only)."""
        content = """
**╔══ DevJsk Command List ══╗**

**📋 Info & Help**
`devjsk` — This list
`dev botinfo` — Full bot statistics
`dev ping` — Latency breakdown
`dev uptime` — Bot uptime
`dev sys` — System info (CPU/RAM/OS)

**⚙️ Bot Control**
`dev restart` — Restart the bot
`dev shutdown` — Shut down the bot
`dev setgame <text>` — Change activity status
`dev setstatus <online/idle/dnd/invis>` — Change status

**🧩 Extensions**
`dev load <ext>` — Load a cog
`dev unload <ext>` — Unload a cog
`dev reload <ext>` — Reload a cog (use `~` for all)
`dev listcogs` — List all loaded/unloaded cogs

**🐍 Python Eval**
`dev py <code>` — Execute Python code
`dev pyi <code>` — Inspect/eval expression
`dev sh <cmd>` — Run shell command

**🗄️ Database**
`dev sql <query>` — Run raw SQL on core.db
`dev dbinfo` — List all DB files and sizes

**🌐 Guild Tools**
`dev guilds` — List all guilds bot is in
`dev guildinfo <id>` — Info about a guild
`dev leaveserver <id>` — Leave a guild
`dev announce <msg>` — DM all guild owners

**👤 User Tools**
`dev userinfo <id>` — Lookup any user by ID
`dev dm <user_id> <msg>` — DM any user
`dev blacklist <user_id>` — Blacklist a user
`dev unblacklist <user_id>` — Remove blacklist

**💾 Cache**
`dev clearcache` — Clear bot's internal cache
`dev tasks` — View running asyncio tasks
`dev cancel <id>` — Cancel an asyncio task

**🔧 Misc**
`dev source <cmd>` — Show source of a command
`dev rtt` — Round-trip latency test
`dev sync` — Sync slash commands globally
`dev eval` — Alias for dev py

Owner only. All commands require dev ID.
"""
        await ctx.send(content)

    # ──────────────────────────────────────────────
    # PYTHON EVAL
    # ──────────────────────────────────────────────

    @commands.group(name="dev", invoke_without_command=True)
    @is_developer()
    async def dev(self, ctx):
        await ctx.invoke(self.devjsk)

    @dev.command(name="py", aliases=["eval"])
    @is_developer()
    async def dev_py(self, ctx, *, code: str):
        """Execute Python code."""
        code = self.cleanup_code(code)
        env = {
            "bot": self.bot,
            "ctx": ctx,
            "guild": ctx.guild,
            "channel": ctx.channel,
            "author": ctx.author,
            "message": ctx.message,
            "_": self._last_result,
            "discord": discord,
            "commands": commands,
            "asyncio": asyncio,
        }

        stdout = StringIO()
        to_compile = f"async def __exec():\n" + "\n".join(f"  {l}" for l in code.splitlines())

        try:
            exec(compile(to_compile, "<dev>", "exec"), env)
        except SyntaxError as e:
            return await ctx.send(f"```py\n{e}\n```")

        func = env["__exec"]
        try:
            import contextlib
            with contextlib.redirect_stdout(stdout):
                ret = await func()
        except Exception:
            value = stdout.getvalue()
            return await ctx.send(f"```py\n{value}{traceback.format_exc()}\n```")

        value = stdout.getvalue()
        if ret is not None:
            self._last_result = ret
            result = f"{value}{ret}"
        else:
            result = value or "✅ Executed (no output)"

        if len(result) > 1990:
            await self.send_paginated(ctx, result, "```py\n", "\n```")
        else:
            await ctx.send(f"```py\n{result}\n```")

    @dev.command(name="pyi")
    @is_developer()
    async def dev_pyi(self, ctx, *, code: str):
        """Inspect an expression."""
        code = self.cleanup_code(code)
        env = {"bot": self.bot, "ctx": ctx, "guild": ctx.guild, "_": self._last_result}
        try:
            result = eval(code, env)
            output = (
                f"Type    : {type(result).__name__}\n"
                f"Value   : {result!r}\n"
                f"Module  : {getattr(type(result), '__module__', 'N/A')}\n"
                f"MRO     : {[c.__name__ for c in type(result).__mro__]}"
            )
            await ctx.send(f"```py\n{output}\n```")
        except Exception as e:
            await ctx.send(f"```py\n{traceback.format_exc()}\n```")

    @dev.command(name="sh")
    @is_developer()
    async def dev_sh(self, ctx, *, cmd: str):
        """Run a shell command."""
        try:
            proc = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=30)
            output = (stdout.decode() + stderr.decode()).strip() or "✅ No output"
            await self.send_paginated(ctx, output, "```sh\n", "\n```")
        except asyncio.TimeoutError:
            await ctx.send("❌ Command timed out (30s).")
        except Exception as e:
            await ctx.send(f"❌ Error: `{e}`")

    # ──────────────────────────────────────────────
    # BOT INFO & STATUS
    # ──────────────────────────────────────────────

    @dev.command(name="botinfo")
    @is_developer()
    async def dev_botinfo(self, ctx):
        """Full bot statistics."""
        proc = psutil.Process()
        mem = proc.memory_info().rss / 1024 ** 2
        cpu = psutil.cpu_percent(interval=0.5)
        uptime_s = int(time.time() - proc.create_time())
        h, r = divmod(uptime_s, 3600)
        m, s = divmod(r, 60)

        total_members = sum(g.member_count or 0 for g in self.bot.guilds)
        text_channels = sum(len(g.text_channels) for g in self.bot.guilds)
        voice_channels = sum(len(g.voice_channels) for g in self.bot.guilds)

        embed = discord.Embed(title="🤖 Bot Info", color=0x2b2d31, timestamp=datetime.now(timezone.utc))
        embed.add_field(name="Bot", value=f"`{self.bot.user}` (`{self.bot.user.id}`)", inline=False)
        embed.add_field(name="Guilds", value=f"`{len(self.bot.guilds)}`", inline=True)
        embed.add_field(name="Members", value=f"`{total_members:,}`", inline=True)
        embed.add_field(name="Channels", value=f"Text `{text_channels}` | Voice `{voice_channels}`", inline=True)
        embed.add_field(name="Commands", value=f"`{len(self.bot.commands)}`", inline=True)
        embed.add_field(name="Cogs", value=f"`{len(self.bot.cogs)}`", inline=True)
        embed.add_field(name="Latency", value=f"`{round(self.bot.latency * 1000)}ms`", inline=True)
        embed.add_field(name="Uptime", value=f"`{h}h {m}m {s}s`", inline=True)
        embed.add_field(name="RAM", value=f"`{mem:.1f} MB`", inline=True)
        embed.add_field(name="CPU", value=f"`{cpu}%`", inline=True)
        embed.add_field(name="Python", value=f"`{sys.version.split()[0]}`", inline=True)
        embed.add_field(name="discord.py", value=f"`{discord.__version__}`", inline=True)
        await ctx.send(embed=embed)

    @dev.command(name="ping")
    @is_developer()
    async def dev_ping(self, ctx):
        """Latency breakdown."""
        ws = round(self.bot.latency * 1000)
        t1 = time.perf_counter()
        msg = await ctx.send("🏓 Pinging...")
        rest = round((time.perf_counter() - t1) * 1000)
        t2 = time.perf_counter()
        await msg.edit(content="🏓 Computing typing...")
        typing = round((time.perf_counter() - t2) * 1000)
        await msg.edit(content=(
            f"🏓 **Pong!**\n"
            f"Websocket: `{ws}ms`\n"
            f"REST: `{rest}ms`\n"
            f"Typing: `{typing}ms`"
        ))

    @dev.command(name="uptime")
    @is_developer()
    async def dev_uptime(self, ctx):
        """Bot uptime."""
        proc = psutil.Process()
        uptime_s = int(time.time() - proc.create_time())
        h, r = divmod(uptime_s, 3600)
        m, s = divmod(r, 60)
        d, h = divmod(h, 24)
        await ctx.send(f"⏱️ Uptime: `{d}d {h}h {m}m {s}s`")

    @dev.command(name="sys")
    @is_developer()
    async def dev_sys(self, ctx):
        """System info."""
        mem = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        output = (
            f"OS      : {platform.system()} {platform.release()}\n"
            f"CPU     : {psutil.cpu_percent()}% ({psutil.cpu_count()} cores)\n"
            f"RAM     : {mem.used/1024**2:.0f}/{mem.total/1024**2:.0f} MB ({mem.percent}%)\n"
            f"Disk    : {disk.used/1024**3:.1f}/{disk.total/1024**3:.1f} GB ({disk.percent}%)\n"
            f"Python  : {sys.version.split()[0]}\n"
            f"PID     : {os.getpid()}"
        )
        await ctx.send(f"```\n{output}\n```")

    @dev.command(name="rtt")
    @is_developer()
    async def dev_rtt(self, ctx):
        """Round-trip latency test (5 samples)."""
        results = []
        msg = await ctx.send("📡 Measuring RTT...")
        for i in range(5):
            t = time.perf_counter()
            await msg.edit(content=f"📡 Sample {i+1}/5...")
            results.append(round((time.perf_counter() - t) * 1000))
            await asyncio.sleep(0.3)
        avg = sum(results) / len(results)
        await msg.edit(content=(
            f"📡 **RTT Results**\n"
            f"Samples : `{results}`\n"
            f"Average : `{avg:.1f}ms`\n"
            f"Min/Max : `{min(results)}ms` / `{max(results)}ms`"
        ))

    # ──────────────────────────────────────────────
    # BOT CONTROL
    # ──────────────────────────────────────────────

    @dev.command(name="restart")
    @is_developer()
    async def dev_restart(self, ctx):
        """Restart the bot."""
        await ctx.send("<a:reload:1508670175749341204> Restarting...")
        await self.bot.close()
        os.execv(sys.executable, [sys.executable] + sys.argv)

    @dev.command(name="shutdown")
    @is_developer()
    async def dev_shutdown(self, ctx):
        """Shut down the bot."""
        await ctx.send("🛑 Shutting down...")
        await self.bot.close()

    @dev.command(name="setgame")
    @is_developer()
    async def dev_setgame(self, ctx, *, text: str):
        """Change the bot's activity."""
        await self.bot.change_presence(activity=discord.CustomActivity(name=text))
        await ctx.send(f"✅ Activity set to: `{text}`")

    @dev.command(name="setstatus")
    @is_developer()
    async def dev_setstatus(self, ctx, status: str):
        """Change bot's online status. (online/idle/dnd/invis)"""
        statuses = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invis": discord.Status.invisible,
            "invisible": discord.Status.invisible,
        }
        s = statuses.get(status.lower())
        if not s:
            return await ctx.send(f"❌ Unknown status. Use: `{', '.join(statuses)}`")
        await self.bot.change_presence(status=s)
        await ctx.send(f"✅ Status set to `{status}`")

    # ──────────────────────────────────────────────
    # EXTENSIONS
    # ──────────────────────────────────────────────

    @dev.command(name="load")
    @is_developer()
    async def dev_load(self, ctx, *, ext: str):
        """Load a cog."""
        try:
            await self.bot.load_extension(ext)
            await ctx.send(f"✅ Loaded `{ext}`")
        except Exception as e:
            await ctx.send(f"❌ `{ext}`: `{e}`")

    @dev.command(name="unload")
    @is_developer()
    async def dev_unload(self, ctx, *, ext: str):
        """Unload a cog."""
        try:
            await self.bot.unload_extension(ext)
            await ctx.send(f"✅ Unloaded `{ext}`")
        except Exception as e:
            await ctx.send(f"❌ `{ext}`: `{e}`")

    @dev.command(name="reload")
    @is_developer()
    async def dev_reload(self, ctx, *, ext: str = "~"):
        """Reload a cog. Use `~` to reload all."""
        if ext == "~":
            loaded = list(self.bot.extensions.keys())
            ok, fail = [], []
            for e in loaded:
                try:
                    await self.bot.reload_extension(e)
                    ok.append(e)
                except Exception as err:
                    fail.append(f"{e}: {err}")
            msg = f"🔄 Reloaded `{len(ok)}` cogs."
            if fail:
                msg += f"\n❌ Failed:\n" + "\n".join(f"`{f}`" for f in fail)
            await ctx.send(msg)
        else:
            try:
                await self.bot.reload_extension(ext)
                await ctx.send(f"🔄 Reloaded `{ext}`")
            except Exception as e:
                await ctx.send(f"❌ `{ext}`: `{e}`")

    @dev.command(name="listcogs")
    @is_developer()
    async def dev_listcogs(self, ctx):
        """List all loaded cogs and available files."""
        loaded = set(self.bot.extensions.keys())
        files = set(
            f"cogs.{p.stem}"
            for p in Path("cogs").glob("*.py")
            if not p.name.startswith("_")
        )
        unloaded = files - loaded

        lines = ["**✅ Loaded:**"]
        lines += [f"  `{e}`" for e in sorted(loaded)] or ["  none"]
        lines += ["\n**❌ Unloaded:**"]
        lines += [f"  `{e}`" for e in sorted(unloaded)] or ["  none"]
        await ctx.send("\n".join(lines))

    # ──────────────────────────────────────────────
    # DATABASE
    # ──────────────────────────────────────────────

    @dev.command(name="sql")
    @is_developer()
    async def dev_sql(self, ctx, *, query: str):
        """Run raw SQL on core.db."""
        try:
            async with aiosqlite.connect("db/core.db") as db:
                async with db.execute(query) as cursor:
                    rows = await cursor.fetchmany(20)
                    if cursor.description:
                        headers = [d[0] for d in cursor.description]
                        lines = [" | ".join(headers)]
                        lines += ["-" * len(lines[0])]
                        lines += [" | ".join(str(v) for v in row) for row in rows]
                        result = "\n".join(lines) or "No rows returned."
                    else:
                        await db.commit()
                        result = f"✅ Query OK. Rows affected: {cursor.rowcount}"
            await self.send_paginated(ctx, result, "```\n", "\n```")
        except Exception as e:
            await ctx.send(f"❌ SQL Error: `{e}`")

    @dev.command(name="dbinfo")
    @is_developer()
    async def dev_dbinfo(self, ctx):
        """Show all database files and sizes."""
        db_dir = Path("db")
        if not db_dir.exists():
            return await ctx.send("❌ No `db/` directory found.")
        lines = []
        for f in sorted(db_dir.glob("*.db")):
            size = f.stat().st_size / 1024
            lines.append(f"`{f.name}` — `{size:.1f} KB`")
        await ctx.send("🗄️ **Databases:**\n" + "\n".join(lines) if lines else "No databases found.")

    # ──────────────────────────────────────────────
    # GUILD TOOLS
    # ──────────────────────────────────────────────

    @dev.command(name="guilds")
    @is_developer()
    async def dev_guilds(self, ctx):
        """List all guilds."""
        guilds = sorted(self.bot.guilds, key=lambda g: g.member_count or 0, reverse=True)
        lines = [f"`{g.id}` — **{g.name}** ({g.member_count} members)" for g in guilds[:30]]
        if len(guilds) > 30:
            lines.append(f"... and {len(guilds)-30} more")
        await ctx.send(f"🌐 **Guilds ({len(guilds)}):**\n" + "\n".join(lines))

    @dev.command(name="guildinfo")
    @is_developer()
    async def dev_guildinfo(self, ctx, guild_id: int):
        """Info about a specific guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send(f"❌ Guild `{guild_id}` not found.")
        embed = discord.Embed(title=guild.name, color=0x2b2d31)
        embed.add_field(name="ID", value=f"`{guild.id}`")
        embed.add_field(name="Owner", value=f"`{guild.owner}` (`{guild.owner_id}`)")
        embed.add_field(name="Members", value=f"`{guild.member_count}`")
        embed.add_field(name="Channels", value=f"Text `{len(guild.text_channels)}` | Voice `{len(guild.voice_channels)}`")
        embed.add_field(name="Roles", value=f"`{len(guild.roles)}`")
        embed.add_field(name="Boosts", value=f"`{guild.premium_subscription_count}`")
        embed.add_field(name="Created", value=f"<t:{int(guild.created_at.timestamp())}:R>")
        if guild.icon:
            embed.set_thumbnail(url=guild.icon.url)
        await ctx.send(embed=embed)

    @dev.command(name="leaveserver")
    @is_developer()
    async def dev_leaveserver(self, ctx, guild_id: int):
        """Leave a guild."""
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send(f"❌ Guild `{guild_id}` not found.")
        await guild.leave()
        await ctx.send(f"✅ Left guild `{guild.name}` (`{guild_id}`)")

    @dev.command(name="announce")
    @is_developer()
    async def dev_announce(self, ctx, *, message: str):
        """DM all guild owners an announcement."""
        ok, fail = 0, 0
        for guild in self.bot.guilds:
            try:
                await guild.owner.send(f"📢 **Announcement from {self.bot.user.name}:**\n{message}")
                ok += 1
                await asyncio.sleep(0.5)
            except Exception:
                fail += 1
        await ctx.send(f"📢 Sent to `{ok}` owners. Failed: `{fail}`")

    # ──────────────────────────────────────────────
    # USER TOOLS
    # ──────────────────────────────────────────────

    @dev.command(name="userinfo")
    @is_developer()
    async def dev_userinfo(self, ctx, user_id: int):
        """Lookup any user by ID."""
        try:
            user = await self.bot.fetch_user(user_id)
        except discord.NotFound:
            return await ctx.send(f"❌ User `{user_id}` not found.")
        embed = discord.Embed(title=str(user), color=0x2b2d31)
        embed.add_field(name="ID", value=f"`{user.id}`")
        embed.add_field(name="Bot", value=f"`{user.bot}`")
        embed.add_field(name="Created", value=f"<t:{int(user.created_at.timestamp())}:R>")
        if user.avatar:
            embed.set_thumbnail(url=user.avatar.url)
        await ctx.send(embed=embed)

    @dev.command(name="dm")
    @is_developer()
    async def dev_dm(self, ctx, user_id: int, *, message: str):
        """DM any user by ID."""
        try:
            user = await self.bot.fetch_user(user_id)
            await user.send(message)
            await ctx.send(f"✅ DM sent to `{user}` (`{user_id}`)")
        except Exception as e:
            await ctx.send(f"❌ Failed: `{e}`")

    @dev.command(name="blacklist")
    @is_developer()
    async def dev_blacklist(self, ctx, user_id: int):
        """Blacklist a user from using the bot."""
        async with aiosqlite.connect("db/core.db") as db:
            await db.execute(
                "CREATE TABLE IF NOT EXISTS blacklisted (user_id INTEGER PRIMARY KEY)"
            )
            await db.execute("INSERT OR IGNORE INTO blacklisted VALUES (?)", (user_id,))
            await db.commit()
        await ctx.send(f"🚫 User `{user_id}` blacklisted.")

    @dev.command(name="unblacklist")
    @is_developer()
    async def dev_unblacklist(self, ctx, user_id: int):
        """Remove a user from the blacklist."""
        async with aiosqlite.connect("db/core.db") as db:
            await db.execute("DELETE FROM blacklisted WHERE user_id = ?", (user_id,))
            await db.commit()
        await ctx.send(f"✅ User `{user_id}` removed from blacklist.")

    # ──────────────────────────────────────────────
    # CACHE & TASKS
    # ──────────────────────────────────────────────

    @dev.command(name="clearcache")
    @is_developer()
    async def dev_clearcache(self, ctx):
        """Clear bot's internal cache."""
        before = len(self.bot.guilds)
        self.bot._connection._messages.clear()
        await ctx.send(f"✅ Message cache cleared. Guilds cached: `{before}`")

    @dev.command(name="tasks")
    @is_developer()
    async def dev_tasks(self, ctx):
        """View running asyncio tasks."""
        tasks = asyncio.all_tasks()
        lines = []
        for i, task in enumerate(tasks, 1):
            name = task.get_name()
            done = "✅" if task.done() else "🔄"
            lines.append(f"`{i}` {done} `{name}`")
        if not lines:
            return await ctx.send("No tasks running.")
        await self.send_paginated(ctx, "\n".join(lines), "**Tasks:**\n", "")

    @dev.command(name="cancel")
    @is_developer()
    async def dev_cancel(self, ctx, task_id: int):
        """Cancel an asyncio task by index."""
        tasks = list(asyncio.all_tasks())
        if task_id < 1 or task_id > len(tasks):
            return await ctx.send(f"❌ Invalid task ID. Use `dev tasks` to list.")
        task = tasks[task_id - 1]
        task.cancel()
        await ctx.send(f"✅ Cancelled task `{task.get_name()}`")

    # ──────────────────────────────────────────────
    # MISC UTILS
    # ──────────────────────────────────────────────

    @dev.command(name="source")
    @is_developer()
    async def dev_source(self, ctx, *, cmd_name: str):
        """Show the source code of a command."""
        cmd = self.bot.get_command(cmd_name)
        if not cmd:
            return await ctx.send(f"❌ Command `{cmd_name}` not found.")
        try:
            source = inspect.getsource(cmd.callback)
            await self.send_paginated(ctx, source, "```py\n", "\n```")
        except Exception as e:
            await ctx.send(f"❌ Could not get source: `{e}`")

    @dev.command(name="sync")
    @is_developer()
    async def dev_sync(self, ctx):
        """Sync slash commands globally."""
        try:
            synced = await self.bot.tree.sync()
            await ctx.send(f"✅ Synced `{len(synced)}` slash commands globally.")
        except Exception as e:
            await ctx.send(f"❌ Sync failed: `{e}`")

    @dev.command(name="sudo")
    @is_developer()
    async def dev_sudo(self, ctx, member: discord.Member, *, cmd: str):
        """Run a command as another user."""
        fake_msg = ctx.message
        fake_msg = discord.Message
        new_ctx = await self.bot.get_context(ctx.message)
        new_ctx.author = member
        new_ctx.message.content = ctx.prefix + cmd
        try:
            await self.bot.invoke(new_ctx)
        except Exception as e:
            await ctx.send(f"❌ Sudo failed: `{e}`")


async def setup(bot):
    await bot.add_cog(DevJsk(bot))
