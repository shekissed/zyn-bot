import discord
from discord.ext import commands
from discord import SelectOption
from discord.ui import (
    LayoutView,
    Container,
    Section,
    TextDisplay,
    Separator,
    Select,
    ActionRow,
    Thumbnail,
    Button,
    button
)
import sys
from pathlib import Path
import logging
import traceback
from datetime import datetime

# Add parent directory to path to import main config
sys.path.insert(0, str(Path(__file__).parent.parent))
from main import DEFAULT_PREFIX
from emojis import (
    CAT_ANTINUKE, CAT_AUTOMOD, CAT_AUTOMATIONS, CAT_AUTORESPONDER,
    CAT_AUTOREACT, CAT_ROLES, CAT_FUN, CAT_INFO, CAT_GIVEAWAY,
    CAT_TRACKER, CAT_ADVANCED_LOGGING, CAT_MODERATION, CAT_MUSIC,
    CAT_PROFILE, CAT_PFP, CAT_ROLEPLAY, CAT_SOCIAL, CAT_EMBED,
    CAT_UTILITY, CAT_VOICEMASTER, CAT_WELCOME, CAT_AI
)

# ---------------------------------------------------------------------------
# Category definitions
# Each entry has:
#   "emoji"    – the emoji shown next to the module name in the home list
#   "commands" – list of (command_name, description) tuples
#   "description" – shown in the dropdown and at the top of the module page
# ---------------------------------------------------------------------------
CATEGORY_COMMANDS = {
    "AntiNuke": {
        "emoji": CAT_ANTINUKE,
        "description": "Advanced protection against server nuking and unauthorised actions.",
        "commands": [
            ("antinuke", "View antinuke status"),
            ("antinuke enable", "Enable antinuke protection"),
            ("antinuke disable", "Disable antinuke protection"),
            ("antinuke whitelist", "Whitelist a member"),
            ("antinuke unwhitelist", "Remove whitelist"),
            ("extraowner set", "Set extra owner"),
            ("extraowner reset", "Reset extra owner"),
            ("extraowner view", "View extra owners"),
        ],
    },
    "AutoMod": {
        "emoji": CAT_AUTOMOD,
        "description": "Automatic moderation to keep your server safe from spam, invites, and disruptions.",
        "commands": [
            ("automod enable", "Enable automod features"),
            ("automod disable", "Disable automod features"),
            ("automod config", "Configure automod settings"),
            ("automod punishment", "Set punishment methods"),
        ],
    },
    "Automations": {
        "emoji": CAT_AUTOMATIONS,
        "description": "Set up automatic actions and triggers for your server.",
        "commands": [
            ("autoreact add", "Add an auto-reaction trigger"),
            ("autoreact remove", "Remove an auto-reaction trigger"),
            ("autoreact list", "List all auto-reaction triggers"),
        ],
    },
    "Autoresponder": {
        "emoji": CAT_AUTORESPONDER,
        "description": "Setup automatic responses to specific keywords.",
        "commands": [
            ("ar add", "Add an auto-response"),
            ("ar remove", "Remove an auto-response"),
            ("ar list", "List all auto-responses"),
        ],
    },
    "Roles": {
        "emoji": CAT_ROLES,
        "description": "Create and manage self-assignable role menus for your members.",
        "commands": [
            ("roles selection", "Create a self-role menu with a list of roles"),
        ],
    },
    "Fun": {
        "emoji": CAT_FUN,
        "description": "Fun anime-style roleplay commands with GIFs. Interact with members in a cute and expressive way!",
        "commands": [
            ("hug", "Hug someone warmly"),
            ("kiss", "Kiss someone"),
            ("slap", "Slap someone"),
            ("pat", "Pat someone on the head"),
            ("poke", "Poke someone"),
            ("cuddle", "Cuddle with someone"),
            ("punch", "Punch someone"),
            ("bite", "Bite someone"),
            ("lick", "Lick someone"),
            ("highfive", "High five someone"),
            ("feed", "Feed someone"),
            ("stare", "Stare at someone"),
            ("tickle", "Tickle someone"),
            ("handhold", "Hold someone's hand"),
            ("nom", "Nom on someone"),
            ("yeet", "Yeet someone into the void"),
            ("kill", "Eliminate someone"),
            ("throw", "Throw someone"),
            ("smile", "Smile at someone or just smile"),
            ("wink", "Wink at someone"),
            ("wave", "Wave at someone"),
            ("cry", "Cry"),
            ("dance", "Dance"),
            ("blush", "Blush"),
            ("ship", "Ship two members and check compatibility"),
        ],
    },
    "Info": {
        "emoji": CAT_INFO,
        "description": "Information commands to get details about the bot and server.",
        "commands": [
            ("help", "Show this help menu"),
            ("ping", "Check bot latency"),
            ("stats", "View bot statistics"),
            ("botinfo", "Get bot information"),
            ("uptime", "Check bot uptime"),
            ("invite", "Get bot invite link"),
            ("support", "Join support server"),
            ("vote", "Vote for the bot"),
        ],
    },
    "Giveaway": {
        "emoji": CAT_GIVEAWAY,
        "description": "Host and manage giveaways for your community.",
        "commands": [
            ("giveaway start", "Start a new giveaway"),
            ("giveaway end", "End a giveaway early"),
            ("giveaway reroll", "Reroll a giveaway winner"),
            ("giveaway list", "List active giveaways"),
        ],
    },
    "Tracker": {
        "emoji": CAT_TRACKER,
        "description": "Track invites, messages, and member activity to reward active users.",
        "commands": [
            ("invites", "Check your invites"),
            ("inviter", "See who invited you"),
            ("invited", "See who you invited"),
            ("inviteinfo", "Get invite information"),
            ("addinvites", "Add invite count"),
            ("removeinvites", "Remove invite count"),
            ("messages", "Check message count"),
            ("addmessages", "Add message count"),
            ("removemessages", "Remove message count"),
            ("clearmessages", "Clear message counts"),
            ("resetmymessages", "Reset your message count"),
        ],
    },
    "Advanced Logging": {
        "emoji": CAT_ADVANCED_LOGGING,
        "description": "Advanced per-guild logging. Track members, voice, messages, channels, roles, and server changes.",
        "commands": [
            ("/log status", "View all configured log channels"),
            ("/log disable", "Disable a specific log type"),
            ("/log disable-all", "Disable ALL logging"),
            ("/log member-join", "Log channel for members joining"),
            ("/log member-leave", "Log channel for members leaving"),
            ("/log member-update", "Log channel for member updates"),
            ("/log member-ban", "Log channel for member bans"),
            ("/log member-unban", "Log channel for member unbans"),
            ("/log voice", "Log channel for voice activity"),
            ("/log message-delete", "Log channel for deleted messages"),
            ("/log message-edit", "Log channel for edited messages"),
            ("/log channel-create", "Log channel for channel creations"),
            ("/log channel-delete", "Log channel for channel deletions"),
            ("/log channel-update", "Log channel for channel updates"),
            ("/log role-create", "Log channel for role creations"),
            ("/log role-delete", "Log channel for role deletions"),
            ("/log role-update", "Log channel for role updates"),
            ("/log server-update", "Log channel for server setting changes"),
            ("/log invite-create", "Log channel for invite creations"),
            ("/log invite-delete", "Log channel for invite deletions"),
        ],
    },
    "Moderation": {
        "emoji": CAT_MODERATION,
        "description": "Powerful moderation tools to manage your server and keep members in check.",
        "commands": [
            ("ban", "Ban a member from the server"),
            ("kick", "Kick a member from the server"),
            ("mute", "Mute a member"),
            ("unmute", "Unmute a member"),
            ("lock", "Lock a channel"),
            ("unlock", "Unlock a channel"),
            ("hide", "Hide a channel"),
            ("unhide", "Unhide a channel"),
            ("unban", "Unban a member"),
            ("purge", "Delete multiple messages"),
            ("snipe", "View deleted messages"),
            ("warn", "Warn a member"),
        ],
    },
    "Profile": {
        "emoji": CAT_PROFILE,
        "description": "Customise your personal profile card with a bio, background, and social media links.",
        "commands": [
            ("profile view [member]", "View your or another member's profile"),
            ("profile card [member]", "View a compact profile card"),
            ("profile description <text>", "Set your profile bio"),
            ("profile social <platform> [url]", "Add/remove a social media link"),
            ("profile background <image_url>", "Set your profile background"),
            ("profile reset", "Reset your entire profile"),
            ("serveravatar [member]", "View a member's server avatar"),
            ("serverbanner", "View the server banner"),
            ("serverbio", "View the server description"),
            ("servername", "View the server name and ID"),
            ("serverresetprofile <member>", "Reset a member's profile"),
        ],
    },
    "Pfp": {
        "emoji": CAT_PFP,
        "description": "Get random profile pictures from various categories.",
        "commands": [
            ("boys", "Random boy profile pictures"),
            ("girls", "Random girl profile pictures"),
            ("couples", "Random couple pictures"),
            ("anime", "Random anime profile pictures"),
            ("pic", "Random pictures"),
        ],
    },
    "Roleplay": {
        "emoji": CAT_ROLEPLAY,
        "description": "Anime-style roleplay GIF commands to interact with members expressively.",
        "commands": [
            ("hug", "Hug someone"),
            ("kiss", "Kiss someone"),
            ("slap", "Slap someone"),
            ("pat", "Pat someone"),
            ("cuddle", "Cuddle with someone"),
            ("punch", "Punch someone"),
        ],
    },
    "Social": {
        "emoji": CAT_SOCIAL,
        "description": "Social commands to interact with members, set reminders, and translate text.",
        "commands": [
            ("remind", "Set a reminder"),
            ("remind list", "List your active reminders"),
            ("translate", "Translate text to any language"),
        ],
    },
    "Utility": {
        "emoji": CAT_UTILITY,
        "description": "Useful utility commands for everyday server management.",
        "commands": [
            ("avatar", "Get a member's avatar"),
            ("serverinfo", "Get server information"),
            ("userinfo", "Get user information"),
            ("steal", "Steal an emoji"),
            ("afk", "Set AFK status"),
            ("reminder", "Set reminders"),
            ("timer", "Create timers"),
            ("banner", "Get server banner"),
            ("users", "Count members"),
            ("setprefix", "Change command prefix"),
            ("resetprefix", "Reset to default prefix"),
        ],
    },
    "VoiceMaster": {
        "emoji": CAT_VOICEMASTER,
        "description": "Manage and create temporary voice channels for your members.",
        "commands": [
            ("voicemaster setup", "Setup voice channels"),
            ("voicemaster remove", "Remove voice channels"),
        ],
    },
    "Welcome": {
        "emoji": CAT_WELCOME,
        "description": "Setup automatic welcome messages for new members joining your server.",
        "commands": [
            ("greet setup", "Setup welcome message"),
            ("greet reset", "Reset welcome settings"),
            ("greet channel", "Set welcome channel"),
            ("greet edit", "Edit welcome message"),
            ("greet test", "Test welcome message"),
            ("greet config", "View welcome config"),
            ("greet autodelete", "Set auto-delete timer"),
        ],
    },
    "AI": {
        "emoji": CAT_AI,
        "description": "Artificial intelligence features for intelligent server interactions.",
        "commands": [
            ("setup_ai", "Setup AI features"),
            ("reset_ai", "Reset AI settings"),
            ("ai_help", "Get AI help information"),
        ],
    },
    "Container": {
        "emoji": CAT_EMBED,
        "description": "Interactively build and send Components V2 containers with text, images, buttons, galleries, and more.",
        "commands": [
            ("container", "Open the interactive container builder"),
            ("build", "Alias for container builder"),
            ("cb", "Shorthand alias for container builder"),
        ],
    },
}


class HelpView(LayoutView):
    def __init__(self, bot: commands.Bot, author: discord.Member):
        super().__init__(timeout=120)
        self.bot = bot
        self.author = author
        container = self._build_home_container()
        self.add_item(container)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _create_dropdown(self, default_category: str = None) -> Select:
        """Dropdown that lists every category – matches Zynrax 'Select Module From Here' style."""
        def _safe_emoji(emoji_str: str):
            # SelectOption only accepts Unicode emoji or discord.PartialEmoji objects.
            # Raw custom-emoji strings like "<:name:id>" or "<a:name:id>" must be
            # converted to PartialEmoji, otherwise Discord raises a validation error.
            if emoji_str.startswith("<") and emoji_str.endswith(">"):
                try:
                    animated = emoji_str.startswith("<a:")
                    parts = emoji_str.strip("<>").split(":")
                    # parts = ["a", "name", "id"]  or  ["", "name", "id"]
                    name = parts[-2]
                    emoji_id = int(parts[-1])
                    return discord.PartialEmoji(name=name, id=emoji_id, animated=animated)
                except Exception:
                    return None
            return emoji_str or None

        options = [
            SelectOption(
                label=category,
                value=category,
                description=f"Get All {category} Commands",
                emoji=_safe_emoji(data["emoji"]),
                default=(category == default_category) if default_category else False
            )
            for category, data in CATEGORY_COMMANDS.items()
        ]
        dropdown = Select(
            placeholder="❯ Select Module From Here",
            min_values=1,
            max_values=1,
            options=options,
            custom_id=f"help_category_select_{id(self)}"
        )
        dropdown.callback = self.on_select
        return dropdown

    def _build_module_list_text(self) -> str:
        """
        Build the home-screen module list exactly like Zynrax:
            <emoji> » ModuleName
        """
        lines = [f"> {data['emoji']} » {category}" for category, data in CATEGORY_COMMANDS.items()]
        return "\n".join(lines)

    def _get_welcome_section(self) -> Section:
        """
        Home header – mirrors Zynrax layout:
            Hey, I'm <BotName>™
            A powerful multipurpose bot
            • My Prefix is <prefix>
            • Total Commands: <n>
            • Choose a Specific Module of your Desire
              <emoji> » Module
              ...
        """
        total_commands = sum(len(cat["commands"]) for cat in CATEGORY_COMMANDS.values())
        module_list = self._build_module_list_text()

        welcome_text = (
            f"## Hey, I'm {self.bot.user.name}™\n"
            f"A powerful multipurpose bot with the Fastest Antinuke\n\n"
            f"- **My Prefix is** `{DEFAULT_PREFIX}`\n"
            f"- **Total Commands:** {total_commands}\n"
            f"- **Choose a Specific Module of your Desire**\n\n"
            f"{module_list}"
        )

        return Section(
            TextDisplay(welcome_text),
            accessory=Thumbnail(
                media=discord.UnfurledMediaItem(url=self.bot.user.display_avatar.url),
                description=f"{self.bot.user.name}"
            ),
            id=1
        )

    def _build_home_container(self) -> Container:
        dropdown = self._create_dropdown()

        support_btn = Button(
            label="Support",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/bvYrysAU7d"
        )
        invite_btn = Button(
            label="Invite",
            style=discord.ButtonStyle.link,
            url="https://discord.gg/zyn"
        )
        website_btn = Button(
            label="Website",
            style=discord.ButtonStyle.link,
            url="https://zyndev.xyz"
        )

        links_row = ActionRow(support_btn, invite_btn, website_btn)

        return Container(
            self._get_welcome_section(),
            Separator(),
            TextDisplay("**❯ Select Module From Here**"),
            ActionRow(dropdown),
            links_row
        )

    def _get_category_section(self, category: str) -> Section:
        """
        Module page – shows comma-separated command names (Zynrax style),
        with the module description underneath.
        """
        category_data = CATEGORY_COMMANDS.get(category)
        if not category_data:
            return None

        emoji = category_data["emoji"]
        description = category_data.get("description", "")
        cmd_names = [cmd_name for cmd_name, _ in category_data["commands"]]
        commands_inline = ", ".join(cmd_names)

        module_text = (
            f"## {emoji} {category}\n\n"
            f"{description}\n\n"
            f"**Commands**\n"
            f"`{commands_inline}`"
        )

        if len(module_text) > 3950:
            module_text = module_text[:3900] + "\n\n*... and more (too many to display)*"

        return Section(
            TextDisplay(module_text),
            accessory=Thumbnail(
                media=discord.UnfurledMediaItem(url=self.bot.user.display_avatar.url),
                description=f"{category} Commands"
            ),
            id=2
        )

    def _build_category_container(self, category: str) -> Container:
        dropdown = self._create_dropdown(default_category=category)

        back_button = Button(
            label="Home",
            style=discord.ButtonStyle.primary,
            custom_id="help_back_home"
        )
        back_button.callback = self.on_back_home

        dropdown_row = ActionRow(dropdown)
        button_row = ActionRow(back_button)

        return Container(
            self._get_category_section(category),
            Separator(),
            TextDisplay("**❯ Select Another Module:**"),
            dropdown_row,
            button_row
        )

    # ------------------------------------------------------------------
    # Interaction handlers
    # ------------------------------------------------------------------

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "This help menu isn't for you. Run the `help` command yourself.",
                ephemeral=True
            )
            return False
        return True

    async def on_select(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            selected_category = interaction.data.get("values", [None])[0]

            if not selected_category or selected_category not in CATEGORY_COMMANDS:
                await interaction.followup.send("No commands found for this category.", ephemeral=True)
                return

            container = self._build_category_container(selected_category)
            self.clear_items()
            self.add_item(container)
            await interaction.followup.edit_message(message_id=interaction.message.id, view=self)
        except Exception as e:
            print(f"Error in on_select: {e}\n{traceback.format_exc()}")
            if not interaction.response.is_done():
                try:
                    await interaction.response.send_message(f"An error occurred: {str(e)[:100]}", ephemeral=True)
                except Exception:
                    pass

    async def on_back_home(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer()
            container = self._build_home_container()
            self.clear_items()
            self.add_item(container)
            await interaction.followup.edit_message(message_id=interaction.message.id, view=self)
        except Exception as e:
            print(f"Error in on_back_home: {e}\n{traceback.format_exc()}")
            if not interaction.response.is_done():
                try:
                    await interaction.response.send_message(f"An error occurred: {str(e)[:100]}", ephemeral=True)
                except Exception:
                    pass


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------

class HelpCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.logger = logging.getLogger(__name__)
        self.log_channel_id = None

    async def log_error(self, ctx: commands.Context, error: Exception, error_type: str = "Error"):
        self.logger.error(f"[{error_type}] {error}", exc_info=True)
        if self.log_channel_id:
            try:
                log_channel = self.bot.get_channel(self.log_channel_id)
                if log_channel:
                    embed = discord.Embed(
                        title="Help Command Error",
                        description=f"**Error Type:** {error_type}",
                        color=0x525252,
                        timestamp=datetime.utcnow()
                    )
                    embed.add_field(name="Guild", value=f"{ctx.guild.name if ctx.guild else 'DM'} ({ctx.guild.id if ctx.guild else 'N/A'})", inline=False)
                    embed.add_field(name="User", value=f"{ctx.author} ({ctx.author.id})", inline=False)
                    embed.add_field(name="Error Message", value=f"```{str(error)[:1024]}```", inline=False)
                    embed.add_field(name="Traceback", value=f"```{traceback.format_exc()[:1024]}```", inline=False)
                    await log_channel.send(embed=embed)
            except Exception as log_error:
                self.logger.error(f"Failed to send error log: {log_error}")

    async def log_usage(self, ctx: commands.Context):
        self.logger.info(f"Help used by {ctx.author} ({ctx.author.id}) in {ctx.guild.name if ctx.guild else 'DM'}")

    @commands.command(name="help", aliases=["h"])
    async def help_command(self, ctx: commands.Context):
        """Display the help menu."""
        try:
            view = HelpView(self.bot, ctx.author)
            await ctx.send(view=view)
            await self.log_usage(ctx)
        except Exception as error:
            await self.log_error(ctx, error, "HelpCommandError")
            embed = discord.Embed(
                title="Help Command Error",
                description="An error occurred while loading the help menu. This has been reported to the developers.",
                color=0x525252
            )
            try:
                await ctx.send(embed=embed, ephemeral=True)
            except Exception:
                await ctx.send("An error occurred while loading the help menu.", ephemeral=True)


async def setup(bot):
    await bot.add_cog(HelpCog(bot))
