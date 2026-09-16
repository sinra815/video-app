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

# Comma-separated list of additional allowed CORS origins, e.g. the deployed
# frontend's URL (https://my-app.onrender.com). Localhost dev origins are
# always allowed on top of this.
ALLOWED_ORIGINS = os.environ.get("ALLOWED_ORIGINS", "")
