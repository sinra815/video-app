"""Image + text prompt -> edited image via the fal.ai hosted API.

Same account/credits and upload flow as fal_image_to_video.py, but hits
FLUX.1 Kontext [dev] (`fal-ai/flux-kontext/dev`) instead of LTX-Video:
- Submit: POST https://queue.fal.run/fal-ai/flux-kontext/dev with
  {"image_url", "prompt"} -> {"status_url", "response_url"}.
- Poll status_url until status == "COMPLETED", then GET response_url ->
  {"images": [{"url": ...}], ...} (an image edit result, not a video).

Reference: https://fal.ai/models/fal-ai/flux-kontext/dev/api
"""
import time
import urllib.request
from pathlib import Path

from .base import ProgressCallback, VideoGenerator
from .fal_image_to_video import FalError, _request, _upload_image

_QUEUE_URL = "https://queue.fal.run/fal-ai/flux-kontext/dev"
_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 300


class FalImageEditGenerator(VideoGenerator):
    """Uses fal.ai's hosted FLUX Kontext [dev] queue API (see module docstring)."""

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_path = Path(params["image_path"])

        on_progress("uploading source image")
        image_url = _upload_image(image_path)

        on_progress("submitting job to fal.ai")
        body = {"image_url": image_url, "prompt": params["prompt"]}
        submitted = _request("POST", _QUEUE_URL, body)
        status_url = submitted["status_url"]
        response_url = submitted["response_url"]

        on_progress("editing on fal.ai")
        deadline = time.time() + _POLL_TIMEOUT_SECONDS
        while time.time() < deadline:
            status = _request("GET", status_url)
            state = status.get("status")
            if state == "COMPLETED":
                break
            if state not in ("IN_QUEUE", "IN_PROGRESS"):
                raise FalError(f"fal.ai job ended with unexpected status {state}: {status}")
            time.sleep(_POLL_INTERVAL_SECONDS)
        else:
            raise FalError(f"fal.ai job did not finish within {_POLL_TIMEOUT_SECONDS}s")

        on_progress("downloading result")
        result = _request("GET", response_url)
        try:
            download_url = result["images"][0]["url"]
        except (KeyError, IndexError, TypeError) as exc:
            raise FalError(f"fal.ai result has no images[0].url: {result}") from exc
        req = urllib.request.Request(download_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            output_path.write_bytes(resp.read())

        on_progress("done")
