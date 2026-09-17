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
   apply) generates a short video via diffusers' I2VGenXL pipeline
   (`ali-vilab/i2vgen-xl`) on the same Colab GPU lifecycle.

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
- `I2VGenXLPipeline` is deprecated in current `diffusers` (dropped from
  active maintenance after 0.33.1) and reaches into `CLIPTextModel`
  internals that newer `transformers` restructured. An unpinned "latest"
  install of both breaks one way (`AttributeError: 'CLIPTextModel' object
  has no attribute 'text_model'`); pinning only `transformers` older breaks
  the other way (`diffusers` importing a `transformers` symbol that doesn't
  exist yet). Pinned to a matching contemporary pair,
  `diffusers==0.31.0` + `transformers==4.46.3`, in
  [`colab_image_to_video.py`](backend/app/generators/colab_image_to_video.py).
- `I2VGenXLPipeline`'s own defaults are `height=704, width=1280` — with
  `num_frames` folded into the batch dim for the temporal transformer, that
  blows past a T4's 16GB VRAM (`CUDA out of memory` mid-forward, inside the
  `transformer_in` feed-forward block) even with `enable_model_cpu_offload()`
  on, since offload only moves idle submodules off-GPU, not activations.
  Confirmed against a real session; the overshoot was modest (~3.4GiB
  against a ~14.5GiB budget). Added `enable_vae_slicing()` /
  `enable_attention_slicing()` for headroom, plus capping resolution.
  An initial fix capped all the way to `height=320, width=576` to be safe,
  but that's ~5x fewer pixels than native and pushed the model far enough
  outside its trained scale to cause visible morphing/warping artifacts in
  the output (confirmed against a real generation) — this model degrades
  noticeably away from its native resolution. Settled on `height=512,
  width=896` (~2x native's overshoot margin, ~2.4x more pixels than the
  first attempt) as a better balance, in
  [`colab_image_to_video_template.py`](backend/app/generators/colab_image_to_video_template.py).
  If OOM resurfaces at this size, step down gradually rather than jumping
  back to a very small resolution; if warping persists even without OOM,
  it may be closer to this deprecated model's inherent quality ceiling.

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
