# Deploy 833's Guardian on Render (Free Plan)

Render Free does **not** provide free Background Worker instances. This project deploys as a **Web Service** and starts:
1) an HTTP health server bound to `0.0.0.0:$PORT`
2) the Discord bot

## Repo requirements (already included)
- `render.yaml` at repo root
- `requirements.txt` at repo root
- `runtime.txt` pinning a stable Python version
- `src/guardian/render_entry.py` (starts health server + bot)

## Steps
1) Push the repo to GitHub.
2) Render Dashboard → New → Blueprint → select repo → Apply.
3) Service → Environment → add `DISCORD_TOKEN` as a **Secret**.
4) Deploy / restart.

## Health endpoints
- GET `/`
- GET `/healthz`

## Free plan caveat
Free web services can spin down when idle; that can take your bot offline until the service is started again.
For always-on 24/7, use a paid plan or a platform that supports workers.


## If you see `Unknown interaction (10062)` in logs
This can happen if the service is restarting/deploying or the interaction isn't acknowledged quickly.
The bot now defers interaction responses immediately and uses follow-ups to avoid this.
