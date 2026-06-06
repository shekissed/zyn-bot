"""
roleplay.py — Fun & roleplay commands with GIF support.
Commands: hug, kiss, slap, ship, pat, poke, cuddle, punch,
          bite, lick, wave, cry, dance, blush, smile, wink,
          highfive, feed, kill, stare, throw, tickle, yeet
"""

import discord
from discord.ext import commands
import aiohttp
import random
import io
import os
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

# ── GIF endpoints (nekos.best — free, no key required) ───────────────────────

NEKOS_BASE = "https://nekos.best/api/v2"

ROLEPLAY_ACTIONS = {
    "hug":       {"url": f"{NEKOS_BASE}/hug",       "color": 0x000000, "solo": False},
    "kiss":      {"url": f"{NEKOS_BASE}/kiss",      "color": 0x000000, "solo": False},
    "slap":      {"url": f"{NEKOS_BASE}/slap",      "color": 0x000000, "solo": False},
    "pat":       {"url": f"{NEKOS_BASE}/pat",       "color": 0x000000, "solo": False},
    "poke":      {"url": f"{NEKOS_BASE}/poke",      "color": 0x000000, "solo": False},
    "cuddle":    {"url": f"{NEKOS_BASE}/cuddle",    "color": 0x000000, "solo": False},
    "punch":     {"url": f"{NEKOS_BASE}/punch",     "color": 0x000000, "solo": False},
    "bite":      {"url": f"{NEKOS_BASE}/bite",      "color": 0x000000, "solo": False},
    "lick":      {"url": f"{NEKOS_BASE}/lick",      "color": 0x000000, "solo": False},
    "wave":      {"url": f"{NEKOS_BASE}/wave",      "color": 0x000000, "solo": True },
    "cry":       {"url": f"{NEKOS_BASE}/cry",       "color": 0x000000, "solo": True },
    "dance":     {"url": f"{NEKOS_BASE}/dance",     "color": 0x000000, "solo": True },
    "blush":     {"url": f"{NEKOS_BASE}/blush",     "color": 0x000000, "solo": True },
    "smile":     {"url": f"{NEKOS_BASE}/smile",     "color": 0x000000, "solo": True },
    "wink":      {"url": f"{NEKOS_BASE}/wink",      "color": 0x000000, "solo": True },
    "highfive":  {"url": f"{NEKOS_BASE}/highfive",  "color": 0x000000, "solo": False},
    "feed":      {"url": f"{NEKOS_BASE}/feed",      "color": 0x000000, "solo": False},
    "stare":     {"url": f"{NEKOS_BASE}/stare",     "color": 0x000000, "solo": False},
    "tickle":    {"url": f"{NEKOS_BASE}/tickle",    "color": 0x000000, "solo": False},
    "handhold":  {"url": f"{NEKOS_BASE}/handhold",  "color": 0x000000, "solo": False},
    "nom":       {"url": f"{NEKOS_BASE}/nom",       "color": 0x000000, "solo": False},
    "yeet":      {"url": f"{NEKOS_BASE}/yeet",      "color": 0x000000, "solo": False},
    "kill":      {"url": f"{NEKOS_BASE}/kill",      "color": 0x000000, "solo": False},
    "throw":     {"url": f"{NEKOS_BASE}/throw",     "color": 0x000000, "solo": False},
}

ACTION_MESSAGES = {
    "hug":      ["{author} gave {target} a warm hug! 🤗", "{author} wrapped {target} in a big hug! 💞", "Aww, {author} is hugging {target}! 🥰"],
    "kiss":     ["{author} kissed {target}! 😘", "{author} planted a sweet kiss on {target}! 💋", "{author} gave {target} a big kiss! 💕"],
    "slap":     ["{author} slapped {target}! 💢", "{author} gave {target} a hard slap! 😤", "{target} got slapped by {author}! 😳"],
    "pat":      ["{author} patted {target}! 🥹", "{author} gently patted {target} on the head! ✨", "Good job {target}, {author} is patting you! 😊"],
    "poke":     ["{author} poked {target}! 👉", "{author} keeps poking {target}...", "{target} got poked by {author}! 😆"],
    "cuddle":   ["{author} is cuddling with {target}! 🥰", "{author} pulled {target} in for cuddles! 💞", "So cute! {author} and {target} are cuddling!"],
    "punch":    ["{author} punched {target}! 💥", "{author} threw a punch at {target}! 😤", "Ouch! {author} punched {target} right in the face! 👊"],
    "bite":     ["{author} bit {target}! 😬", "{author} nibbled on {target}! 🫦", "Ouch! {author} gave {target} a little bite!"],
    "lick":     ["{author} licked {target}! 👅", "{author} gave {target} a big lick! 😛", "Eww, {author} licked {target}! 😅"],
    "wave":     ["{author} waved at {target}! 👋", "{author} is waving at {target}!", "Hey! {author} just waved at {target}!"],
    "cry":      ["{author} is crying... 😢", "{author} burst into tears 😭", "Someone comfort {author}, they're crying! 💔"],
    "dance":    ["{author} is dancing! 💃", "{author} busted some moves! 🕺", "{author} can't stop dancing! 🎶"],
    "blush":    ["{author} is blushing! 😳", "{author} turned bright red! 🌸", "Aww {author} is blushing so hard!"],
    "smile":    ["{author} smiled at {target}! 😊", "{author} flashed a big smile at {target}! ✨", "{author}'s smile just lit up the room 🌟"],
    "wink":     ["{author} winked at {target}! 😉", "{author} gave {target} a cheeky wink!", "Ooh, {author} is winking at {target}! 👀"],
    "highfive": ["{author} high-fived {target}! 🙌", "Yes! {author} and {target} nailed that high five!", "{author} slapped hands with {target}! ✋"],
    "feed":     ["{author} is feeding {target}! 🍴", "{author} made food for {target}! 🥺", "So sweet, {author} is feeding {target}!"],
    "stare":    ["{author} is staring at {target}...", "{author} won't stop staring at {target} 👀", "{target} feels {author}'s intense gaze..."],
    "tickle":   ["{author} is tickling {target}! 😂", "Stop, stop! {author} is tickling {target}!", "{target} can't handle {author}'s tickles! 🤣"],
    "handhold": ["{author} is holding {target}'s hand! 🥹", "{author} grabbed {target}'s hand! 💞", "Aww, {author} and {target} are holding hands!"],
    "nom":      ["{author} nommed on {target}! 😋", "{author} took a little nom of {target}! 👄", "Chomp! {author} is nomming {target}!"],
    "yeet":     ["{author} yeeted {target} into the void! 🌌", "{author} YEETED {target}! 🚀", "{target} got yeeted by {author} to another dimension!"],
    "kill":     ["{author} eliminated {target}! ☠️", "{target} was slain by {author}! ⚔️", "RIP {target}, destroyed by {author}! 💀"],
    "throw":    ["{author} threw {target} across the room! 😂", "{author} yoinked and threw {target}! 💨", "{target} got launched by {author}!"],
}

SOLO_MESSAGES = {
    "wave":   ["{author} is waving! 👋", "Hey everyone, {author} is waving!"],
    "cry":    ["{author} is crying 😢", "{author} burst into tears 😭"],
    "dance":  ["{author} is busting moves! 💃", "{author} started dancing! 🕺"],
    "blush":  ["{author} is blushing! 😳", "{author} turned bright red! 🌸"],
    "smile":  ["{author} is smiling! 😊", "{author} flashed a big smile! ✨"],
    "wink":   ["{author} winked! 😉", "{author} gave a cheeky wink!"],
}

# Path to the ship background (same folder as this file)
_SHIP_BG = Path(__file__).parent / "assets" / "ship_bg.jpg"
# Fallback: look in uploads path too (for dev)
_SHIP_BG_FALLBACK = Path("/mnt/user-data/uploads/1000039805.jpg")


async def fetch_gif(url: str) -> str | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    results = data.get("results", [])
                    if results:
                        return results[0].get("url")
    except Exception:
        pass
    return None


async def fetch_avatar(url: str) -> Image.Image | None:
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        pass
    return None


# ── Card generation ──────────────────────────────────────────────────────────

def _circle_crop(img: Image.Image, size: int) -> Image.Image:
    img = img.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    img.putalpha(mask)
    return img


def _draw_heart(canvas: Image.Image, cx: int, cy: int, size: int, color: tuple, alpha: int = 255):
    heart = Image.new("RGBA", (size * 2, size * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(heart)
    s = size
    d.ellipse([0, 0, s, s],      fill=(*color, alpha))
    d.ellipse([s, 0, s * 2, s],  fill=(*color, alpha))
    d.polygon([(0, s // 2), (s * 2, s // 2), (s, s * 2)], fill=(*color, alpha))
    heart = heart.rotate(-45, expand=True)
    hx = cx - heart.width // 2
    hy = cy - heart.height // 2
    canvas.paste(heart, (hx, hy), heart)


def _get_font(size: int, bold: bool = False):
    candidates = [
        f"/usr/share/fonts/truetype/dejavu/DejaVuSans{'-Bold' if bold else ''}.ttf",
        f"/usr/share/fonts/truetype/liberation/LiberationSans{'-Bold' if bold else '-Regular'}.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def build_ship_card(
    av1: Image.Image | None,
    av2: Image.Image | None,
    name1: str,
    name2: str,
    score: int,
) -> io.BytesIO:
    W, H = 900, 280

    # ── Background ──
    bg_path = _SHIP_BG if _SHIP_BG.exists() else _SHIP_BG_FALLBACK
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA").resize((W, H), Image.LANCZOS)
    else:
        bg = Image.new("RGBA", (W, H), (30, 10, 20, 255))

    # Darken bg slightly
    bg = Image.alpha_composite(bg, Image.new("RGBA", (W, H), (0, 0, 0, 70)))

    # ── Dark center strip ──
    strip_h = 165
    strip_y = (H - strip_h) // 2
    strip = Image.new("RGBA", (W, strip_h), (8, 8, 28, 215))
    bg.paste(strip, (0, strip_y), strip)

    # ── Decorative scattered hearts ──
    deco_hearts = [
        (55,  28, 22, (255, 70, 70),  175),
        (825, 35, 18, (255, 140, 140),145),
        (125, 228, 16, (255, 90, 90), 155),
        (765, 235, 20, (255, 70, 70), 165),
        (400, 12, 13, (255, 110, 110),135),
        (505, 255, 11, (255, 140, 140),125),
        (25, 135, 9,  (255, 90, 90),  115),
        (868, 145, 11,(255, 70, 70),  135),
        (660, 18, 10, (255, 120, 120),120),
        (230, 12, 9,  (255, 100, 100),110),
    ]
    for hx, hy, hs, hc, ha in deco_hearts:
        _draw_heart(bg, hx, hy, hs, hc, ha)

    # ── Avatars ──
    av_size = 130
    cx1, cy1 = 190, H // 2
    cx2, cy2 = W - 190, H // 2

    placeholder1 = Image.new("RGBA", (av_size, av_size), (100, 100, 180, 255))
    placeholder2 = Image.new("RGBA", (av_size, av_size), (180, 100, 100, 255))
    img1 = _circle_crop(av1 if av1 else placeholder1, av_size)
    img2 = _circle_crop(av2 if av2 else placeholder2, av_size)

    # Red rings
    ring_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    rd = ImageDraw.Draw(ring_layer)
    r = av_size // 2 + 6
    rd.ellipse([cx1-r, cy1-r, cx1+r, cy1+r], outline=(215, 25, 25), width=6)
    rd.ellipse([cx2-r, cy2-r, cx2+r, cy2+r], outline=(215, 25, 25), width=6)
    bg = Image.alpha_composite(bg, ring_layer)

    bg.paste(img1, (cx1 - av_size // 2, cy1 - av_size // 2), img1)
    bg.paste(img2, (cx2 - av_size // 2, cy2 - av_size // 2), img2)

    # ── Center heart ──
    _draw_heart(bg, W // 2, H // 2, 58, (200, 25, 25), 255)
    # Lighter inner highlight
    _draw_heart(bg, W // 2 - 6, H // 2 - 10, 20, (255, 120, 120), 160)

    # ── Text ──
    draw = ImageDraw.Draw(bg)
    font_pct   = _get_font(30, bold=True)
    font_name  = _get_font(21, bold=True)
    font_ship  = _get_font(17, bold=False)

    # Percentage in heart
    pct_text = f"{score}%"
    bb = draw.textbbox((0, 0), pct_text, font=font_pct)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    draw.text((W // 2 - tw // 2, H // 2 - th // 2 + 2), pct_text, font=font_pct, fill=(255, 255, 255))

    # Names under avatars
    def draw_centered(text, cx, y, font, color=(255, 255, 255)):
        bb = draw.textbbox((0, 0), text, font=font)
        w = bb[2] - bb[0]
        draw.text((cx - w // 2, y), text, font=font, fill=color)

    draw_centered(name1, cx1, cy1 + av_size // 2 + 10, font_name)
    draw_centered(name2, cx2, cy2 + av_size // 2 + 10, font_name)

    # Ship name / couple line above strip
    ship_name = name1[:max(1, len(name1) // 2)] + name2[len(name2) // 2:]
    couple_text = f"{name1} + {name2}"
    draw_centered(couple_text, W // 2, strip_y - 28, font_ship, color=(255, 200, 200))

    # Save
    buf = io.BytesIO()
    bg.convert("RGB").save(buf, format="JPEG", quality=95)
    buf.seek(0)
    return buf


# ── Cog ──────────────────────────────────────────────────────────────────────

class Roleplay(commands.Cog):
    """🎭 Fun & roleplay commands."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _send_action(self, ctx: commands.Context, action: str, target: discord.Member = None):
        cfg = ROLEPLAY_ACTIONS[action]
        is_solo = cfg["solo"]

        if target and not is_solo:
            msg = random.choice(ACTION_MESSAGES.get(action, [f"{ctx.author.mention} → {target.mention}"]))
            msg = msg.format(author=ctx.author.mention, target=target.mention)
        elif action in SOLO_MESSAGES:
            msg = random.choice(SOLO_MESSAGES[action])
            msg = msg.format(author=ctx.author.mention)
        else:
            msg = random.choice(ACTION_MESSAGES.get(action, [f"{ctx.author.mention} used {action}!"]))
            msg = msg.format(author=ctx.author.mention, target=target.mention if target else "someone")

        gif_url = await fetch_gif(cfg["url"])
        embed = discord.Embed(description=msg, color=cfg["color"])
        if gif_url:
            embed.set_image(url=gif_url)
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    # ── Roleplay commands ─────────────────────────────────────────────────────

    @commands.command(name="hug")
    async def hug(self, ctx, member: discord.Member):
        await self._send_action(ctx, "hug", member)

    @commands.command(name="kiss")
    async def kiss(self, ctx, member: discord.Member):
        await self._send_action(ctx, "kiss", member)

    @commands.command(name="slap")
    async def slap(self, ctx, member: discord.Member):
        await self._send_action(ctx, "slap", member)

    @commands.command(name="pat")
    async def pat(self, ctx, member: discord.Member):
        await self._send_action(ctx, "pat", member)

    @commands.command(name="poke")
    async def poke(self, ctx, member: discord.Member):
        await self._send_action(ctx, "poke", member)

    @commands.command(name="cuddle")
    async def cuddle(self, ctx, member: discord.Member):
        await self._send_action(ctx, "cuddle", member)

    @commands.command(name="punch")
    async def punch(self, ctx, member: discord.Member):
        await self._send_action(ctx, "punch", member)

    @commands.command(name="bite")
    async def bite(self, ctx, member: discord.Member):
        await self._send_action(ctx, "bite", member)

    @commands.command(name="lick")
    async def lick(self, ctx, member: discord.Member):
        await self._send_action(ctx, "lick", member)

    @commands.command(name="highfive")
    async def highfive(self, ctx, member: discord.Member):
        await self._send_action(ctx, "highfive", member)

    @commands.command(name="feed")
    async def feed(self, ctx, member: discord.Member):
        await self._send_action(ctx, "feed", member)

    @commands.command(name="stare")
    async def stare(self, ctx, member: discord.Member):
        await self._send_action(ctx, "stare", member)

    @commands.command(name="tickle")
    async def tickle(self, ctx, member: discord.Member):
        await self._send_action(ctx, "tickle", member)

    @commands.command(name="handhold")
    async def handhold(self, ctx, member: discord.Member):
        await self._send_action(ctx, "handhold", member)

    @commands.command(name="nom")
    async def nom(self, ctx, member: discord.Member):
        await self._send_action(ctx, "nom", member)

    @commands.command(name="yeet")
    async def yeet(self, ctx, member: discord.Member):
        await self._send_action(ctx, "yeet", member)

    @commands.command(name="kill")
    async def kill(self, ctx, member: discord.Member):
        await self._send_action(ctx, "kill", member)

    @commands.command(name="throw")
    async def throw(self, ctx, member: discord.Member):
        await self._send_action(ctx, "throw", member)

    @commands.command(name="smile")
    async def smile(self, ctx, member: discord.Member = None):
        await self._send_action(ctx, "smile", member)

    @commands.command(name="wink")
    async def wink(self, ctx, member: discord.Member = None):
        await self._send_action(ctx, "wink", member)

    @commands.command(name="wave")
    async def wave(self, ctx, member: discord.Member = None):
        await self._send_action(ctx, "wave", member)

    @commands.command(name="cry")
    async def cry(self, ctx):
        await self._send_action(ctx, "cry")

    @commands.command(name="dance")
    async def dance(self, ctx):
        await self._send_action(ctx, "dance")

    @commands.command(name="blush")
    async def blush(self, ctx):
        await self._send_action(ctx, "blush")

    # ── Ship command ──────────────────────────────────────────────────────────

    @commands.command(name="ship")
    async def ship(self, ctx, member: discord.Member = None):
        """💘 Ship yourself with someone, or mention one user to ship with them.
        Usage:
          ;ship          → ships you with a random server member
          ;ship @user    → ships you with that user
        """
        # Pick targets
        member1 = ctx.author

        if member is None:
            # Random member — exclude bots and the author
            candidates = [m for m in ctx.guild.members if not m.bot and m.id != ctx.author.id]
            if not candidates:
                return await ctx.send("💔 There's nobody else here to ship you with!")
            member2 = random.choice(candidates)
        else:
            member2 = member

        # Deterministic score
        score = (member1.id + member2.id) % 101

        # Fetch avatars concurrently
        async with ctx.typing():
            av1_img = await fetch_avatar(str(member1.display_avatar.replace(format="png", size=256).url))
            av2_img = await fetch_avatar(str(member2.display_avatar.replace(format="png", size=256).url))

            buf = build_ship_card(
                av1_img, av2_img,
                member1.display_name, member2.display_name,
                score
            )

        # Status label
        if score < 20:   status = "No chance... 💔"
        elif score < 40: status = "It's complicated ❤️‍🩹"
        elif score < 60: status = "There's potential! 💛"
        elif score < 80: status = "Looking good! 🧡"
        elif score < 95: status = "A great match! ❤️"
        else:            status = "PERFECT MATCH! 💞🎉"

        ship_name = member1.display_name[:max(1, len(member1.display_name)//2)] + member2.display_name[len(member2.display_name)//2:]

        file = discord.File(buf, filename="ship.jpg")
        embed = discord.Embed(
            description=(
                f"❤️ **Relationship Percentage** ❤️\n\n"
                f"**{member1.display_name} + {member2.display_name}**\n"
                f"-# Ship name: **{ship_name}** • {status}"
            ),
            color=0xff4466
        )
        embed.set_image(url="attachment://ship.jpg")
        embed.set_footer(text=f"Requested by {ctx.author.display_name}", icon_url=ctx.author.display_avatar.url)
        await ctx.send(file=file, embed=embed)

    # ── Error handlers ────────────────────────────────────────────────────────

    @hug.error
    @kiss.error
    @slap.error
    @pat.error
    @poke.error
    @cuddle.error
    @punch.error
    @bite.error
    @lick.error
    @highfive.error
    @feed.error
    @stare.error
    @tickle.error
    @handhold.error
    @nom.error
    @yeet.error
    @kill.error
    @throw.error
    async def roleplay_error(self, ctx, error):
        if isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=discord.Embed(
                description="❌ Member not found. Please mention a valid server member.",
                color=0xe63946
            ), delete_after=5)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(embed=discord.Embed(
                description=f"❌ Please mention someone!\nUsage: `{ctx.prefix}{ctx.command.name} @user`",
                color=0xe63946
            ), delete_after=5)


async def setup(bot: commands.Bot):
    await bot.add_cog(Roleplay(bot))
