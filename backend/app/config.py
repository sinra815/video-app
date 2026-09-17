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
# the generated video is too large to attach directly.
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
