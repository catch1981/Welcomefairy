
import os
import json
import asyncio
import logging
from datetime import datetime, timezone

import discord
from discord.ext import commands

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("welcome_fairy")

# ---------- Configuration via ENV ----------
DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = int(os.environ.get("GUILD_ID", "0"))  # 0 = no pinning
WELCOME_CHANNEL_ID = int(os.environ.get("WELCOME_CHANNEL_ID", "0"))
WITCHPATH_CHANNEL_ID = int(os.environ.get("WITCHPATH_CHANNEL_ID", "0"))
FRACTUREPATH_CHANNEL_ID = int(os.environ.get("FRACTUREPATH_CHANNEL_ID", "0"))
# Role names (created automatically if missing)
WITCH_ROLE_NAME = os.environ.get("WITCH_ROLE_NAME", "Witchpath")
FRACTURE_ROLE_NAME = os.environ.get("FRACTURE_ROLE_NAME", "Fracturepath")

# Firebase service account JSON is expected in env var FIREBASE_SERVICE_ACCOUNT.
FIREBASE_SERVICE_ACCOUNT = os.environ.get("FIREBASE_SERVICE_ACCOUNT")

if not DISCORD_TOKEN:
    raise SystemExit("Missing DISCORD_TOKEN")
if not WELCOME_CHANNEL_ID:
    raise SystemExit("Missing WELCOME_CHANNEL_ID")

# ---------- Firebase Setup ----------
db = None
if FIREBASE_SERVICE_ACCOUNT:
    try:
        cred_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        log.info("Connected to Firebase Firestore.")
    except Exception as e:
        log.error("Failed to init Firebase: %s", e)
        db = None
else:
    log.warning("FIREBASE_SERVICE_ACCOUNT not provided; Firebase logging disabled.")

# ---------- Discord Bot Setup ----------
intents = discord.Intents.default()
intents.members = True  # For member join events
intents.guilds = True
intents.message_content = False

bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- Utilities ----------
async def ensure_role(guild: discord.Guild, role_name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=role_name)
    if role is None:
        role = await guild.create_role(name=role_name, reason="WelcomeFairy auto-create")
    return role

async def log_choice_to_firebase(member: discord.Member, choice: str):
    if not db:
        return
    doc = {
        "user_id": str(member.id),
        "username": str(member),
        "choice": choice,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "guild_id": str(member.guild.id),
    }
    try:
        db.collection("coven_onboarding").add(doc)
    except Exception as e:
        log.error("Firestore write failed: %s", e)

class PathChoiceView(discord.ui.View):
    def __init__(self, timeout: float | None = 600):
        super().__init__(timeout=timeout)

    @discord.ui.button(label="☽ Witchpath", style=discord.ButtonStyle.primary, custom_id="choose_witch")
    async def choose_witch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_choice(interaction, "witch")

    @discord.ui.button(label="⛨ Fracturepath", style=discord.ButtonStyle.secondary, custom_id="choose_fracture")
    async def choose_fracture(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._handle_choice(interaction, "fracture")

    async def _handle_choice(self, interaction: discord.Interaction, choice: str):
        member = interaction.user
        guild = interaction.guild
        if guild is None:
            await interaction.response.send_message("This can only be used in a server.", ephemeral=True)
            return

        if choice == "witch":
            role = await ensure_role(guild, WITCH_ROLE_NAME)
            channel_id = WITCHPATH_CHANNEL_ID
            role_name = WITCH_ROLE_NAME
        else:
            role = await ensure_role(guild, FRACTURE_ROLE_NAME)
            channel_id = FRACTUREPATH_CHANNEL_ID
            role_name = FRACTURE_ROLE_NAME

        try:
            await member.add_roles(role, reason=f"WelcomeFairy choice: {choice}")
        except discord.Forbidden:
            await interaction.response.send_message("I lack permission to assign roles. Please grant 'Manage Roles'.", ephemeral=True)
            return

        # Drop a nudge into the selected channel if configured
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel is not None:
                try:
                    await channel.send(f"{member.mention} — your path is set: **{role_name}**. Begin with the pinned scroll.")
                except Exception as e:
                    log.warning("Failed to send to path channel: %s", e)

        await log_choice_to_firebase(member, choice)
        await interaction.response.send_message(f"Path locked: **{role_name}**. Check your channel sidebar for access ✨", ephemeral=True)

@bot.event
async def on_ready():
    log.info("WelcomeFairy online as %s (ID: %s)", bot.user, bot.user.id)
    # Optional: pin a fresh welcome panel in the welcome channel
    if GUILD_ID and WELCOME_CHANNEL_ID:
        guild = bot.get_guild(GUILD_ID)
        channel = guild.get_channel(WELCOME_CHANNEL_ID) if guild else None
        if channel:
            try:
                view = PathChoiceView()
                await channel.send(
                    "🧚 **Welcome to COVEN/ꔷZERO**
Choose your path to unlock the right circle:",
                    view=view
                )
            except Exception as e:
                log.warning("Could not seed welcome panel: %s", e)

@bot.event
async def on_member_join(member: discord.Member):
    # Drop a welcome message with buttons
    channel = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if channel is None:
        log.warning("Welcome channel not found.")
        return
    view = PathChoiceView()
    try:
        await channel.send(
            f"👋 {member.mention} — you made it.
Choose your path below to begin:",
            view=view
        )
    except Exception as e:
        log.warning("Welcome message failed: %s", e)

# Simple health command
@bot.command(name="ping")
async def ping(ctx: commands.Context):
    await ctx.reply("WelcomeFairy is alive ✨")

def main():
    bot.run(DISCORD_TOKEN, log_handler=None)

if __name__ == "__main__":
    main()
