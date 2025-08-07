import os, json, logging, threading
from datetime import datetime, timezone

# --- Keepalive HTTP server (so Render Web Service stays up) ---
try:
    from flask import Flask
    app = Flask(__name__)

    @app.route("/")
    def home():
        return "OK", 200

    def run_web():
        port = int(os.environ.get("PORT", 8080))
        app.run(host="0.0.0.0", port=port)
except Exception as e:
    app = None
    def run_web():
        print(f"[KEEPALIVE] Flask not available: {e}")
# --------------------------------------------------------------

# Third-party libs
try:
    import discord
    from discord.ext import commands
except Exception as e:
    print(f"[BOOT] Failed to import discord.py: {e}")
    raise

# Firebase (optional)
db = None
try:
    import firebase_admin
    from firebase_admin import credentials, firestore
except Exception as e:
    print(f"[BOOT] firebase_admin not installed (logging to Firestore disabled): {e}")
    firebase_admin = None
    credentials = None
    firestore = None

# Logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log = logging.getLogger("welcome_fairy")

def _mask(token: str, show: int = 6) -> str:
    if not token: return "<empty>"
    return f"{token[:2]}...{token[-show:]}" if len(token) > show else "***"

# ENV
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "0") or "0")
WELCOME_CHANNEL_ID = int(os.getenv("WELCOME_CHANNEL_ID", "0") or "0")
WITCHPATH_CHANNEL_ID = int(os.getenv("WITCHPATH_CHANNEL_ID", "0") or "0")
FRACTUREPATH_CHANNEL_ID = int(os.getenv("FRACTUREPATH_CHANNEL_ID", "0") or "0")
WITCH_ROLE_NAME = os.getenv("WITCH_ROLE_NAME", "Witchpath")
FRACTURE_ROLE_NAME = os.getenv("FRACTURE_ROLE_NAME", "Fracturepath")
FIREBASE_SERVICE_ACCOUNT = os.getenv("FIREBASE_SERVICE_ACCOUNT")

log.info("Boot env → "
         f"GUILD_ID={GUILD_ID}, WELCOME_CHANNEL_ID={WELCOME_CHANNEL_ID}, "
         f"WITCHPATH_CHANNEL_ID={WITCHPATH_CHANNEL_ID}, FRACTUREPATH_CHANNEL_ID={FRACTUREPATH_CHANNEL_ID}, "
         f"WITCH_ROLE_NAME='{WITCH_ROLE_NAME}', FRACTURE_ROLE_NAME='{FRACTURE_ROLE_NAME}', "
         f"DISCORD_TOKEN({_mask(DISCORD_TOKEN)})")

if not DISCORD_TOKEN:
    log.error("Missing DISCORD_TOKEN. Set it in Render → Environment → Variables.")
    raise SystemExit(1)
if not WELCOME_CHANNEL_ID:
    log.error("Missing WELCOME_CHANNEL_ID. Set the channel ID for #welcome-to-the-coven.")
    raise SystemExit(1)

# Firebase init (optional)
if FIREBASE_SERVICE_ACCOUNT and firebase_admin and credentials and firestore:
    try:
        cred_info = json.loads(FIREBASE_SERVICE_ACCOUNT)
        cred = credentials.Certificate(cred_info)
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        log.info("Firebase Firestore connected.")
    except Exception as e:
        log.error(f"Firebase init failed: {e}")
else:
    log.warning("FIREBASE_SERVICE_ACCOUNT not set or firebase_admin missing; Firestore logging disabled.")

# Discord bot
intents = discord.Intents.default()
intents.members = True
intents.guilds = True
bot = commands.Bot(command_prefix="!", intents=intents)

async def ensure_role(guild: discord.Guild, name: str) -> discord.Role:
    role = discord.utils.get(guild.roles, name=name)
    if role is None:
        try:
            role = await guild.create_role(name=name, reason="WelcomeFairy auto-create")
            log.info(f"Created role '{name}' in guild {guild.id}")
        except discord.Forbidden:
            log.error("Missing permission to create roles. Grant 'Manage Roles'.")
            raise
    return role

async def log_choice(member: discord.Member, choice: str):
    if not db:
        return
    try:
        db.collection("coven_onboarding").add({
            "user_id": str(member.id),
            "username": str(member),
            "choice": choice,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "guild_id": str(member.guild.id),
        })
        log.info(f"Logged choice: user={member.id} choice={choice}")
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

        try:
            await member.add_roles(role, reason=f"WelcomeFairy choice: {choice}")
        except discord.Forbidden:
            return await itx.response.send_message("I need **Manage Roles** permission.", ephemeral=True)

        if channel_id:
            ch = guild.get_channel(channel_id)
            if ch:
                try:
                    await ch.send(f"{member.mention} — path set: **{role_name}**. See pinned scroll.")
                except Exception as e:
                    log.warning(f"Path channel send failed: {e}")

        await log_choice(member, choice)
        await itx.response.send_message(f"Path locked: **{role_name}**. Check your sidebar ✨", ephemeral=True)

@bot.event
async def on_ready():
    log.info(f"WelcomeFairy online as {bot.user} (ID: {bot.user.id})")
    if GUILD_ID and WELCOME_CHANNEL_ID:
        g = bot.get_guild(GUILD_ID)
        ch = g.get_channel(WELCOME_CHANNEL_ID) if g else None
        if ch:
            try:
                await ch.send("🧚 **Welcome to COVEN/ꔷZERO**\nChoose your path to unlock the right circle:", view=PathChoiceView())
                log.info("Seeded welcome panel.")
            except Exception as e:
                log.warning(f"Seed panel failed: {e}")
        else:
            log.warning("Guild or welcome channel not resolved. Check GUILD_ID/WELCOME_CHANNEL_ID.")

@bot.event
async def on_member_join(member: discord.Member):
    ch = member.guild.get_channel(WELCOME_CHANNEL_ID)
    if not ch:
        log.warning("Welcome channel not found on member join.")
        return
    try:
        await ch.send(f"👋 {member.mention} — you made it.\nChoose your path below to begin:", view=PathChoiceView())
    except Exception as e:
        log.warning(f"Welcome message failed: {e}")

@bot.command()
async def ping(ctx: commands.Context):
    await ctx.reply("WelcomeFairy is alive ✨")

if __name__ == "__main__":
    # Start keepalive web server in background (only if Flask available)
    if app is not None:
        threading.Thread(target=run_web, daemon=True).start()
        log.info("Keepalive web server started.")
    else:
        log.warning("Keepalive disabled (Flask not installed).")

    # Start Discord bot (blocks the main thread)
    bot.run(DISCORD_TOKEN, log_handler=None)
