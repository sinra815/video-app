# 컨텐츠 생성기 (Content Generator)

A web app for AI-generating photos and videos three ways:

1. **AI text-to-video** — a text prompt is turned into a short video by
   provisioning a GPU runtime on Google Colab via
   [`google-colab-cli`](https://github.com/googlecolab/google-colab-cli),
   running a diffusers text-to-video pipeline there, and pulling the result
   back.
2. **AI image-to-video** — a photo + a text prompt (what motion/change to
   apply) generates a short video via the hosted [Magic
   Hour](https://magichour.ai) API (see [Image-to-video via Magic
   Hour](#image-to-video-via-magic-hour) below), not Colab. Also supports
   giving the image as a URL instead of uploading a file, since the server
   fetches it itself.
3. **AI image edit** — a photo + a text prompt (what to change) returns an
   edited still image instead of a video, via one of two providers picked
   in the "생성 API" selector: Magic Hour's `/ai-image-editor` (needs a paid
   plan - see caveat below), or [Cloudflare Workers AI](#image-edit-via-cloudflare-workers-ai-second-provider)
   (free, no card required - the default).

## Stack

- Backend: FastAPI (Python), background job queue via a thread pool
- Frontend: React + Vite

## PIN lock

The frontend shows a 4-digit PIN screen before the app itself — since this
is deployed publicly reachable (so it works from a phone anywhere) but only
meant for one person's use, and each generation spends real Magic Hour
credits. The PIN is client-side only (`frontend/src/pin.js`, stored in
`localStorage`), not a real auth system — good enough to stop a random
visitor with the URL, not a determined attacker. Default PIN is `2848`;
change it from the "비밀번호 변경" link in the app header (asks for the
current PIN, then a new 4-digit one).

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

The text-to-video form no longer offers a GPU choice - `colab new --gpu L4`
and `--gpu A100` both failed on a real job (`Backend rejected accelerator
'L4'. You may not have quota or entitlement for this accelerator on your
account`) since this Colab account's free tier only has T4 entitlement.
`AiForm.jsx` hardcodes `gpu: "T4"` instead of offering options that would
just fail.

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
## Image-to-video via Magic Hour

Image-to-video used to run on the same Colab lifecycle as text-to-video —
first `I2VGenXLPipeline` (2023, deprecated upstream), then
`LTXImageToVideoPipeline` ([Lightricks/LTX-Video](https://huggingface.co/Lightricks/LTX-Video)),
then `CogVideoXImageToVideoPipeline`. All three were abandoned after real
testing, for two different reasons:

- **I2VGenXL**: even after raising resolution to reclaim unused T4 headroom
  (512x896 → 576x1024, confirmed to run without OOM), a real generation
  showed severe temporal instability — a coherent first frame that visibly
  collapsed into gray noise by the last frame of a 16-frame clip. Not a
  resolution problem, so more pixels wouldn't have fixed it.
- **LTX-Video and CogVideoX**: both use an ~11B-parameter T5-XXL text
  encoder. Since each job is a fresh Colab VM with no persistent disk, the
  ~20GB of combined weights gets re-downloaded from the HF Hub on *every
  single job* — slow enough (even with an `HF_TOKEN` set, confirmed against
  a real run) to blow past the 1700s exec timeout before inference even
  starts. This is a structural mismatch between "huge model" and "no
  cross-job cache," not something fixable by tuning one job's script.

Image-to-video now calls the hosted [Magic Hour](https://magichour.ai) API
instead (`app/generators/magic_hour_image_to_video.py`) — no self-hosting,
no per-job download, no Colab GPU involved for this feature:

1. Upload the source image via `POST /v1/files/upload-urls` (get a
   presigned URL) then `PUT` the bytes to it.
2. `POST /v1/image-to-video` with the uploaded `file_path`, the prompt, and
   `end_seconds`. Neither `model` nor `resolution` is passed explicitly, so
   Magic Hour uses whatever the account's plan defaults to.
3. Poll `GET /v1/video-projects/{id}` until `status` is `complete` (or
   `error`/`canceled`), then download the result from `downloads[0]`.

Set `MAGIC_HOUR_API_KEY` as a backend env var — get a free key (trial
credits, no card required) at <https://magichour.ai/developer>. Those are
one-time signup credits, not a renewing daily allowance, so sustained use
eventually needs a paid plan. (Checked alternatives: Luma/Kling/Hailuo's
own developer APIs have no free tier at all; core.today advertises daily
free credits but its cheapest image-to-video model costs more than the
entire daily allowance, so it can't complete even one generation for free.)

Magic Hour's credits ran out mid-use in practice (a 5s clip cost more
credits than the trial balance had left) with no visibility until a job
failed, so `GET /api/providers?mode=video|edit` now reports each
provider's `configured`/`credits`/`error` state plus a computed `usable`
flag (`configured && !error && (credits is None or credits > 0)`), and the
"생성 API" selector disables any `<option>` where `usable` is false (shown
as "사용 불가" instead of a credit count) so a provider that's out of
credits, locked, or plan-gated can't be selected in the first place. The
backend re-checks `usable` on job submission too (`_require_usable_provider`
in `main.py`) so a stale/cached page can't slip a disabled provider through
- it gets a clean 400 instead of a raw provider error mid-job.

**AI Image Editor caveat**: unlike `/image-to-video`, Magic Hour's
`/ai-image-editor` endpoint is gated behind a paid plan even with trial
credits available - a real test job failed with `402 plan_upgrade_required`
("Please upgrade to creator, pro, or business to create an edit with this
model"). Not a bug in this app; Magic Hour just doesn't offer that specific
feature on the free/trial tier. Use the Cloudflare Workers AI provider for
image edit instead (see below).

## Image edit via Cloudflare Workers AI (second provider)

Added as a second image-edit provider (`app/generators/cloudflare_image_edit.py`)
after Magic Hour (needs a paid plan for `/ai-image-editor`, see above)
turned out not to be usable for free in practice. Cloudflare Workers AI's
free plan gives **10,000 "neurons"/day
at no cost, no card required**, running the open-weight Stable Diffusion
XL `img2img` model:

1. `POST https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/stabilityai/stable-diffusion-xl-base-1.0`
   with `{"image_b64": <base64 source image>, "prompt": ..., "strength": 0.7}`.
2. The response is either the raw image bytes (`Content-Type: image/*`) or a
   JSON envelope `{"result": {"image": <base64>}, "success": true}` —
   Cloudflare's own docs are inconsistent about which, so both are handled.

**Verification status**: `@cf/runwayml/stable-diffusion-v1-5-img2img` was
tried first (matches Cloudflare's own model-catalog wording most closely),
but a real call against a fresh account failed with `403 {"code": 5018,
"message": "This account is not allowed to access
@cf/runwayml/stable-diffusion-v1-5-img2img"}` — that model has been pulled
from general availability (its docs page 404s; only accounts grandfathered
in before the change can still reach it). Switched to
`stable-diffusion-xl-base-1.0`, which supports the same img2img
image/image_b64 + strength inputs and is still generally available.

No upload/poll/download round trip like the other two providers — this is a
single synchronous request.

Set both `CLOUDFLARE_ACCOUNT_ID` and `CLOUDFLARE_API_TOKEN` as backend env
vars:
- **Account ID**: [Cloudflare dashboard](https://dash.cloudflare.com) →
  Workers & Pages → Overview (right-hand sidebar).
- **API Token**: dashboard → My Profile → API Tokens → Create Token →
  Custom Token, with the **Account / Workers AI / Read** and
  **Account / Workers AI / Edit** permissions.

**Note on content restrictions**: this uses an open-weight model with much
lighter built-in refusal behavior than closed models (Magic Hour, Gemini)
for ordinary edits (outfit/background/style changes on a photo), since it
lacks their heavy safety fine-tuning. Cloudflare's own Acceptable Use
Policy still applies at the platform level (sexual, exploitative, or
otherwise prohibited content is not permitted regardless of provider) —
this only reduces false-positive refusals on legitimate edits, not the
underlying policy.

Even so, the model still occasionally refuses an ordinary edit with a
generic "please choose another prompt" message, seemingly keying off exact
wording rather than an actual policy violation — a semantically identical
prompt reworded differently sometimes then passes. On that specific error,
`cloudflare_image_edit.py` now retries with the prompt reworded via
round-trip translation (English → Korean/Japanese/French → English, using
the same free Google Translate endpoint as `translate.py`) instead of
resending the unchanged prompt, up to 3 times, separately from the
capacity-error retry above.

**Ruled out: Google Gemini (`gemini-3.1-flash-image`, "Nano Banana")**. Best
edit quality of anything tried (identity-preserving, closed model), and a
real request authenticated fine with a free API key - but every image
model returns `429 {"code": "too_many_requests", ...limit: 0...}` until the
Google Cloud project has a **billing account linked**, even to use the free
daily quota at all (a widely-reported Gemini API behavior, not a bug in
this app). Ruled out here specifically because it requires registering a
card - do not re-add this provider unless that changes.

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

## Email notifications on job completion

Every generation form (slideshow, AI text-to-video, image-to-video, image
edit) has an optional "완료 시 알림 받을 이메일" field, pre-filled with
`sinra815@gmail.com` (editable, and remembered per-browser via
`localStorage` after the first submit). When set, the backend emails that
address once the job reaches a terminal state (success or failure):

- On success, the generated file is attached directly — a video as `.mp4`,
  an AI image-edit result as `.png` — rather than linked, since Render's
  free tier has no persistent disk and a download link can 404 once the
  instance restarts before the recipient checks it. Only if the file is too
  large to attach (>20MB) does it fall back to a `PUBLIC_BASE_URL` link.
- On failure, the email includes the error message.
- A notification failure never affects the job itself — it's logged and
  swallowed (see `JobStore._run` in [`app/jobs.py`](backend/app/jobs.py)).

This needs an SMTP relay configured via env vars on the backend service (see
[`app/config.py`](backend/app/config.py) and
[`app/email_notify.py`](backend/app/email_notify.py)) — notifications are
silently skipped if `SMTP_HOST` isn't set, so this doesn't break deployments
that don't configure it:

- `SMTP_HOST`, `SMTP_PORT` (defaults to 587), `SMTP_USER`, `SMTP_PASSWORD`,
  `SMTP_FROM` (defaults to `SMTP_USER`).
- `PUBLIC_BASE_URL` — this backend's own public URL (e.g.
  `https://video-app-backend-idmf.onrender.com`, no trailing slash), only
  used for the oversized-file fallback link.
- `DEFAULT_NOTIFY_EMAIL` — only affects `GET /api/health`'s
  `default_notify_email` field; the actual pre-filled address in each form
  is hardcoded in the frontend (`sinra815@gmail.com`), not fetched from the
  backend.

Works with any SMTP provider. For Gmail: `SMTP_HOST=smtp.gmail.com`,
`SMTP_PORT=587`, `SMTP_USER` = your Gmail address, `SMTP_PASSWORD` = a
[Google App Password](https://myaccount.google.com/apppasswords) (a regular
account password won't work with 2FA enabled, which Google requires for App
Passwords anyway). Set these as Render environment variables on the backend
service (Environment tab) — same place as `ALLOWED_ORIGINS` — then redeploy.

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
  (not implemented here). This also means job history (`JobStore`, backed by
  `storage/jobs.json`) doesn't survive a crash-triggered restart either -
  confirmed against two real jobs that vanished (`GET /api/jobs` came back
  `[]` right after) when the backend process restarted mid-job. The write
  is still there since it's harmless and helps in any environment where the
  disk *does* survive, but don't rely on it here.
- **512MB RAM is tight** — a Cloudflare FLUX.2 image-edit job holding a
  background thread in a multi-minute retry-with-backoff loop (see
  `cloudflare_image_edit.py`) correlated with the whole process restarting
  mid-job twice in a row when the retry budget was widened to ~4.6 minutes;
  narrowing it back to ~50s (3 retries) stopped it. If job history keeps
  disappearing, suspect whatever generator is holding a thread longest.
  Since the backend retry budget alone still leaves real capacity dips
  unhandled, `JobStatus.jsx` now also retries client-side on **any** job
  failure, but as separate short-lived job submissions spread ~5s apart (up
  to 12 extra attempts) instead of one long-held backend request. A
  permanently-broken request (bad config, plan-gated provider, etc.) just
  fails the same way each of the 12 times and then stops - this trades a
  few wasted retries on non-transient errors for not needing to keep a
  by-error allowlist in sync. Also a manual "다시 시도" button on any failure
  that resubmits without re-uploading the photo (the server keeps the
  uploaded file, so a retry only needs the same
  `image_file_id`/prompt/provider).
- The free web service spins down after 15 minutes of inactivity — the first
  request after that takes 30-60s to wake it back up.
- The Colab OAuth token is stored as a Render Secret File, which — unlike
  local disk — *does* survive redeploys and restarts (see "How auth is wired
  up" above). If Colab jobs start failing with an auth error, the refresh
  token was likely revoked and needs regenerating.
- Colab's free tier has unpredictable GPU availability and rate limits meant
  for interactive notebook use, not a production backend — expect occasional
  `colab new` failures under real traffic. Colab Pro/Pro+ is more reliable for
  sustained automated use. (This only affects AI text-to-video — image-to-video
  uses Magic Hour, not Colab.)
- Magic Hour's free-tier credits are a one-time signup grant, not a daily
  allowance — once they run out, `ai-image-to-video` jobs will fail until the
  account is topped up or upgraded.

## Notes for Windows developers

- `google-colab-cli` genuinely doesn't work on Windows (Windows-only
  `import termios` crash at startup) — this is expected, not a bug in this
  app. Use WSL or a Linux/macOS box to actually exercise the AI path.
- If you hit `esbuild`-related `ENOENT` spawn errors from `npm`/`vite` in a
  sandboxed or virtualized filesystem environment, set `ESBUILD_BINARY_PATH`
  to the literal (non-virtualized) path of
  `node_modules/@esbuild/win32-x64/esbuild.exe` before running `npm install`
  or `vite build`. This isn't needed on a normal Windows install.
