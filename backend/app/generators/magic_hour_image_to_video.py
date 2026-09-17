"""Image + text prompt -> short video via the Magic Hour hosted API.

Magic Hour (magichour.ai) is a third-party API aggregator that proxies
several hosted video models (Kling, LTX, etc.) behind one API. Used here
instead of self-hosting: every open image-to-video model tried so far
(I2VGenXL, LTX-Video, CogVideoX) uses an ~11B-parameter T5-XXL text encoder
that has to be re-downloaded (tens of GB) on every Colab job, since each job
runs on a fresh ephemeral VM with no persistent cache - that repeatedly
timed out in practice even after raising timeouts and fixing HF auth. A
hosted API has no such per-job download.

No `model` or `resolution` is requested explicitly - Magic Hour defaults
both to whatever the account's plan allows (a cheaper/free-tier model and
480p on a free account, better ones on a paid account), so this generator
behaves correctly either way without hardcoding a plan-specific choice.
"""
import json
import mimetypes
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from .. import config
from .base import ProgressCallback, VideoGenerator

_API_BASE = "https://api.magichour.ai/v1"
_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 600


class MagicHourError(RuntimeError):
    pass


def _request(method: str, path: str, body: Optional[dict] = None) -> dict:
    if not config.MAGIC_HOUR_API_KEY:
        raise MagicHourError(
            "MAGIC_HOUR_API_KEY is not configured. Get a free key at "
            "https://magichour.ai/developer and set it as a backend env var."
        )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        f"{_API_BASE}{path}",
        data=data,
        method=method,
        headers={
            "authorization": f"Bearer {config.MAGIC_HOUR_API_KEY}",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise MagicHourError(f"Magic Hour API {method} {path} failed ({exc.code}): {detail}") from exc


def _upload_image(image_path: Path) -> str:
    ext = image_path.suffix.lstrip(".").lower() or "jpg"
    result = _request("POST", "/files/upload-urls", {"items": [{"extension": ext, "type": "image"}]})
    item = result["items"][0]

    upload_req = urllib.request.Request(
        item["upload_url"],
        data=image_path.read_bytes(),
        method="PUT",
        headers={"content-type": mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"},
    )
    with urllib.request.urlopen(upload_req, timeout=120):
        pass

    return item["file_path"]


def get_account() -> dict:
    """Current credit balance and subscription details (GET /v1/account)."""
    return _request("GET", "/account")


def _extract_download_url(project: dict) -> str:
    downloads = project.get("downloads") or []
    if not downloads:
        raise MagicHourError(f"Magic Hour project has no downloads: {project}")
    first = downloads[0]
    return first["url"] if isinstance(first, dict) else first


class MagicHourImageToVideoGenerator(VideoGenerator):
    """Uses Magic Hour's hosted /image-to-video API (see module docstring)."""

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_path = Path(params["image_path"])

        on_progress("uploading source image")
        file_path = _upload_image(image_path)

        on_progress("submitting job to Magic Hour")
        body = {
            "end_seconds": float(params.get("duration_seconds", 5.0)),
            "style": {"prompt": params["prompt"]},
            "assets": {"image_file_path": file_path},
        }
        created = _request("POST", "/image-to-video", body)
        project_id = created["id"]

        on_progress("rendering on Magic Hour")
        deadline = time.time() + _POLL_TIMEOUT_SECONDS
        project = None
        while time.time() < deadline:
            project = _request("GET", f"/video-projects/{project_id}")
            status = project.get("status")
            if status == "complete":
                break
            if status in ("error", "canceled"):
                raise MagicHourError(f"Magic Hour job {status}: {project}")
            time.sleep(_POLL_INTERVAL_SECONDS)
        else:
            raise MagicHourError(f"Magic Hour job did not finish within {_POLL_TIMEOUT_SECONDS}s")

        on_progress("downloading result")
        download_url = _extract_download_url(project)
        req = urllib.request.Request(download_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            output_path.write_bytes(resp.read())

        on_progress("done")
