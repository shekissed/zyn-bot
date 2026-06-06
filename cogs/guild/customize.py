# cogs/customize.py - /customize avatar | banner | bio (Slash, Premium Only)
import discord
import aiosqlite
import time
import sys
from discord.ext import commands
from discord import app_commands
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from main import PREMIUM_DB
from emojis import CHECK, CROSS, REPLY


async def _has_premium(user_id: int) -> bool:
    async with aiosqlite.connect(PREMIUM_DB) as db:
        async with db.execute(
            "SELECT expires FROM premium_users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
    return bool(row and row[0] > time.time())


# ── Sentinel cogs so LOCKED_COGS check in main.py keeps working ──
class ChangeAvatar(commands.Cog): pass
class ChangeBanner(commands.Cog): pass
class ChangeBio(commands.Cog):    pass


# ── Main cog with the /customize group ───────────────────────────
class CustomizeCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    customize = app_commands.Group(
        name="customize",
        description="Customize the bot's appearance (Premium only)"
    )

    # ── /customize avatar ─────────────────────────────────────
    @customize.command(name="avatar", description="Change the bot's server avatar")
    @app_commands.describe(image="Image or GIF file (PNG, JPG, GIF, WEBP)")
    async def cmd_avatar(self, interaction: discord.Interaction, image: discord.Attachment):
        if not await _has_premium(interaction.user.id):
            return await interaction.response.send_message(embed=discord.Embed(
                description=f"{CROSS} You don't have an active premium subscription.",
                color=0x2b2d31
            ), ephemeral=True)

        if not image.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return await interaction.response.send_message(embed=discord.Embed(
                description=f"{CROSS} Only PNG, JPG, GIF, or WEBP files are allowed.",
                color=0x2b2d31
            ), ephemeral=True)

        await interaction.response.defer()

        try:
            await interaction.guild.me.edit(avatar=await image.read())
        except discord.HTTPException as e:
            return await interaction.followup.send(embed=discord.Embed(
                description=f"{CROSS} Failed to update avatar: `{e}`",
                color=0x2b2d31
            ), ephemeral=True)

        embed = discord.Embed(color=0x2b2d31)
        embed.title = f"{CHECK} Avatar Updated"
        embed.description = f"{REPLY} The bot's server avatar has been successfully changed."
        embed.set_thumbnail(url=image.url)
        await interaction.followup.send(embed=embed)

    # ── /customize banner ─────────────────────────────────────
    @customize.command(name="banner", description="Change the bot's server banner")
    @app_commands.describe(image="Image or GIF file (PNG, JPG, GIF, WEBP)")
    async def cmd_banner(self, interaction: discord.Interaction, image: discord.Attachment):
        if not await _has_premium(interaction.user.id):
            return await interaction.response.send_message(embed=discord.Embed(
                description=f"{CROSS} You don't have an active premium subscription.",
                color=0x2b2d31
            ), ephemeral=True)

        if not image.filename.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
            return await interaction.response.send_message(embed=discord.Embed(
                description=f"{CROSS} Only PNG, JPG, GIF, or WEBP files are allowed.",
                color=0x2b2d31
            ), ephemeral=True)

        await interaction.response.defer()

        try:
            await self.bot.user.edit(banner=await image.read())
        except discord.HTTPException as e:
            return await interaction.followup.send(embed=discord.Embed(
                description=f"{CROSS} Failed to update banner: `{e}`",
                color=0x2b2d31
            ), ephemeral=True)

        embed = discord.Embed(color=0x2b2d31)
        embed.title = f"{CHECK} Banner Updated"
        embed.description = f"{REPLY} The bot's server banner has been successfully changed."
        embed.set_image(url=image.url)
        await interaction.followup.send(embed=embed)

    # ── /customize bio ────────────────────────────────────────
    @customize.command(name="bio", description="Change the bot's bio")
    @app_commands.describe(bio="New bio text (max 190 characters)")
    async def cmd_bio(self, interaction: discord.Interaction, bio: str):
        if not await _has_premium(interaction.user.id):
            return await interaction.response.send_message(embed=discord.Embed(
                description=f"{CROSS} You don't have an active premium subscription.",
                color=0x2b2d31
            ), ephemeral=True)

        if len(bio) > 190:
            return await interaction.response.send_message(embed=discord.Embed(
                description=f"{CROSS} Bio must be 190 characters or fewer.",
                color=0x2b2d31
            ), ephemeral=True)

        await interaction.response.defer()

        try:
            await self.bot.user.edit(bio=bio)
        except discord.HTTPException as e:
            return await interaction.followup.send(embed=discord.Embed(
                description=f"{CROSS} Failed to update bio: `{e}`",
                color=0x2b2d31
            ), ephemeral=True)

        embed = discord.Embed(color=0x2b2d31)
        embed.title = f"{CHECK} Bio Updated"
        embed.description = f"{REPLY} The bot's server bio has been successfully updated."
        await interaction.followup.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(ChangeAvatar(bot))
    await bot.add_cog(ChangeBanner(bot))
    await bot.add_cog(ChangeBio(bot))
    await bot.add_cog(CustomizeCog(bot))
