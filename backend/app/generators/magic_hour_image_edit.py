"""Image + text prompt -> edited image via the Magic Hour hosted API.

Same account/credits and upload flow as magic_hour_image_to_video.py, but
hits the AI Image Editor endpoints instead of the video ones:
- POST /v1/ai-image-editor with {"assets": {"image_file_path": ...},
  "style": {"prompt": ...}} -> {"id", "credits_charged"}
- GET /v1/image-projects/{id} (not video-projects) to poll, same status
  values and "downloads" shape as the video endpoint.
"""
import time
import urllib.request
from pathlib import Path

from .base import ProgressCallback, VideoGenerator
from .magic_hour_image_to_video import MagicHourError, _extract_download_url, _request, _upload_image

_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 300


class MagicHourImageEditGenerator(VideoGenerator):
    """Uses Magic Hour's hosted /ai-image-editor API (see module docstring)."""

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_path = Path(params["image_path"])

        on_progress("uploading source image")
        file_path = _upload_image(image_path)

        on_progress("submitting job to Magic Hour")
        body = {
            "style": {"prompt": params["prompt"]},
            "assets": {"image_file_path": file_path},
        }
        created = _request("POST", "/ai-image-editor", body)
        project_id = created["id"]

        on_progress("editing on Magic Hour")
        deadline = time.time() + _POLL_TIMEOUT_SECONDS
        project = None
        while time.time() < deadline:
            project = _request("GET", f"/image-projects/{project_id}")
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
