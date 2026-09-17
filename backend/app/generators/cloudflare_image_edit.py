"""Image + text prompt -> edited image via Cloudflare Workers AI (free tier).

Cloudflare Workers AI's free plan gives 10,000 "neurons"/day at no cost and
no card required, running the open-weight Stable Diffusion v1.5 img2img
model. Being open-weight (unlike Magic Hour or Gemini's closed models), it
also has much lighter built-in refusal behavior for ordinary photo edits
(outfit/background/style changes) - see README for account setup.

REST call: POST https://api.cloudflare.com/client/v4/accounts/{account_id}
/ai/run/@cf/runwayml/stable-diffusion-v1-5-img2img with
{"image_b64": <base64 source image>, "prompt": ...}. Cloudflare's docs are
inconsistent about whether the response is the raw image bytes
(Content-Type: image/*) or a JSON envelope {"result": {"image": <base64>},
"success": true}, so both are handled here.
"""
import base64
import json
import urllib.error
import urllib.request
from pathlib import Path

from .. import config
from .base import ProgressCallback, VideoGenerator

_MODEL = "@cf/runwayml/stable-diffusion-v1-5-img2img"
_TIMEOUT_SECONDS = 120


class CloudflareError(RuntimeError):
    pass


def _run(body: dict) -> tuple[str, bytes]:
    if not config.CLOUDFLARE_ACCOUNT_ID or not config.CLOUDFLARE_API_TOKEN:
        raise CloudflareError(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not configured. "
            "Create a free account at https://dash.cloudflare.com and set both "
            "as backend env vars."
        )
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/{_MODEL}"
    )
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        method="POST",
        headers={
            "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            content_type = resp.headers.get("Content-Type", "")
            return content_type, resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise CloudflareError(
            f"Cloudflare Workers AI request failed ({exc.code}): {detail}"
        ) from exc


class CloudflareImageEditGenerator(VideoGenerator):
    """Uses Cloudflare Workers AI's hosted SD v1.5 img2img model (see module docstring)."""

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_path = Path(params["image_path"])
        image_b64 = base64.b64encode(image_path.read_bytes()).decode("ascii")

        on_progress("submitting job to Cloudflare Workers AI")
        content_type, raw = _run({"image_b64": image_b64, "prompt": params["prompt"]})

        on_progress("saving result")
        if content_type.startswith("image/"):
            output_path.write_bytes(raw)
        else:
            try:
                payload = json.loads(raw)
                image_field = payload["result"]["image"]
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise CloudflareError(
                    f"Cloudflare Workers AI response has no image: {raw[:500]!r}"
                ) from exc
            output_path.write_bytes(base64.b64decode(image_field))

        on_progress("done")
