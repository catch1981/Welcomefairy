import os, json, logging
from datetime import datetime, timezone
import discord
from discord.ext import commands

# Firebase Admin
import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("welcome_fairy")

# ── ENV ────────────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0"))
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0"))
WITCHPATH_CHANNEL_ID = int(os.getenv("WITCHPATH_CHANNEL_ID", "0"))
FRACTUREPATH_CHANNEL_ID = int(os.getenv("FRACTUREPATH_CHANNEL_ID", "0"))
WITCH_ROLE_NAME = os.getenv("WITCH_ROLE_NAME", "Witchpath")
FRACTURE_ROLE_NAME = os.getenv("FRACTURE_ROLE_NAME", "Fracturepath")
FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT")

missing = [k for k, v in {
  "DISCORD_TOKEN": DISCORD_TOKEN,
  "WELCOME_CHANNEL_ID": WELCOME_CHANNEL_ID
}.items() if not v]
if missing:
    raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

# ── Firebase ───────────────────────────────────────────────────────────────────
db = None
if FIREBASE_SERVICE_ACCOUNT:
    try:
        cred_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        log.info("Firebase Firestore connected.")
    except Exception as e:
        log.error(f"Firebase init failed: {e}")
else:
    log.warning("FIREBASE_SERVICE_ACCOUNT not set; Firebase logging disabled.")

# ── Discord ────────────────────────────────────────────────────────────────────
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def ensure_role(guild: discord.Guild, name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=name)
    return role or await guild.create_role(name=name, reason="WelcomeFairy auto-create")

async def log_choice(member: discord.Member, choice: str):
    if not db: return
    try:
        db.collection("coven_onboarding").add({
            "user_id": str(member.id),
            "username": str(member),
            "choice": choice,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guild_id": str(member.guild.id),
        })
    except Exception as e:
        log.error(f"Firestore write failed: {e}")

class PathChoiceView(discord.ui.View):
    def __init__(self): super().__init__(timeout=600)

    @discord.ui.button(label="☽ Witchpath", style=discord.ButtonStyle.primary, custom_id="choose_witch")
    async def choose_witch(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._pick(itx, "witch")

    @discord.ui.button(label="⛨ Fracturepath", style=discord.ButtonStyle.secondary, custom_id="choose_fracture")
    async def choose_fracture(self, itx: discord.Interaction, _: discord.ui.Button):
        await self._pick(itx, "fracture")

    async def _pick(self, itx: discord.Interaction, choice: str):
        guild = itx.guild
        member = itx.user
        if not guild:
            return await itx.response.send_message("Use this in a server.", ephemeral=True)

        if choice == "witch":
            role = await ensure_role(guild, WITCH_ROLE_NAME)
            channel_id, role_name = WITCHPATH_CHANNEL_ID, WITCH_ROLE_NAME
        else:
            role = await ensure_role(guild, FRACTURE_ROLE_NAME)
            channel_id, role_name = FRACTUREPATH_CHANNEL_ID, FRACTURE_ROLE_NAME

        await member.add_roles(role)
        await log_choice(member, choice)
        await itx.response.send_message(f"Assigned to {role_name}. Head to <#{channel_id}>.", ephemeral=True)

@bot.event
async def on_ready():
    log.info(f"Logged in as {bot.user} (ID: {bot.user.id})")
    guild = bot.get_guild(GUILD_ID)
    if guild:
        channel = guild.get_channel(WELCOME_CHANNEL_ID)
        if channel:
            await channel.send("Welcome! Choose your path:", view=PathChoiceView())

if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
