import discord
from discord.ext import commands, tasks
from discord import ui
from typing import Optional
import requests
from io import BytesIO
import aiosqlite
import os
import time
import re

# ================= CONFIG =================
DB_PATH = "db/utility.db"

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from emojis import (
    CHECK as EMOJI_CHECK,
    CROSS as EMOJI_CROSS,
    TIMER as EMOJI_TIMER,
    REPLY as EMOJI_REPLY,
    BELL as EMOJI_BELL
)


# ================= UI HELPER =================
async def ui_message(ctx, title: str, text: str):
    view = ui.LayoutView(timeout=120)
    view.add_item(
        ui.Container(
            ui.TextDisplay(f"# {title}"),
            ui.Separator(),
            ui.TextDisplay(text)
        )
    )
    await ctx.send(view=view)


class Utility(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        os.makedirs("db", exist_ok=True)
        bot.loop.create_task(self._startup())

    async def _startup(self):
        await self._init_db()
        self.timer_loop.start()

    # ================= DATABASE =================
    async def _init_db(self):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.executescript("""
            CREATE TABLE IF NOT EXISTS timers (
                channel INTEGER,
                user INTEGER,
                end INTEGER
            );

            CREATE TABLE IF NOT EXISTS autoresponders (
                guild INTEGER,
                trigger TEXT,
                response TEXT
            );

            CREATE TABLE IF NOT EXISTS autoreacts (
                guild INTEGER,
                trigger TEXT,
                emoji TEXT
            );
            """)
            await db.commit()

    # ================= AVATAR / BANNER =================
    async def _send_media(self, ctx, user, asset: discord.Asset, title: str):
        fmt = "gif" if asset.is_animated() else "png"
        filename = f"{title.lower()}.{fmt}"

        data = BytesIO(
            requests.get(asset.replace(size=1024, format=fmt).url).content
        )

        gallery = ui.MediaGallery()
        gallery.add_item(media=f"attachment://{filename}")

        buttons = [
            ui.Button(label="PNG", url=asset.replace(size=1024, format="png").url),
            ui.Button(label="JPG", url=asset.replace(size=1024, format="jpg").url),
            ui.Button(label="WEBP", url=asset.replace(size=1024, format="webp").url),
        ]
        if asset.is_animated():
            buttons.append(
                ui.Button(label="GIF", url=asset.replace(size=1024, format="gif").url)
            )

        view = ui.LayoutView(timeout=120)
        view.add_item(
            ui.Container(
                ui.TextDisplay(f"# {user.name}'s {title}"),
                ui.Separator(),
                gallery,
                ui.Separator(),
                ui.ActionRow(*buttons)
            )
        )

        await ctx.send(view=view, files=[discord.File(data, filename)])

    @commands.command(name="avatar", aliases=["av", "pfp"])
    async def avatar(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        await self._send_media(ctx, member, member.display_avatar, "Avatar")

    @commands.command(name="banner")
    async def banner(self, ctx, member: Optional[discord.Member] = None):
        member = member or ctx.author
        user = await self.bot.fetch_user(member.id)

        if not user.banner:
            return await ui_message(ctx, "Banner", f"{EMOJI_CROSS} User has no banner")

        await self._send_media(ctx, user, user.banner, "Banner")

    # ================= SERVER INFO =================
    @commands.command(name="serverinfo", aliases=["si", "server", "guildinfo"])
    async def serverinfo(self, ctx):
        g = ctx.guild
        await g.chunk()  # ensure member cache is populated

        # ── counts ──────────────────────────────────────────────
        total      = g.member_count
        bots       = sum(1 for m in g.members if m.bot)
        humans     = total - bots
        online     = sum(1 for m in g.members if not m.bot and m.status != discord.Status.offline)
        text_ch    = len(g.text_channels)
        voice_ch   = len(g.voice_channels)
        stage_ch   = len(g.stage_channels)
        cat_count  = len(g.categories)
        roles      = len(g.roles) - 1          # exclude @everyone
        emojis     = len(g.emojis)
        stickers   = len(g.stickers)
        animated   = sum(1 for e in g.emojis if e.animated)
        static_em  = emojis - animated

        # ── boost ───────────────────────────────────────────────
        boost_lvl  = g.premium_tier
        boosts     = g.premium_subscription_count or 0
        booster_role = g.premium_subscriber_role
        booster_str  = booster_role.mention if booster_role else "None"

        # ── system channels ─────────────────────────────────────
        rules_ch   = g.rules_channel.mention   if g.rules_channel   else "None"
        updates_ch = g.public_updates_channel.mention if g.public_updates_channel else "None"
        system_ch  = g.system_channel.mention  if g.system_channel  else "None"
        afk_ch     = g.afk_channel.mention     if g.afk_channel     else "None"
        afk_to     = f"{g.afk_timeout // 60}m" if g.afk_channel    else "None"

        # ── misc ────────────────────────────────────────────────
        vanity     = g.vanity_url_code or "None"
        desc       = g.description or "No description set"
        locale     = str(g.preferred_locale)
        mfa        = "Enabled" if g.mfa_level else "Disabled"
        content_filter = str(g.explicit_content_filter).replace("_", " ").title()
        verif      = str(g.verification_level).title()
        created_ts = int(g.created_at.timestamp())

        # ── features ────────────────────────────────────────────
        features_list = [f.replace("_", " ").title() for f in g.features] if g.features else []
        features_str  = ", ".join(features_list) if features_list else "None"

        # ── build text sections ─────────────────────────────────
        general_txt = (
            f"**ID:** {g.id}\n"
            f"**Owner:** {g.owner.mention if g.owner else 'Unknown'}\n"
            f"**Created:** <t:{created_ts}:F>\n"
            f"**Description:** {desc}\n"
            f"**Locale:** {locale}\n"
            f"**Vanity URL:** {vanity}"
        )

        members_txt = (
            f"**Total:** {total}\n"
            f"**Humans:** {humans}\n"
            f"**Bots:** {bots}\n"
            f"**Online:** {online}"
        )

        channels_txt = (
            f"**AFK:** {afk_ch} ({afk_to})\n"
            f"**Text:** {text_ch}\n"
            f"**Voice:** {voice_ch}\n"
            f"**Stage:** {stage_ch}\n"
            f"**Categories:** {cat_count}"
        )

        roles_media_txt = (
            f"**Roles:** {roles}\n"
            f"**Emojis:** {emojis} ({static_em} static / {animated} animated)\n"
            f"**Stickers:** {stickers}"
        )

        boosting_txt = (
            f"**Level:** {boost_lvl}\n"
            f"**Boosts:** {boosts}\n"
            f"**Booster Role:** {booster_str}"
        )

        security_txt = (
            f"**Verification:** {verif}\n"
            f"**Content Filter:** {content_filter}\n"
            f"**2FA Requirement:** {mfa}"
        )

        system_txt = (
            f"**Rules:** {rules_ch}\n"
            f"**Updates:** {updates_ch}\n"
            f"**System Msgs:** {system_ch}"
        )

        features_txt = f"**Features:** {features_str}"

        # ── build buttons ────────────────────────────────────────
        icon_btn    = ui.Button(label="Server Icon",   style=discord.ButtonStyle.secondary, custom_id="si_icon")
        banner_btn  = ui.Button(label="Server Banner", style=discord.ButtonStyle.secondary, custom_id="si_banner")
        splash_btn  = ui.Button(label="Splash",        style=discord.ButtonStyle.secondary, custom_id="si_splash")
        features_btn = ui.Button(label="Features",     style=discord.ButtonStyle.secondary, custom_id="si_features")

        # disable buttons for missing assets
        if not g.icon:    icon_btn.disabled    = True
        if not g.banner:  banner_btn.disabled  = True
        if not g.splash:  splash_btn.disabled  = True

        # ── requester footer ─────────────────────────────────────
        footer_txt = f"Requested By {ctx.author.display_name} | Today at {discord.utils.utcnow().strftime('%-I:%M %p')}"

        # ── layout ───────────────────────────────────────────────
        view = ui.LayoutView(timeout=120)

        async def _send_asset(interaction: discord.Interaction, asset: discord.Asset, title: str):
            await interaction.response.defer(ephemeral=True)
            fmt = "gif" if asset.is_animated() else "png"
            fname = f"{title.lower()}.{fmt}"
            data = BytesIO(requests.get(asset.replace(size=1024, format=fmt).url).content)
            btns = [
                ui.Button(label="PNG",  url=asset.replace(size=1024, format="png").url),
                ui.Button(label="JPG",  url=asset.replace(size=1024, format="jpg").url),
                ui.Button(label="WEBP", url=asset.replace(size=1024, format="webp").url),
            ]
            if asset.is_animated():
                btns.append(ui.Button(label="GIF", url=asset.replace(size=1024, format="gif").url))
            gal = ui.MediaGallery()
            gal.add_item(media=f"attachment://{fname}")
            v2 = ui.LayoutView(timeout=60)
            v2.add_item(ui.Container(
                ui.TextDisplay(f"# {g.name} — {title}"),
                ui.Separator(),
                gal,
                ui.Separator(),
                ui.ActionRow(*btns)
            ))
            await interaction.followup.send(view=v2, files=[discord.File(data, fname)], ephemeral=True)

        async def _show_features(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            txt = "\n".join(f"• {f}" for f in features_list) if features_list else "No special features."
            v2 = ui.LayoutView(timeout=60)
            v2.add_item(ui.Container(
                ui.TextDisplay(f"# {g.name} — Features"),
                ui.Separator(),
                ui.TextDisplay(txt)
            ))
            await interaction.followup.send(view=v2, ephemeral=True)

        icon_btn.callback     = lambda i: _send_asset(i, g.icon,   "Server Icon")
        banner_btn.callback   = lambda i: _send_asset(i, g.banner, "Server Banner")
        splash_btn.callback   = lambda i: _send_asset(i, g.splash, "Splash")
        features_btn.callback = _show_features

        view.add_item(
            ui.Container(
                ui.TextDisplay(f"# {g.name}"),
                ui.Separator(),

                ui.TextDisplay("**General**"),
                ui.TextDisplay(general_txt),
                ui.Separator(),

                ui.TextDisplay("**Members**"),
                ui.TextDisplay(members_txt),
                ui.Separator(),

                ui.TextDisplay("**Channels**"),
                ui.TextDisplay(channels_txt),
                ui.Separator(),

                ui.TextDisplay("**Roles & Media**"),
                ui.TextDisplay(roles_media_txt),
                ui.Separator(),

                ui.TextDisplay("**Boosting**"),
                ui.TextDisplay(boosting_txt),
                ui.Separator(),

                ui.TextDisplay("**Security**"),
                ui.TextDisplay(security_txt),
                ui.Separator(),

                ui.TextDisplay("**System Channels**"),
                ui.TextDisplay(system_txt),
                ui.Separator(),

                ui.TextDisplay(features_txt),
                ui.Separator(),

                ui.TextDisplay(f"-# {footer_txt}"),
                ui.ActionRow(icon_btn, banner_btn, splash_btn),
                ui.ActionRow(features_btn),

                accent_color=discord.Color.from_str("#000000")
            )
        )

        await ctx.send(view=view)

    # ================= TIMER =================
    @commands.command(name="timer")
    async def timer(self, ctx, seconds: int):
        if seconds <= 0:
            return await ui_message(ctx, "Timer", f"{EMOJI_CROSS} Invalid time")

        end = int(time.time()) + seconds
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO timers VALUES (?, ?, ?)",
                (ctx.channel.id, ctx.author.id, end)
            )
            await db.commit()

        await ui_message(ctx, "Timer Started", f"{EMOJI_TIMER} Ends <t:{end}:R>")

    @tasks.loop(seconds=5)
    async def timer_loop(self):
        now = int(time.time())
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall(
                "SELECT rowid, channel, user FROM timers WHERE end<=?",
                (now,)
            )

            for rid, ch, uid in rows:
                channel = self.bot.get_channel(ch)
                if channel:
                    await channel.send(f"{EMOJI_TIMER} <@{uid}> your timer ended")
                await db.execute("DELETE FROM timers WHERE rowid=?", (rid,))
            await db.commit()

    # ================= AUTORESPONDER COMMANDS =================
    @commands.group(name="ar", invoke_without_command=True)
    async def ar(self, ctx):
        await ui_message(
            ctx,
            "Autoresponder",
            "`ar add <word> <reply>`\n`ar remove <word>`\n`ar list`"
        )

    @ar.command(name="add")
    @commands.has_permissions(manage_messages=True)
    async def ar_add(self, ctx, trigger: str, *, response: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO autoresponders VALUES (?, ?, ?)",
                (ctx.guild.id, trigger.lower(), response)
            )
            await db.commit()

        await ui_message(ctx, "Autoresponder", f"{EMOJI_CHECK} Added `{trigger}`")

    @ar.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def ar_remove(self, ctx, trigger: str):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "DELETE FROM autoresponders WHERE guild=? AND trigger=?",
                (ctx.guild.id, trigger.lower())
            )
            await db.commit()

        await ui_message(
            ctx,
            "Autoresponder",
            f"{EMOJI_CHECK} Removed `{trigger}`"
            if cur.rowcount else f"{EMOJI_CROSS} Trigger not found"
        )

    @ar.command(name="list")
    async def ar_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall(
                "SELECT trigger, response FROM autoresponders WHERE guild=?",
                (ctx.guild.id,)
            )

        if not rows:
            return await ui_message(ctx, "Autoresponder", f"{EMOJI_CROSS} None set")

        await ui_message(
            ctx,
            "Autoresponders",
            "\n".join(f"`{t}` → {r}" for t, r in rows)
        )

    # ================= AUTOREACT COMMANDS =================
    @commands.group(name="react", invoke_without_command=True)
    async def react(self, ctx):
        await ui_message(
            ctx,
            "Autoreact",
            "`react add <word | @user | @role> <emoji>`\n`react remove <trigger>`\n`react list`"
        )

    @react.command(name="add")
    @commands.has_permissions(manage_messages=True)
    async def react_add(self, ctx, trigger: str, emoji: str):
        async with aiosqlite.connect(DB_PATH) as db:
            await db.execute(
                "INSERT INTO autoreacts VALUES (?, ?, ?)",
                (ctx.guild.id, trigger.lower(), emoji)
            )
            await db.commit()

        await ui_message(ctx, "Autoreact", f"{EMOJI_CHECK} Added `{trigger}` → {emoji}")

    @react.command(name="remove")
    @commands.has_permissions(manage_messages=True)
    async def react_remove(self, ctx, trigger: str):
        async with aiosqlite.connect(DB_PATH) as db:
            cur = await db.execute(
                "DELETE FROM autoreacts WHERE guild=? AND trigger=?",
                (ctx.guild.id, trigger.lower())
            )
            await db.commit()

        await ui_message(
            ctx,
            "Autoreact",
            f"{EMOJI_CHECK} Removed `{trigger}`"
            if cur.rowcount else f"{EMOJI_CROSS} Trigger not found"
        )

    @react.command(name="list")
    async def react_list(self, ctx):
        async with aiosqlite.connect(DB_PATH) as db:
            rows = await db.execute_fetchall(
                "SELECT trigger, emoji FROM autoreacts WHERE guild=?",
                (ctx.guild.id,)
            )

        if not rows:
            return await ui_message(ctx, "Autoreact", f"{EMOJI_CROSS} None set")

        await ui_message(
            ctx,
            "Autoreacts",
            "\n".join(f"`{t}` → {e}" for t, e in rows)
        )

    # ================= LISTENER =================
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot:
            return

        if message.guild:
            content = message.content.lower()
            words = re.findall(r"\b\w+\b", content)

            async with aiosqlite.connect(DB_PATH) as db:
                ars = await db.execute_fetchall(
                    "SELECT trigger, response FROM autoresponders WHERE guild=?",
                    (message.guild.id,)
                )
                reacts = await db.execute_fetchall(
                    "SELECT trigger, emoji FROM autoreacts WHERE guild=?",
                    (message.guild.id,)
                )

            # EXACT autoresponder
            for t, r in ars:
                if content.strip() == t:
                    await message.reply(f"{EMOJI_REPLY} {r}")
                    break

            # WORD / MENTION autoreact
            for t, e in reacts:
                if (
                    t in words or
                    any(t == f"<@{m.id}>" or t == f"<@!{m.id}>" for m in message.mentions) or
                    any(t == f"<@&{r.id}>" for r in message.role_mentions)
                ):
                    try:
                        await message.add_reaction(e)
                    except:
                        pass
                    break

       # await self.bot.process_commands(message)


async def setup(bot):
    await bot.add_cog(Utility(bot))
