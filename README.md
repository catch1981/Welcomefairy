
# WelcomeFairy (COVEN/ꔷZERO)

Discord onboarding bot (Python + discord.py + Firebase). Render-ready via `render.yaml` blueprint.

## Quick Start (Local)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env .env.local  # optional backup
python app.py
```

## Deploy on Render (Blueprint)
1. Push this folder to a new **GitHub repo**.
2. In Render: **New → Blueprint** → paste your repo URL.
3. Set env vars when prompted:
   - `DISCORD_TOKEN` = your bot token
   - `FIREBASE_SERVICE_ACCOUNT` = single-line service account JSON
   - (Already set in `render.yaml`): `GUILD_ID`, channel IDs, role names
4. Deploy. The worker starts and seeds a welcome panel.

## Required Discord Settings
- Developer Portal → Bot → **SERVER MEMBERS INTENT** = ON
- Invite with scopes: `bot`, `applications.commands`
- Permissions: `Manage Roles`, `View Channels`, `Send Messages`
- Move bot's role **above** `Witchpath` and `Fracturepath`

## Firebase
Writes to Firestore collection: `coven_onboarding`

## Commands
- `!ping` — healthcheck
