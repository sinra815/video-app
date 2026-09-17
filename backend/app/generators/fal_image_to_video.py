"""Image + text prompt -> short video via the fal.ai hosted API.

fal.ai (fal.ai) is a third-party API platform that hosts many open video
models (LTX-Video, Kling, Hunyuan, etc.) behind one REST API with
predictable per-generation USD pricing, unlike Magic Hour's opaque credit
system. Uses the LTX-Video model (`fal-ai/ltx-video/image-to-video`):
cheap (~$0.02/generation), and self-hosting it on Colab was already ruled
out (see colab_image_to_video history) because of its large text encoder's
per-job re-download cost - a hosted API sidesteps that entirely.

Note: this endpoint produces a fixed-length (~5s) clip; `duration_seconds`
from the request is not configurable for this model and is ignored.

Reference (verified against the fal-ai/fal Python client source and fal's
own docs, not just a web summary, after Magic Hour's `type`/`type_` mixup):
- Auth: `Authorization: Key <FAL_API_KEY>`.
- Upload: POST https://rest.fal.ai/storage/upload/initiate?storage_type=gcs
  -> {"upload_url", "file_url"}, then PUT the bytes to upload_url.
- Submit: POST https://queue.fal.run/fal-ai/ltx-video/image-to-video with
  {"image_url", "prompt", "negative_prompt"?} (no "input" wrapper) ->
  {"request_id", "status_url", "response_url", "cancel_url"}.
- Poll status_url until status == "COMPLETED", then GET response_url ->
  {"video": {"url": ...}}.
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

_REST_BASE = "https://rest.fal.ai"
_QUEUE_URL = "https://queue.fal.run/fal-ai/ltx-video/image-to-video"
_POLL_INTERVAL_SECONDS = 5
_POLL_TIMEOUT_SECONDS = 600


class FalError(RuntimeError):
    pass


def _request(method: str, url: str, body: Optional[dict] = None) -> dict:
    if not config.FAL_API_KEY:
        raise FalError(
            "FAL_API_KEY is not configured. Get a free key at "
            "https://fal.ai/dashboard/keys and set it as a backend env var."
        )
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        method=method,
        headers={
            "authorization": f"Key {config.FAL_API_KEY}",
            "content-type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise FalError(f"fal.ai API {method} {url} failed ({exc.code}): {detail}") from exc


def get_credits() -> Optional[float]:
    """Best-effort credit balance (GET /v1/account/billing?expand=credits).

    The exact response shape wasn't independently confirmable (fal's docs
    domains are unreachable from this dev environment), so this parses
    defensively and returns None rather than raising on an unrecognized
    shape - the caller surfaces None as "확인 실패" rather than crashing.
    """
    data = _request("GET", f"{_REST_BASE}/v1/account/billing?expand=credits")
    credits = data.get("credits")
    if isinstance(credits, dict):
        for key in ("balance", "amount", "remaining", "value"):
            if key in credits:
                return credits[key]
        return None
    return credits


def _upload_image(image_path: Path) -> str:
    content_type = mimetypes.guess_type(str(image_path))[0] or "application/octet-stream"
    init = _request(
        "POST",
        f"{_REST_BASE}/storage/upload/initiate?storage_type=gcs",
        {"file_name": image_path.name, "content_type": content_type},
    )
    upload_url = init["upload_url"]
    file_url = init["file_url"]

    req = urllib.request.Request(
        upload_url,
        data=image_path.read_bytes(),
        method="PUT",
        headers={"content-type": content_type},
    )
    with urllib.request.urlopen(req, timeout=120):
        pass

    return file_url


class FalImageToVideoGenerator(VideoGenerator):
    """Uses fal.ai's hosted LTX-Video queue API (see module docstring)."""

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_path = Path(params["image_path"])

        on_progress("uploading source image")
        image_url = _upload_image(image_path)

        on_progress("submitting job to fal.ai")
        body = {"image_url": image_url, "prompt": params["prompt"]}
        if params.get("negative_prompt"):
            body["negative_prompt"] = params["negative_prompt"]
        submitted = _request("POST", _QUEUE_URL, body)
        status_url = submitted["status_url"]
        response_url = submitted["response_url"]

        on_progress("rendering on fal.ai")
        deadline = time.time() + _POLL_TIMEOUT_SECONDS
        status = None
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
            download_url = result["video"]["url"]
        except (KeyError, TypeError) as exc:
            raise FalError(f"fal.ai result has no video.url: {result}") from exc
        req = urllib.request.Request(download_url)
        with urllib.request.urlopen(req, timeout=120) as resp:
            output_path.write_bytes(resp.read())

        on_progress("done")
