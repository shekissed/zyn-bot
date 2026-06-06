"""
card_generator.py — Profile card matching Blame bot aesthetic exactly.

Layout (900x340):
  • Full-bleed avatar/background, blurred + darkened
  • Left-to-right dark gradient (text side readable, right side shows bg)  
  • Circular avatar, left side, NO coloured ring — just a thin white ring
  • Status dot bottom-right of avatar circle (grey=offline, yellow-moon=idle, green=online, red=dnd)
  • Display name large bold, username smaller — vertically centred
  • Clan tag pill top-right corner (💗 tag)
  • Date pill bottom-right corner
  • NO purple accents, NO glow rings, NO accent lines
"""

from PIL import Image, ImageDraw, ImageFont, ImageFilter
import io, os

# ── Font resolution ────────────────────────────────────────────────────────

def _find_font(candidates):
    for p in candidates:
        if p and os.path.isfile(p):
            return p
    return None

def _load(candidates, size):
    path = _find_font(candidates)
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)

_BOLD = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Bold.ttf",
    os.path.join(os.path.dirname(__file__), "fonts", "Poppins-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
_MEDIUM = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Medium.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Medium.ttf",
    os.path.join(os.path.dirname(__file__), "fonts", "Poppins-Medium.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_LIGHT = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Light.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Light.ttf",
    os.path.join(os.path.dirname(__file__), "fonts", "Poppins-Light.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_REG = [
    "/usr/share/fonts/truetype/google-fonts/Poppins-Regular.ttf",
    "/usr/share/fonts/google-fonts/Poppins-Regular.ttf",
    os.path.join(os.path.dirname(__file__), "fonts", "Poppins-Regular.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]

CARD_W, CARD_H = 900, 340
CORNER_R = 22

# status key → (RGB colour, is_circle — False means draw moon)
STATUS = {
    "online":    ((59, 165, 93),   True),
    "idle":      ((250, 168, 0),   False),
    "dnd":       ((237, 66, 69),   True),
    "offline":   ((116, 127, 141), True),
    "invisible": ((116, 127, 141), True),
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _round_corners(im, r):
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, *im.size], radius=r, fill=255)
    out = im.convert("RGBA")
    out.putalpha(mask)
    return out


def _circle_crop(im, size):
    im = im.resize((size, size), Image.LANCZOS).convert("RGBA")
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size, size], fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(im, mask=mask)
    return out


def _fit_crop(im, w, h):
    r = im.width / im.height
    if r > w / h:
        nw, nh = int(r * h), h
    else:
        nw, nh = w, int(w / r)
    im = im.resize((nw, nh), Image.LANCZOS)
    x, y = (nw - w) // 2, (nh - h) // 2
    return im.crop((x, y, x + w, y + h))


def _shadow(draw, xy, text, font, fill=(255,255,255,255), shadow=(0,0,0,160), offset=2):
    draw.text((xy[0]+offset, xy[1]+offset), text, font=font, fill=shadow)
    draw.text(xy, text, font=font, fill=fill)


def _horiz_grad(w, h, left_rgba, right_rgba):
    """Pixel-perfect left→right RGBA gradient."""
    img = Image.new("RGBA", (w, h))
    px = img.load()
    lr, lg, lb, la = left_rgba
    rr, rg, rb, ra = right_rgba
    for x in range(w):
        t = x / max(w - 1, 1)
        col = (
            int(lr + (rr-lr)*t),
            int(lg + (rg-lg)*t),
            int(lb + (rb-lb)*t),
            int(la + (ra-la)*t),
        )
        for y in range(h):
            px[x, y] = col
    return img


def _draw_crescent(draw, cx, cy, r, color, bg):
    """Yellow crescent moon (idle status)."""
    draw.ellipse([cx-r, cy-r, cx+r, cy+r], fill=(*color, 255))
    # carve-out circle offset up+right to form crescent
    bite = int(r * 0.72)
    ox = int(r * 0.5)
    oy = int(-r * 0.4)
    draw.ellipse([cx-bite+ox, cy-bite+oy, cx+bite+ox, cy+bite+oy], fill=(*bg, 255))


# ── Main ───────────────────────────────────────────────────────────────────

def make_profile_card(
    avatar_bytes: bytes,
    display_name: str,
    username: str,
    clan_tag: str = None,
    status: str = "offline",
    joined_date: str = "May 14, 2026",
    background_bytes: bytes = None,
) -> bytes:

    # ── 1. Background: avatar (or custom bg) blurred and darkened ──────────
    bg_src = Image.open(io.BytesIO(background_bytes or avatar_bytes)).convert("RGBA")
    bg = _fit_crop(bg_src, CARD_W, CARD_H)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=24))

    # Uniform dark overlay so background isn't too vivid
    overlay = Image.new("RGBA", bg.size, (15, 12, 30, 140))
    card = Image.alpha_composite(bg, overlay)

    # Left-heavy gradient: left side nearly opaque dark, right side transparent
    # This makes text readable while right side shows blurred bg
    grad = _horiz_grad(CARD_W, CARD_H,
                       (15, 12, 30, 200),   # left — dark indigo, mostly opaque
                       (15, 12, 30,  0))    # right — fully transparent
    card = Image.alpha_composite(card, grad)

    draw = ImageDraw.Draw(card)

    # ── 2. Circular avatar — NO coloured ring, just thin white border ──────
    AV = 200
    av_x = 38
    av_y = (CARD_H - AV) // 2   # vertically centred

    # Thin white ring (2px, low opacity) — matches reference exactly
    ring_size = AV + 4
    ring_img = Image.new("RGBA", (ring_size, ring_size), (0, 0, 0, 0))
    ImageDraw.Draw(ring_img).ellipse(
        [0, 0, ring_size, ring_size],
        outline=(255, 255, 255, 60), width=2
    )
    card.paste(ring_img, (av_x - 2, av_y - 2), ring_img)

    av_img = _circle_crop(Image.open(io.BytesIO(avatar_bytes)), AV)
    card.paste(av_img, (av_x, av_y), av_img)

    # ── 3. Status indicator — bottom-right of avatar ───────────────────────
    s_key = status if status in STATUS else "offline"
    s_color, is_circle = STATUS[s_key]
    DOT_R = 14
    dot_cx = av_x + AV - DOT_R - 4
    dot_cy = av_y + AV - DOT_R - 4
    bg_col  = (15, 12, 30)

    # Dark backing so dot is visible against any avatar colour
    draw.ellipse(
        [dot_cx - DOT_R - 4, dot_cy - DOT_R - 4,
         dot_cx + DOT_R + 4, dot_cy + DOT_R + 4],
        fill=(*bg_col, 255)
    )

    if is_circle:
        draw.ellipse(
            [dot_cx - DOT_R, dot_cy - DOT_R,
             dot_cx + DOT_R, dot_cy + DOT_R],
            fill=(*s_color, 255)
        )
    else:
        _draw_crescent(draw, dot_cx, dot_cy, DOT_R, s_color, bg_col)

    # ── 4. Text — display name + username, vertically centred ──────────────
    text_x = av_x + AV + 40

    fn_name = _load(_BOLD, 72)
    fn_user = _load(_LIGHT, 30)

    nb = fn_name.getbbox(display_name)
    name_h = nb[3] - nb[1]

    ub = fn_user.getbbox(f"@{username}" if not username.startswith("@") else username)
    user_h = ub[3] - ub[1]

    gap = 6
    total_h = name_h + gap + user_h
    name_y = (CARD_H - total_h) // 2
    user_y = name_y + name_h + gap

    handle = username if username.startswith("@") else f"@{username}"

    _shadow(draw, (text_x, name_y), display_name, fn_name,
            fill=(255, 255, 255, 255), shadow=(0, 0, 0, 180), offset=2)
    _shadow(draw, (text_x, user_y), handle, fn_user,
            fill=(210, 205, 235, 230), shadow=(0, 0, 0, 150), offset=2)

    # ── 5. Clan tag pill — top right ───────────────────────────────────────
    if clan_tag:
        tf = _load(_MEDIUM, 21)
        tag_text = f"💗  {clan_tag}"
        tb = tf.getbbox(tag_text)
        tw = (tb[2] - tb[0]) + 28
        th = (tb[3] - tb[1]) + 12
        px = CARD_W - tw - 16
        py = 16
        draw.rounded_rectangle(
            [px, py, px + tw, py + th],
            radius=th // 2,
            fill=(30, 20, 45, 220)
        )
        draw.text((px + 14, py + 6), tag_text, font=tf, fill=(255, 165, 205, 255))

    # ── 6. Date pill — bottom right ────────────────────────────────────────
    df = _load(_REG, 18)
    dbox = df.getbbox(joined_date)
    dw = dbox[2] - dbox[0]
    dx = CARD_W - dw - 22
    dy = CARD_H - 34
    draw.rounded_rectangle(
        [dx - 10, dy - 4, dx + dw + 10, dy + 20],
        radius=8, fill=(0, 0, 0, 170)
    )
    draw.text((dx, dy), joined_date, font=df, fill=(200, 198, 230, 230))

    # ── 7. Round corners (NO accent lines, NO purple border) ───────────────
    card = _round_corners(card, CORNER_R)

    out = io.BytesIO()
    card.save(out, format="PNG", optimize=True)
    return out.getvalue()
