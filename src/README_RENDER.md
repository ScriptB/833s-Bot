Render (Free) setup:
- Service type: Web Service
- Build: pip install -U pip && pip install -r requirements.txt && pip install -e .
- Start: python -m guardian.render_entry
Env vars:
- DISCORD_TOKEN = your bot token
- GUILD_ID (optional) = limit commands to one guild for faster sync
