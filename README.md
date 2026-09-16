# Video Generator

A web app for generating videos two ways:

1. **Image slideshow** — upload images (+ optional background audio), get an mp4
   with crossfade transitions. Runs locally via `ffmpeg` (bundled through
   `imageio-ffmpeg`), no GPU or external service required.
2. **AI text-to-video** — a text prompt is turned into a short video by
   provisioning a GPU runtime on Google Colab via
   [`google-colab-cli`](https://github.com/googlecolab/google-colab-cli),
   running a diffusers text-to-video pipeline there, and pulling the result
   back.

## Stack

- Backend: FastAPI (Python), background job queue via a thread pool
- Frontend: React + Vite

## Colab integration status

`google-colab-cli` **only supports Linux/macOS** and needs a Google account
authenticated against the Colab API (OAuth2 or ADC), plus available Colab
compute units. Because of that, the AI generation path is built and fully
wired to the CLI's documented commands (`colab new/install/exec/download/stop`,
see [`app/colab_client.py`](backend/app/colab_client.py) and
[`app/generators/colab_ai.py`](backend/app/generators/colab_ai.py)), but it
can only be *exercised* end-to-end on Linux/macOS with the CLI installed and
authenticated:

```bash
uv tool install google-colab-cli
colab auth   # first-time Google OAuth
```

`GET /api/health` reports `colab_cli_available` (whether the `colab` binary is
on `PATH`) so the frontend can show a warning banner when it isn't configured.
Submitting an AI job without a working CLI still creates a job — it just ends
up `failed` with a descriptive error, same as any other runtime failure.

## Running locally

### Backend

```bash
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Then open http://localhost:5173. The frontend calls the backend at
`VITE_API_BASE` (falls back to `http://127.0.0.1:8000` for local dev) — see
[`src/api.js`](frontend/src/api.js).

## Deploying to Render (so it's reachable from a phone anywhere)

This runs two separate Render services from the same repo: a Python web
service for the backend, and a static site for the frontend.

1. Push this repo to GitHub.
2. On [Render](https://render.com), **New > Blueprint**, point it at the repo.
   Render reads [`render.yaml`](render.yaml) and creates both services. If
   Blueprint isn't available on your account, create them manually instead:
   - **Web Service** (backend): root dir `backend`, build command
     `pip install -r requirements.txt`, start command
     `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   - **Static Site** (frontend): root dir `frontend`, build command
     `npm install && npm run build`, publish directory `dist`.
3. Once the backend is deployed, copy its URL (e.g.
   `https://video-app-backend.onrender.com`) and set it as the frontend's
   `VITE_API_BASE` env var, then redeploy the frontend (env vars are baked in
   at build time for a static site).
4. Set the backend's `ALLOWED_ORIGINS` env var to the frontend's URL (e.g.
   `https://video-app-frontend.onrender.com`) so CORS allows it, then redeploy
   the backend.
5. Open the frontend URL on your phone — it works from any network, not just
   the same Wi-Fi as your computer.

**Caveats on Render's free tier:**

- No persistent disk — uploaded images and generated videos live only on the
  container's local disk, so they're **lost on every redeploy or restart**.
  Fine for trying it out; for real use, add a paid persistent disk mounted at
  `backend/storage`, or swap local storage for S3-compatible object storage
  (not implemented here).
- The free web service spins down after 15 minutes of inactivity — the first
  request after that takes 30-60s to wake it back up.
- The AI Colab path needs `colab auth`'s interactive Google OAuth flow, which
  isn't practical to run in a normal deploy. It would need a paid plan with
  shell access to authenticate once, and even then the auth token won't
  survive a restart without persistent disk. The slideshow feature is
  unaffected by any of this.

## Notes for Windows developers

- `google-colab-cli` genuinely doesn't work on Windows (Windows-only
  `import termios` crash at startup) — this is expected, not a bug in this
  app. Use WSL or a Linux/macOS box to actually exercise the AI path.
- If you hit `esbuild`-related `ENOENT` spawn errors from `npm`/`vite` in a
  sandboxed or virtualized filesystem environment, set `ESBUILD_BINARY_PATH`
  to the literal (non-virtualized) path of
  `node_modules/@esbuild/win32-x64/esbuild.exe` before running `npm install`
  or `vite build`. This isn't needed on a normal Windows install.
