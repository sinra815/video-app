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
3. **AI image-to-video** — a photo + a text prompt (what motion/change to
   apply) generates a short video via diffusers' LTX-Video pipeline
   (`Lightricks/LTX-Video`) on the same Colab GPU lifecycle. Also supports
   giving the image as a URL instead of uploading a file, since the server
   fetches it itself.

## Stack

- Backend: FastAPI (Python), background job queue via a thread pool
- Frontend: React + Vite

## Colab integration status

**Live and working** on the deployed backend (verified end-to-end against a
real Colab GPU session: provisioning, dependency install, model inference,
video download, teardown). `google-colab-cli` **only supports Linux/macOS**,
so this only runs on the Render deployment, not on a Windows dev machine —
see [`app/colab_client.py`](backend/app/colab_client.py) and
[`app/generators/colab_ai.py`](backend/app/generators/colab_ai.py).

`GET /api/health` reports `colab_cli_available` (whether the `colab` binary is
on `PATH`) so the frontend can show a warning banner when it isn't configured.
Submitting an AI job without a working CLI/auth still creates a job — it just
ends up `failed` with a descriptive error, same as any other runtime failure.

### How auth is wired up

`google-colab-cli`'s OAuth2 flow is a copy-paste flow (visit a URL, paste back
an authorization code) rather than a localhost callback, so it works fine
from a server. The resulting token lives in a Render **Secret File**
(`colab_token.json`, backend service → Environment → Secret Files), and the
start command copies it into place before launching uvicorn:

```
mkdir -p ~/.config/colab-cli && cp /etc/secrets/colab_token.json ~/.config/colab-cli/token.json && uvicorn ...
```

(see [`render.yaml`](render.yaml)). The app always passes `--auth oauth2`
explicitly (`config.COLAB_AUTH`) since the CLI's own default is `adc`.

To (re-)generate the token yourself: run a Python REPL anywhere with
`google-colab-cli` installed and import `colab_cli.auth` directly (not the
`colab` CLI binary — it eagerly imports a Windows-incompatible module even
for unrelated commands). Build an `InstalledAppFlow` from
`colab_cli/oauth_config.json`'s bundled client config with
`redirect_uri = colab_cli.auth.REMOTE_REDIRECT_URI`, call
`authorization_url(prompt="consent", token_usage="remote")`, visit the URL,
and `fetch_token(code=...)` with the pasted-back code. `flow.credentials.to_json()`
is the file to upload as the secret. Refresh tokens don't expire from
inactivity but can be revoked from the Google account's
[third-party access page](https://myaccount.google.com/permissions) — if that
happens, redo this flow and re-upload the secret file.

Upstream issues found and worked around here, all confirmed against real
Colab sessions:
- `google-colab-cli` 0.6.0 calls `jupyter_kernel_client.KernelClient`, which
  was renamed to `JupyterKernelClient` in `jupyter-kernel-client` 1.0.0, with
  no upper bound in its own dependency spec. Pinned to `<1.0.0` in
  [`requirements.txt`](backend/requirements.txt).
- `colab exec`'s own `--timeout` (independent of any timeout in this app)
  defaults to 30s — nowhere near enough for a model download plus GPU
  inference. Raised explicitly in `ColabSession.exec_file`.
- `colab exec` always exits 0 even when the executed code raises inside the
  kernel (it only prints the traceback to stderr) — a failing script looks
  identical to a successful one by exit code alone. `exec_file` now requires
  a marker string the script prints as its last line on success
  (`success_marker=`), or raises using the captured output.
- `colab upload`'s Jupyter Contents API payload hardcodes `"chunk": 1` and
  never sends a finalizing chunk, leaving the remote file
  truncated/unreadable (`colab upload` itself reports success). Worked
  around in `ColabImageToVideoGenerator` by embedding the source image as
  base64 directly in the generated script instead of uploading it.
- Image-to-video originally used `I2VGenXLPipeline` (2023, deprecated
  upstream). Even after tuning resolution up from an initial safe fallback
  (512x896) to reclaim unused T4 headroom (576x1024, confirmed to run
  without OOM), a real generation showed severe temporal instability: a
  coherent first frame that visibly collapsed into gray noise by the last
  frame of a 16-frame clip. This wasn't a resolution problem, so raising
  resolution further wouldn't have fixed it.
- Switched image-to-video to `LTXImageToVideoPipeline`
  ([Lightricks/LTX-Video](https://huggingface.co/Lightricks/LTX-Video),
  Apache-2.0, Nov 2024) — more recent and actively maintained than
  I2VGenXL, and documented at ~10GB VRAM for a 704x480/161-frame/50-step
  generation, comfortably under a T4's 16GB even before scaling resolution
  up per GPU tier (see `_GPU_PROFILES` in
  [`colab_image_to_video.py`](backend/app/generators/colab_image_to_video.py)).
  Its T5-XXL text encoder is ~11B params on its own, so
  `enable_model_cpu_offload()` (in
  [`colab_image_to_video_template.py`](backend/app/generators/colab_image_to_video_template.py))
  is load-bearing here too, not just an optimization.
  LTX-Video also requires `num_frames` of the form `8k+1` (its temporal VAE
  compresses by 8x) — `_ltx_num_frames()` rounds the requested duration to
  the nearest valid count.
- Since each job is a fresh Colab VM with no persistent disk, LTX-Video's
  ~20GB of weights get re-downloaded from the HF Hub every single job -
  anonymously, that download is rate-limited enough to blow past the 1700s
  exec timeout before inference even starts (confirmed against a real run).
  Set `HF_TOKEN` (a free, read-only [HF access
  token](https://huggingface.co/settings/tokens)) as a Render env var on the
  backend service to lift that limit - see `config.HF_TOKEN`.

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

## Email notifications on job completion

Each generation form has an optional "notify email" field. When set, the
backend emails that address once the job finishes — the generated video is
attached directly (rather than a download link) so it isn't lost if the
free-tier instance restarts before you check it; only if the video is too
large to attach (>20MB) does it fall back to a link, which requires
`PUBLIC_BASE_URL` to be set. On failure, the email includes the error.

This needs an SMTP relay configured via env vars on the backend service (see
[`app/config.py`](backend/app/config.py) and
[`app/email_notify.py`](backend/app/email_notify.py)) — notifications are
silently skipped if `SMTP_HOST` isn't set:

- `SMTP_HOST`, `SMTP_PORT` (defaults to 587), `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_FROM` (defaults to `SMTP_USER`).
- `PUBLIC_BASE_URL` — this backend's own public URL (e.g.
  `https://video-app-backend-idmf.onrender.com`, no trailing slash), only
  used for the oversized-video fallback link.

Works with any SMTP provider. For Gmail: `SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=587`, `SMTP_USER` = your Gmail address, `SMTP_PASSWORD` = a
[Google App Password](https://myaccount.google.com/apppasswords) (a regular
account password won't work with 2FA enabled, which Google requires for App
Passwords anyway). Set these as Render environment variables on the backend
service (Environment tab) — same place as `ALLOWED_ORIGINS`, no secret file
needed since these aren't multi-line like the Colab token — then redeploy.

**Caveats on Render's free tier:**

- No persistent disk — uploaded images and generated videos live only on the
  container's local disk, so they're **lost on every redeploy or restart**.
  Fine for trying it out; for real use, add a paid persistent disk mounted at
  `backend/storage`, or swap local storage for S3-compatible object storage
  (not implemented here).
- The free web service spins down after 15 minutes of inactivity — the first
  request after that takes 30-60s to wake it back up.
- The Colab OAuth token is stored as a Render Secret File, which — unlike
  local disk — *does* survive redeploys and restarts (see "How auth is wired
  up" above). If Colab jobs start failing with an auth error, the refresh
  token was likely revoked and needs regenerating.
- Colab's free tier has unpredictable GPU availability and rate limits meant
  for interactive notebook use, not a production backend — expect occasional
  `colab new` failures under real traffic. Colab Pro/Pro+ is more reliable for
  sustained automated use.

## Notes for Windows developers

- `google-colab-cli` genuinely doesn't work on Windows (Windows-only
  `import termios` crash at startup) — this is expected, not a bug in this
  app. Use WSL or a Linux/macOS box to actually exercise the AI path.
- If you hit `esbuild`-related `ENOENT` spawn errors from `npm`/`vite` in a
  sandboxed or virtualized filesystem environment, set `ESBUILD_BINARY_PATH`
  to the literal (non-virtualized) path of
  `node_modules/@esbuild/win32-x64/esbuild.exe` before running `npm install`
  or `vite build`. This isn't needed on a normal Windows install.
