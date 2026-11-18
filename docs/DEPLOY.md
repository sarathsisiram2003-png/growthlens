# Deploying GrowthLens

Frontend on **Vercel**, backend (FastAPI) on **Render** (Railway notes at the end). Nothing here needs code changes; it is
configuration and a few accounts. Never commit keys: they live in each platform's environment settings.

```
Browser ──▶ Vercel (Next.js)  ──▶  Render (FastAPI + disk at /data)  ──▶ Earth Engine · Overpass · Nominatim · Gemini
```

## 0. What you need

| Account / key | Used for | Where it goes |
|---|---|---|
| Google Cloud project registered for Earth Engine (non-commercial) | satellite data | `EE_PROJECT` |
| A service account on that project, with a JSON key | Earth Engine on a server (no browser login) | `EE_SERVICE_ACCOUNT_JSON` |
| Google AI Studio API key | AI business parsing and briefs | `GEMINI_API_KEY` |
| GitHub repo with this code | both platforms deploy from it | |

## 1. Earth Engine service account (one time)

1. In the Google Cloud console for your Earth Engine project: **IAM & Admin → Service accounts → Create**. Any name, e.g. `growthlens`.
2. Give it the roles **Earth Engine Resource Viewer** and **Service Usage Consumer**.
3. **Keys → Add key → JSON**. A file downloads. This is a secret: don't commit it or paste it into chat.
4. Register the service account for Earth Engine: <https://code.earthengine.google.com/register> → *Service accounts* (or add the account under
   your project's Earth Engine registration). The project must be on the non-commercial plan.
5. Copy the file's *entire contents* into the `EE_SERVICE_ACCOUNT_JSON` variable (step 2 below).

Check it locally first if you like: put the JSON on one line in `backend/.env` as `EE_SERVICE_ACCOUNT_JSON=...` and run
`python -c "from growthlens.satellite import init_ee; init_ee(); print('ok')"` from `backend/`.

## 2. Backend on Render

1. **New → Blueprint**, pick the repo. Render reads [`render.yaml`](../render.yaml): a Docker web service built from `backend/Dockerfile`,
   health check `/health`, and a **2 GB persistent disk at `/data`**.
2. Fill the variables marked `sync: false`:
   - `EE_PROJECT` – your Earth Engine Cloud project id
   - `EE_SERVICE_ACCOUNT_JSON` – the key JSON from step 1
   - `GEMINI_API_KEY` – your AI Studio key
   - `CORS_ORIGINS` – your Vercel URL (set after step 3, then redeploy), e.g. `https://growthlens.vercel.app`
3. Deploy. When it is live, open `https://<service>.onrender.com/health` (should say `ok`) and `/demo` (should list the demo cities).

`TRUST_PROXY=true` is already set so per-client rate limits see real client addresses behind Render's load balancer.

### Free tier trade-off

A persistent disk needs a paid plan. On a free instance (no disk) the service still works, but results, caches and the job
database are wiped on every deploy and restart (and free instances sleep when idle, so the first request after a pause is slow).
The **demo cities keep working** because they are reinstalled from the repository at every start; new searches are simply recomputed
and take a minute or two. For a portfolio demo that is a reasonable default; remove the `disk:` block and set `plan: free` to use it.

## 3. Frontend on Vercel

1. **Add New → Project**, import the repo, set **Root Directory = `frontend`** (framework: Next.js is detected).
2. Environment variable: `NEXT_PUBLIC_API_URL` = the Render URL, no trailing slash (e.g. `https://growthlens-api.onrender.com`).
   This is read at build time, so changing it needs a redeploy.
3. Deploy, then put the resulting URL into Render's `CORS_ORIGINS` and redeploy the backend.

## 4. Check it works

- Start screen shows the demo chips; clicking one opens results instantly.
- Search a new city: the progress steps tick through, then results appear (first run can take a few minutes).
- Open an area's details: satellite images and the AI brief load; the growth slider loads after about a minute the first time.
- `/methodology` shows the backtest table.

## 5. Operating notes

- **Quotas and etiquette.** Earth Engine (non-commercial), Gemini, Overpass and Nominatim are shared or limited services. The API caches
  aggressively and rate-limits per client (`backend/growthlens/ratelimit.py`). Overpass mirrors are sometimes down; the app retries,
  falls back to cached data, and reports partial data clearly rather than failing silently.
- **One process.** Rate limits and the job queue are in-process, so run a single worker. Scaling out needs a shared store (Redis/Postgres).
- **Postgres/Supabase** is the planned production store for the cache and jobs (see the README roadmap); today everything is SQLite plus files
  on the `/data` volume, which is simple and fine for a single instance.
- **Refreshing demo cities.** Rebuild a pack with `python -m growthlens.demo_cli --city "..." --slug ...` (needs live services once), commit
  `backend/demo/`, and redeploy.

## Railway instead of Render

Create a service from the repo with root `backend/` (it detects the Dockerfile), add a **Volume mounted at `/data`**, and set the same
environment variables (`DATA_DIR=/data`, `TRUST_PROXY=true`, `CORS_ORIGINS`, `EE_PROJECT`, `EE_SERVICE_ACCOUNT_JSON`, `GEMINI_API_KEY`).
