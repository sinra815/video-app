import os
from pathlib import Path

BASE_DIR = Path(__file__).absolute().parent.parent
STORAGE_DIR = BASE_DIR / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
OUTPUTS_DIR = STORAGE_DIR / "outputs"

for d in (UPLOADS_DIR, OUTPUTS_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Name of the `colab` executable on PATH (google-colab-cli). Only used by the
# AI text-to-video generator, and only on Linux/macOS where the CLI runs.
COLAB_BIN = os.environ.get("COLAB_BIN", "colab")
COLAB_SESSION_PREFIX = "videoapp"
COLAB_DEFAULT_GPU = os.environ.get("COLAB_GPU", "T4")
# 'oauth2' reads ~/.config/colab-cli/token.json (see colab_auth setup in README);
# the CLI's own default is 'adc', which we don't use.
COLAB_AUTH = os.environ.get("COLAB_AUTH", "oauth2")

# Comma-separated list of additional allowed CORS origins, e.g. the deployed
# frontend's URL (https://my-app.onrender.com). Localhost dev origins are
# always allowed on top of this.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")

# Magic Hour (magichour.ai) API key, used for image-to-video generation via
# their hosted API instead of self-hosting. Every open image-to-video model
# tried (I2VGenXL, LTX-Video, CogVideoX) uses an ~11B-parameter T5-XXL text
# encoder that has to be re-downloaded (tens of GB) on every ephemeral Colab
# job, and repeatedly timed out in practice even after raising timeouts and
# fixing HF auth. Get a free key (trial credits, no card required) at
# https://magichour.ai/developer.
MAGIC_HOUR_API_KEY = os.environ.get("MAGIC_HOUR_API_KEY", "")

# Hugging Face access token (read-only scope is enough). No longer used by
# image-to-video (see MAGIC_HOUR_API_KEY above) but still relevant if the
# text-to-video Colab path (colab_ai.py) ever needs the same fix.
HF_TOKEN = os.environ.get("HF_TOKEN", "")

# Cloudflare Workers AI, used as an image-edit provider. Unlike Magic Hour's
# AI Image Editor (requires a paid plan), Workers AI's free plan includes
# 10,000 "neurons"/day at no cost and no card required, running an
# open-weight Stable Diffusion model that also has much lighter built-in
# refusal behavior than closed
# models for ordinary edits. Get both values from the Cloudflare dashboard:
# CLOUDFLARE_ACCOUNT_ID from the Workers & Pages overview page, and
# CLOUDFLARE_API_TOKEN from My Profile > API Tokens (needs the
# "Workers AI - Read" and "Workers AI - Edit" account permissions).
CLOUDFLARE_ACCOUNT_ID = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "")
CLOUDFLARE_API_TOKEN = os.environ.get("CLOUDFLARE_API_TOKEN", "")

# Optional job-completion email notifications, sent via a plain SMTP relay
# (works with Gmail - smtp.gmail.com:587 with an App Password - or any other
# SMTP provider). Notifications are skipped entirely when SMTP_HOST is unset.
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "") or SMTP_USER

# This backend's own public URL (e.g. https://video-app-backend-idmf.onrender.com,
# no trailing slash), used to build a download link in completion emails when
# the generated file is too large to attach directly.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")

# Default address for job-completion notifications, pre-filled (and
# editable) in every generation form.
DEFAULT_NOTIFY_EMAIL = os.environ.get("DEFAULT_NOTIFY_EMAIL", "sinra815@gmail.com")
