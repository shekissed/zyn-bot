"""
Container Builder Cog
"""

import asyncio
import io
import discord
from discord import ui
from discord.ext import commands

# ── Color palette ─────────────────────────────────────────────────────────────

_COLORS: dict[str, discord.Colour | None] = {
    "none":      None,
    "blurple":   discord.Colour.blurple(),
    "red":       discord.Colour.red(),
    "green":     discord.Colour.green(),
    "blue":      discord.Colour.blue(),
    "orange":    discord.Colour.orange(),
    "dark_grey": discord.Colour.dark_grey(),
    "white":     discord.Colour(0xFFFFFF),
}

_COLOR_NAMES: dict[str, str] = {
    "none":      "None",
    "blurple":   "Blurple",
    "red":       "Red",
    "green":     "Green",
    "blue":      "Blue",
    "orange":    "Orange",
    "dark_grey": "Dark Grey",
    "white":     "White",
}

MAX_COMPONENTS = 20


# ── Helpers ───────────────────────────────────────────────────────────────────

def _media(url: str) -> discord.UnfurledMediaItem:
    """Wrap a URL string into the UnfurledMediaItem discord.py expects."""
    return discord.UnfurledMediaItem(url=url)


def _comp_label(comp: dict, i: int) -> str:
    t = comp["type"]
    if t == "text":
        p = comp["content"][:45].replace("\n", " ")
        return f"{i + 1}. Text — {p}"
    if t == "separator":
        kind = "line" if comp.get("divider", True) else "spacer"
        return f"{i + 1}. Separator ({comp.get('spacing', 'small')}, {kind})"
    if t == "section":
        p = comp["content"][:40].replace("\n", " ")
        return f"{i + 1}. Section — {p}"
    if t == "media_gallery":
        n = len(comp["urls"])
        return f"{i + 1}. Gallery ({n} image{'s' if n != 1 else ''})"
    if t == "button_row":
        labels = ", ".join(b["label"] for b in comp["buttons"][:3])
        suffix = "..." if len(comp["buttons"]) > 3 else ""
        return f"{i + 1}. Buttons — {labels}{suffix}"
    return f"{i + 1}. Unknown"


def _render_into(container: ui.Container, comp: dict) -> None:
    t = comp["type"]
    if t == "text":
        container.add_item(ui.TextDisplay(comp["content"]))

    elif t == "separator":
        sp = (
            discord.SeparatorSpacing.large
            if comp.get("spacing") == "large"
            else discord.SeparatorSpacing.small
        )
        container.add_item(ui.Separator(visible=comp.get("divider", True), spacing=sp))

    elif t == "section":
        url = comp.get("thumbnail_url")
        if url:
            # FIX: must wrap URL in UnfurledMediaItem, not pass raw string
            section = ui.Section(accessory=ui.Thumbnail(media=_media(url)))
            section.add_item(ui.TextDisplay(comp["content"]))
            container.add_item(section)
        else:
            container.add_item(ui.TextDisplay(comp["content"]))

    elif t == "media_gallery":
        if comp["urls"]:
            gallery = ui.MediaGallery()
            for u in comp["urls"]:
                # FIX: must wrap URL in UnfurledMediaItem
                gallery.add_item(media=_media(u))
            container.add_item(gallery)

    elif t == "button_row":
        if comp["buttons"]:
            row = ui.ActionRow(*[
                ui.Button(label=b["label"], style=discord.ButtonStyle.link, url=b["url"])
                for b in comp["buttons"][:5]
            ])
            container.add_item(row)


# ── Upload-aware image helper ─────────────────────────────────────────────────

async def _await_upload(
    interaction: discord.Interaction,
    prompt: str,
    timeout: float = 60.0,
) -> str | None:
    """
    Send an ephemeral follow-up asking the user to upload an image (or paste a
    URL).  Returns the resolved URL string, or None on timeout/cancel.

    Works by watching for the next message the same user sends in the same
    channel that contains either an attachment or plain text URL.
    """
    await interaction.followup.send(
        f"{prompt}\n\n"
        "Upload an image file **or** paste a direct image URL.\n"
        "Type `cancel` to skip.",
        ephemeral=True,
    )

    def check(m: discord.Message) -> bool:
        return (
            m.author.id == interaction.user.id
            and m.channel.id == interaction.channel.id
        )

    try:
        msg: discord.Message = await interaction.client.wait_for(
            "message", check=check, timeout=timeout
        )
    except asyncio.TimeoutError:
        await interaction.followup.send("⏱ Timed out waiting for an image.", ephemeral=True)
        return None

    # Try to delete the user's upload message so the channel stays clean
    try:
        await msg.delete()
    except Exception:
        pass

    if msg.content.strip().lower() == "cancel":
        return None

    # Prefer attachment over text
    if msg.attachments:
        return msg.attachments[0].url

    text = msg.content.strip()
    if text.startswith("http://") or text.startswith("https://"):
        return text

    await interaction.followup.send(
        "❌ That didn't look like a valid URL or image attachment. Skipping.",
        ephemeral=True,
    )
    return None


# ── Modals ────────────────────────────────────────────────────────────────────

class _TextModal(ui.Modal):
    def __init__(self, view: "BuilderView", index: int | None = None):
        super().__init__(title="Edit Text Display" if index is not None else "Add Text Display")
        self._v = view
        self._i = index
        self._field = ui.TextInput(
            label="Content",
            style=discord.TextStyle.paragraph,
            placeholder="Supports full markdown: **bold**, ### heading, > blockquote...",
            required=True,
            max_length=2000,
            default=view._data[index]["content"] if index is not None else None,
        )
        self.add_item(self._field)

    async def on_submit(self, interaction: discord.Interaction):
        d = {"type": "text", "content": self._field.value}
        if self._i is None:
            self._v._data.append(d)
        else:
            self._v._data[self._i] = d
        self._v._mode = "normal"
        self._v._rebuild()
        await interaction.response.edit_message(view=self._v)


class _SeparatorModal(ui.Modal):
    def __init__(self, view: "BuilderView", index: int | None = None):
        super().__init__(title="Edit Separator" if index is not None else "Add Separator")
        self._v = view
        self._i = index
        existing = view._data[index] if index is not None else {}
        self._divider = ui.TextInput(
            label="Show divider line? (yes / no)",
            default="yes" if existing.get("divider", True) else "no",
            max_length=3,
            required=True,
        )
        self._spacing = ui.TextInput(
            label="Spacing (small / large)",
            default=existing.get("spacing", "small"),
            max_length=5,
            required=True,
        )
        self.add_item(self._divider)
        self.add_item(self._spacing)

    async def on_submit(self, interaction: discord.Interaction):
        divider = self._divider.value.strip().lower() not in ("no", "n", "false", "0")
        spacing = "large" if self._spacing.value.strip().lower() == "large" else "small"
        d = {"type": "separator", "divider": divider, "spacing": spacing}
        if self._i is None:
            self._v._data.append(d)
        else:
            self._v._data[self._i] = d
        self._v._mode = "normal"
        self._v._rebuild()
        await interaction.response.edit_message(view=self._v)


class _SectionModal(ui.Modal):
    """
    Section & Thumbnail.
    The thumbnail URL field accepts a direct URL or the literal text "upload"
    to trigger the file-upload flow after the modal submits.
    """

    def __init__(self, view: "BuilderView", index: int | None = None):
        super().__init__(title="Edit Section" if index is not None else "Add Section & Thumbnail")
        self._v = view
        self._i = index
        existing = view._data[index] if index is not None else {}
        self._text = ui.TextInput(
            label="Text Content",
            style=discord.TextStyle.paragraph,
            required=True,
            max_length=1000,
            default=existing.get("content"),
        )
        self._url = ui.TextInput(
            label='Thumbnail URL  (or type "upload" to attach a file)',
            style=discord.TextStyle.short,
            required=False,
            placeholder='https://example.com/image.png  OR  "upload"',
            max_length=500,
            default=existing.get("thumbnail_url"),
        )
        self.add_item(self._text)
        self.add_item(self._url)

    async def on_submit(self, interaction: discord.Interaction):
        raw_url = self._url.value.strip()
        wants_upload = raw_url.lower() == "upload"

        if wants_upload:
            await interaction.response.defer()
            resolved = await _await_upload(
                interaction,
                "<:partners:1511944546496544819> **Upload your thumbnail image for the Section:**",
            )
            url = resolved
        else:
            url = raw_url or None
            await interaction.response.defer()

        d = {"type": "section", "content": self._text.value, "thumbnail_url": url}
        if self._i is None:
            self._v._data.append(d)
        else:
            self._v._data[self._i] = d
        self._v._mode = "normal"
        self._v._rebuild()
        await interaction.followup.edit_message(
            message_id=self._v.message_id, view=self._v
        )


class _GalleryModal(ui.Modal):
    """
    Media Gallery.
    Users can paste URLs one per line, or type "upload" (alone or mixed with
    URLs) to attach files via the follow-up upload flow.
    """

    def __init__(self, view: "BuilderView", index: int | None = None):
        super().__init__(title="Edit Media Gallery" if index is not None else "Add Media Gallery")
        self._v = view
        self._i = index
        existing = view._data[index] if index is not None else {}
        self._urls = ui.TextInput(
            label='Image URLs — one per line, max 10  (or "upload")',
            style=discord.TextStyle.paragraph,
            required=True,
            placeholder='https://example.com/img1.png\nhttps://example.com/img2.png\n\nOr type "upload" to attach files',
            max_length=4000,
            default="\n".join(existing.get("urls", [])) or None,
        )
        self.add_item(self._urls)

    async def on_submit(self, interaction: discord.Interaction):
        lines = [ln.strip() for ln in self._urls.value.splitlines() if ln.strip()]

        # Separate real URLs from "upload" tokens
        real_urls = [ln for ln in lines if ln.lower() != "upload"]
        upload_slots = sum(1 for ln in lines if ln.lower() == "upload")

        await interaction.response.defer()

        # Resolve each upload slot (up to 10 total)
        for _ in range(min(upload_slots, 10 - len(real_urls))):
            resolved = await _await_upload(
                interaction,
                f"📎 **Upload image {len(real_urls) + 1} for the Media Gallery:**",
            )
            if resolved:
                real_urls.append(resolved)

        if not real_urls:
            await interaction.followup.send(
                "<:wickk:1506950253545394257> No valid images were provided. Gallery not added.",
                ephemeral=True,
            )
            return

        d = {"type": "media_gallery", "urls": real_urls[:10]}
        if self._i is None:
            self._v._data.append(d)
        else:
            self._v._data[self._i] = d
        self._v._mode = "normal"
        self._v._rebuild()
        await interaction.followup.edit_message(
            message_id=self._v.message_id, view=self._v
        )


class _ButtonRowModal(ui.Modal):
    def __init__(self, view: "BuilderView", index: int | None = None):
        super().__init__(title="Edit Button Row" if index is not None else "Add Button Row")
        self._v = view
        self._i = index
        existing = view._data[index] if index is not None else {}
        existing_text = "\n".join(
            f"{b['label']} :: {b['url']}" for b in existing.get("buttons", [])
        )
        self._input = ui.TextInput(
            label="Buttons — one per line: Label :: https://url",
            style=discord.TextStyle.paragraph,
            required=True,
            placeholder="Discord :: https://discord.com\nGitHub :: https://github.com",
            max_length=1000,
            default=existing_text or None,
        )
        self.add_item(self._input)

    async def on_submit(self, interaction: discord.Interaction):
        buttons = []
        for line in self._input.value.splitlines():
            if "::" not in line:
                continue
            label_part, _, url_part = line.partition("::")
            label = label_part.strip()[:80]
            url = url_part.strip()
            if label and (url.startswith("http://") or url.startswith("https://")):
                buttons.append({"label": label, "url": url})

        if not buttons:
            # FIX: must still respond to the modal interaction — use defer then followup
            await interaction.response.defer()
            await interaction.followup.send(
                "<:wickk:1506950253545394257> No valid buttons found. Use the format: `Label :: https://url.com`",
                ephemeral=True,
            )
            return

        d = {"type": "button_row", "buttons": buttons[:5]}
        if self._i is None:
            self._v._data.append(d)
        else:
            self._v._data[self._i] = d
        self._v._mode = "normal"
        self._v._rebuild()
        await interaction.response.edit_message(view=self._v)


# ── Builder View ──────────────────────────────────────────────────────────────

class BuilderView(ui.LayoutView):
    def __init__(self, author_id: int):
        super().__init__(timeout=600)
        self.author_id = author_id
        self.message_id: int | None = None   # set after ctx.send() returns
        self._color_key = "none"
        self._data: list[dict] = []
        self._mode = "normal"
        self._reorder_index: int | None = None
        self._rebuild()

    # ── state helpers ──

    def _color(self) -> discord.Colour | None:
        return _COLORS[self._color_key]

    def _color_name(self) -> str:
        return _COLOR_NAMES[self._color_key]

    def _comp_options(self) -> list[discord.SelectOption]:
        return [
            discord.SelectOption(
                label=_comp_label(c, i)[:100],
                value=str(i),
                default=(i == self._reorder_index and self._mode == "reorder"),
            )
            for i, c in enumerate(self._data)
        ]

    # ── preview ──

    def _build_preview(self) -> ui.Container:
        c = ui.Container(accent_color=self._color())
        if not self._data:
            c.add_item(ui.TextDisplay(
                "-# Your container is empty. Use the controls below to add components."
            ))
        else:
            for comp in self._data:
                _render_into(c, comp)
        return c

    # ── control panels ──

    def _ctrl_normal(self) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Container Builder**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(
            f"-# Color: **{self._color_name()}**"
            f"  |  Components: **{len(self._data)} / {MAX_COMPONENTS}**"
        ))
        c.add_item(ui.Separator(visible=False))

        at_max = len(self._data) >= MAX_COMPONENTS
        add_opts = [
            discord.SelectOption(label="Text Display",        value="text",          description="A block of markdown text"),
            discord.SelectOption(label="Separator",           value="separator",     description="A divider line or invisible spacer"),
            discord.SelectOption(label="Section & Thumbnail", value="section",       description='Text + thumbnail. Type "upload" to attach'),
            discord.SelectOption(label="Media Gallery",       value="media_gallery", description='Images in a grid. Type "upload" to attach'),
            discord.SelectOption(label="Button Row",          value="button_row",    description="Up to 5 redirect (link) buttons in a row"),
        ]
        add_row = ui.ActionRow(ui.Select(
            placeholder="Add a component..." if not at_max else f"Maximum {MAX_COMPONENTS} components reached",
            custom_id="ctrl_add",
            options=add_opts,
            disabled=at_max,
        ))
        add_row.children[0].callback = self._cb_add
        c.add_item(add_row)

        has = bool(self._data)
        can_reorder = len(self._data) >= 2
        btn_row = ui.ActionRow(
            ui.Button(label="Edit",    style=discord.ButtonStyle.secondary, custom_id="ctrl_edit",    disabled=not has),
            ui.Button(label="Remove",  style=discord.ButtonStyle.danger,    custom_id="ctrl_remove",  disabled=not has),
            ui.Button(label="Color",   style=discord.ButtonStyle.secondary, custom_id="ctrl_color"),
            ui.Button(label="Reorder", style=discord.ButtonStyle.secondary, custom_id="ctrl_reorder", disabled=not can_reorder),
            ui.Button(label="Send",    style=discord.ButtonStyle.primary,   custom_id="ctrl_send"),
        )
        btn_row.children[0].callback = self._cb_edit_btn
        btn_row.children[1].callback = self._cb_remove_btn
        btn_row.children[2].callback = self._cb_color_btn
        btn_row.children[3].callback = self._cb_reorder_btn
        btn_row.children[4].callback = self._cb_send_btn
        c.add_item(btn_row)
        return c

    def _ctrl_color(self) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Select Accent Color**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(
            "-# Choose the color bar shown on the left side of the container."
        ))
        c.add_item(ui.Separator(visible=False))

        opts = [
            discord.SelectOption(label=name, value=key, default=(key == self._color_key))
            for key, name in _COLOR_NAMES.items()
        ]
        sel_row = ui.ActionRow(ui.Select(
            placeholder="Choose a color...",
            custom_id="ctrl_color_sel",
            options=opts,
        ))
        sel_row.children[0].callback = self._cb_color_sel
        c.add_item(sel_row)

        cancel_row = ui.ActionRow(
            ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ctrl_cancel")
        )
        cancel_row.children[0].callback = self._cb_cancel
        c.add_item(cancel_row)
        return c

    def _ctrl_edit(self) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Edit a Component**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay("-# Select the component you want to edit."))
        c.add_item(ui.Separator(visible=False))

        sel_row = ui.ActionRow(ui.Select(
            placeholder="Select a component to edit...",
            custom_id="ctrl_edit_sel",
            options=self._comp_options(),
        ))
        sel_row.children[0].callback = self._cb_edit_sel
        c.add_item(sel_row)

        cancel_row = ui.ActionRow(
            ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ctrl_cancel")
        )
        cancel_row.children[0].callback = self._cb_cancel
        c.add_item(cancel_row)
        return c

    def _ctrl_remove(self) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Remove a Component**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay("-# Select the component you want to remove."))
        c.add_item(ui.Separator(visible=False))

        sel_row = ui.ActionRow(ui.Select(
            placeholder="Select a component to remove...",
            custom_id="ctrl_remove_sel",
            options=self._comp_options(),
        ))
        sel_row.children[0].callback = self._cb_remove_sel
        c.add_item(sel_row)

        cancel_row = ui.ActionRow(
            ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ctrl_cancel")
        )
        cancel_row.children[0].callback = self._cb_cancel
        c.add_item(cancel_row)
        return c

    def _ctrl_reorder(self) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Reorder Components**"))
        c.add_item(ui.Separator())

        if self._reorder_index is not None:
            label = _comp_label(self._data[self._reorder_index], self._reorder_index)
            c.add_item(ui.TextDisplay(f"-# Selected: **{label[:80]}**"))
        else:
            c.add_item(ui.TextDisplay("-# Select a component below, then use Move Up / Move Down."))

        c.add_item(ui.Separator(visible=False))

        sel_row = ui.ActionRow(ui.Select(
            placeholder="Select a component to move...",
            custom_id="ctrl_reorder_sel",
            options=self._comp_options(),
        ))
        sel_row.children[0].callback = self._cb_reorder_sel
        c.add_item(sel_row)

        can_up   = self._reorder_index is not None and self._reorder_index > 0
        can_down = self._reorder_index is not None and self._reorder_index < len(self._data) - 1

        nav_row = ui.ActionRow(
            ui.Button(label="Move Up",   style=discord.ButtonStyle.secondary, custom_id="ctrl_move_up",   disabled=not can_up),
            ui.Button(label="Move Down", style=discord.ButtonStyle.secondary, custom_id="ctrl_move_down", disabled=not can_down),
            ui.Button(label="Done",      style=discord.ButtonStyle.primary,   custom_id="ctrl_reorder_done"),
        )
        nav_row.children[0].callback = self._cb_move_up
        nav_row.children[1].callback = self._cb_move_down
        nav_row.children[2].callback = self._cb_cancel
        c.add_item(nav_row)
        return c

    def _ctrl_send(self) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Send Container**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(
            "-# Select the channel to send your container to."
        ))
        c.add_item(ui.Separator(visible=False))

        sel_row = ui.ActionRow(ui.ChannelSelect(
            placeholder="Select a channel...",
            custom_id="ctrl_channel_sel",
            channel_types=[discord.ChannelType.text, discord.ChannelType.news],
        ))
        sel_row.children[0].callback = self._cb_channel_sel
        c.add_item(sel_row)

        cancel_row = ui.ActionRow(
            ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, custom_id="ctrl_cancel")
        )
        cancel_row.children[0].callback = self._cb_cancel
        c.add_item(cancel_row)
        return c

    def _ctrl_sent(self, channel_mention: str) -> ui.Container:
        c = ui.Container(accent_color=None)
        c.add_item(ui.TextDisplay("**Container Sent <:success:1506951632670298162>**"))
        c.add_item(ui.Separator())
        c.add_item(ui.TextDisplay(f"Your container was sent to {channel_mention}."))
        c.add_item(ui.Separator(visible=False))

        reset_row = ui.ActionRow(
            ui.Button(label="Build Another", style=discord.ButtonStyle.secondary, custom_id="ctrl_reset")
        )
        reset_row.children[0].callback = self._cb_reset
        c.add_item(reset_row)
        return c

    # ── rebuild ──

    def _rebuild(self, sent_mention: str | None = None) -> None:
        self.clear_items()
        self.add_item(self._build_preview())

        if self._mode == "normal":
            self.add_item(self._ctrl_normal())
        elif self._mode == "color":
            self.add_item(self._ctrl_color())
        elif self._mode == "edit":
            self.add_item(self._ctrl_edit())
        elif self._mode == "remove":
            self.add_item(self._ctrl_remove())
        elif self._mode == "reorder":
            self.add_item(self._ctrl_reorder())
        elif self._mode == "send":
            self.add_item(self._ctrl_send())
        elif self._mode == "sent":
            self.add_item(self._ctrl_sent(sent_mention or "the selected channel"))

    # ── author guard ──

    async def _guard(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "Only the person who ran this command can use these controls.",
                ephemeral=True,
            )
            return False
        return True

    # ── callbacks ──

    async def _cb_add(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        value = interaction.data["values"][0]
        modal_cls = {
            "text":          _TextModal,
            "separator":     _SeparatorModal,
            "section":       _SectionModal,
            "media_gallery": _GalleryModal,
            "button_row":    _ButtonRowModal,
        }[value]
        await interaction.response.send_modal(modal_cls(self))

    async def _cb_edit_btn(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._mode = "edit"
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_remove_btn(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._mode = "remove"
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_color_btn(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._mode = "color"
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_reorder_btn(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._mode = "reorder"
        self._reorder_index = None
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_send_btn(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        if not self._data:
            await interaction.response.send_message(
                "<:wickk:1506950253545394257> Your container is empty. Add at least one component before sending.",
                ephemeral=True,
            )
            return
        self._mode = "send"
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_cancel(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._mode = "normal"
        self._reorder_index = None
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_color_sel(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._color_key = interaction.data["values"][0]
        self._mode = "normal"
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_edit_sel(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        index = int(interaction.data["values"][0])
        comp = self._data[index]
        modal_cls = {
            "text":          _TextModal,
            "separator":     _SeparatorModal,
            "section":       _SectionModal,
            "media_gallery": _GalleryModal,
            "button_row":    _ButtonRowModal,
        }[comp["type"]]
        await interaction.response.send_modal(modal_cls(self, index))

    async def _cb_remove_sel(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        index = int(interaction.data["values"][0])
        self._data.pop(index)
        if self._reorder_index is not None and self._reorder_index >= len(self._data):
            self._reorder_index = max(0, len(self._data) - 1) if self._data else None
        self._mode = "normal"
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_reorder_sel(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._reorder_index = int(interaction.data["values"][0])
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_move_up(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        i = self._reorder_index
        if i is not None and i > 0:
            self._data[i], self._data[i - 1] = self._data[i - 1], self._data[i]
            self._reorder_index = i - 1
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_move_down(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        i = self._reorder_index
        if i is not None and i < len(self._data) - 1:
            self._data[i], self._data[i + 1] = self._data[i + 1], self._data[i]
            self._reorder_index = i + 1
        self._rebuild()
        await interaction.response.edit_message(view=self)

    async def _cb_channel_sel(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return

        channel_id = int(interaction.data["values"][0])
        channel = interaction.guild.get_channel(channel_id)
        if channel is None:
            await interaction.response.send_message("Could not find that channel.", ephemeral=True)
            return

        # FIX: defer FIRST before doing any async work, otherwise the 3-second
        # Discord window expires while we're awaiting channel.send()
        await interaction.response.defer()

        out_view = ui.LayoutView(timeout=None)
        out_container = ui.Container(accent_color=self._color())
        if not self._data:
            out_container.add_item(ui.TextDisplay("*(empty container)*"))
        else:
            for comp in self._data:
                _render_into(out_container, comp)
        out_view.add_item(out_container)

        try:
            await channel.send(view=out_view)
        except discord.Forbidden:
            await interaction.followup.send(
                f"<:wickk:1506950253545394257> I don't have permission to send messages in {channel.mention}.",
                ephemeral=True,
            )
            return
        except Exception as exc:
            await interaction.followup.send(
                f"<:wickk:1506950253545394257> Failed to send: {exc}",
                ephemeral=True,
            )
            return

        self._mode = "sent"
        self._rebuild(sent_mention=channel.mention)
        # FIX: after defer we must use followup.edit_message
        await interaction.followup.edit_message(
            message_id=interaction.message.id, view=self
        )

    async def _cb_reset(self, interaction: discord.Interaction):
        if not await self._guard(interaction):
            return
        self._color_key = "none"
        self._data = []
        self._mode = "normal"
        self._reorder_index = None
        self._rebuild()
        await interaction.response.edit_message(view=self)


# ── Cog ───────────────────────────────────────────────────────────────────────

class ContainerBuilder(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name="container", aliases=["build", "cb"])
    @commands.guild_only()
    async def container_cmd(self, ctx: commands.Context):
        """Interactively build and send a Components V2 container."""
        view = BuilderView(author_id=ctx.author.id)
        msg = await ctx.send(view=view)
        view.message_id = msg.id


async def setup(bot):
    await bot.add_cog(ContainerBuilder(bot))
