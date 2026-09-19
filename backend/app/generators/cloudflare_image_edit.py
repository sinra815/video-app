"""Image + text prompt -> edited image via Cloudflare Workers AI (free tier).

Cloudflare Workers AI's free plan gives 10,000 "neurons"/day at no cost and
no card required. Being open-weight (unlike Magic Hour or Gemini's closed
models), it also has much lighter built-in refusal behavior for ordinary
photo edits (outfit/background/style changes) - see README for account
setup.

Two prior model choices were tried and ruled out against a real deployed
account, in order:
- `@cf/runwayml/stable-diffusion-v1-5-img2img`: 403 `{"code": 5018,
  "message": "This account is not allowed to access ..."}` - pulled from
  general availability (its docs page 404s now).
- `@cf/stabilityai/stable-diffusion-xl-base-1.0`: 400 `{"code": 3030,
  "message": "input tensor `image` is not present in the model"}` for any
  image field name - Cloudflare's own docs claim img2img support here but
  the deployed model doesn't actually have an image input tensor at all
  (confirmed against cloudflare/cloudflare-docs#11835, a still-open
  upstream doc bug).

`@cf/black-forest-labs/flux-2-dev` is the one Workers AI model that
actually supports reference-image editing:
- REST call is **multipart/form-data**, not JSON: `POST
  https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/@cf/black-forest-labs/flux-2-dev`
  with fields `prompt` (text) and `input_image_0` (the source image file).
- Reference images must be resized to fit within 512x512 (aspect ratio
  preserved) or the model rejects them - handled here with Pillow.
- The prompt can refer to the input by index ("image 0"); this always
  sends exactly one reference image, so the prompt is prefixed to say so
  explicitly rather than relying on the model to infer it.
- The response is either the raw image bytes (Content-Type: image/*) or a
  JSON envelope {"result": {"image": <base64>}, "success": true} - as with
  the other providers here, both are handled since Cloudflare's docs are
  inconsistent about which.
"""
import base64
import io
import json
import mimetypes
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

from PIL import Image

from .. import config, translate
from .base import ProgressCallback, VideoGenerator

_MODEL = "@cf/black-forest-labs/flux-2-dev"
_TIMEOUT_SECONDS = 120
_MAX_DIMENSION = 512
# FLUX.2 [dev] is popular enough that Cloudflare's free-tier capacity for it
# is often exhausted (429 {"code": 3040, "message": "Capacity temporarily
# exceeded, please try again"}), confirmed intermittent against a real
# account - retrying with backoff usually clears it. This budget was
# widened to 8 retries (9 attempts, ~4.6min) once to ride out longer
# capacity dips, but two separate real jobs both had the whole backend
# process restart out from under them somewhere in that ~4.6min window
# (job vanished with 404 mid-retry, and - worse - wiped every other job's
# state too, since Render's free-tier disk doesn't survive a restart
# either, confirmed empirically). A third real job with the original
# shorter budget (4 attempts, ~50s) failed cleanly instead (no crash).
# Correlation isn't proof, but holding a thread + memory for minutes on a
# 512MB free instance is exactly the kind of thing that would cause an
# OOM restart, and a clean "failed" beats silently losing every job's
# history - narrowed back down.
_CAPACITY_ERROR_CODE = 3040
_RETRY_DELAYS_SECONDS = (5, 15, 30)

# FLUX.2 [dev]'s content filter sometimes refuses ordinary, non-explicit
# edits (outfit/background/style changes) with a generic "please choose
# another prompt" message - it appears to key off exact wording rather than
# an actual policy violation, since a semantically identical prompt reworded
# differently sometimes then passes. Retried with a paraphrase (round-trip
# translated through another language and back, see translate.paraphrase)
# instead of the unchanged original on this specific error - unlike the
# capacity-error retry above, resending the same prompt here would just get
# refused the same way every time.
_CONTENT_REFUSAL_MARKER = "choose another prompt"
_PARAPHRASE_VIA_LANGS = ("ko", "ja", "fr")


class CloudflareError(RuntimeError):
    pass


def _resize_for_upload(image_path: Path) -> bytes:
    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


def _build_multipart(fields: dict, file_field: str, filename: str, file_bytes: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
    parts.append(
        (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode("utf-8")
        + file_bytes
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(
        p if isinstance(p, bytes) else p.encode("utf-8") for p in parts
    )
    return body, boundary


def _run(prompt: str, image_bytes: bytes) -> tuple[str, bytes]:
    if not config.CLOUDFLARE_ACCOUNT_ID or not config.CLOUDFLARE_API_TOKEN:
        raise CloudflareError(
            "CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN are not configured. "
            "Create a free account at https://dash.cloudflare.com and set both "
            "as backend env vars."
        )
    body, boundary = _build_multipart({"prompt": prompt}, "input_image_0", "image.png", image_bytes)
    url = (
        f"https://api.cloudflare.com/client/v4/accounts/"
        f"{config.CLOUDFLARE_ACCOUNT_ID}/ai/run/{_MODEL}"
    )
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {config.CLOUDFLARE_API_TOKEN}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
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
    """Uses Cloudflare Workers AI's hosted FLUX.2 [dev] model (see module docstring)."""

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_path = Path(params["image_path"])

        on_progress("resizing source image")
        image_bytes = _resize_for_upload(image_path)

        base_prompt = params["prompt"]
        prompt = f"Using image 0 as the source photo, {base_prompt}"
        capacity_retries_left = len(_RETRY_DELAYS_SECONDS)
        paraphrase_attempts_left = len(_PARAPHRASE_VIA_LANGS)
        attempt = 0
        while True:
            attempt += 1
            on_progress(
                "submitting job to Cloudflare Workers AI"
                if attempt == 1
                else f"retrying Cloudflare Workers AI (attempt {attempt})"
            )
            try:
                content_type, raw = _run(prompt, image_bytes)
                break
            except CloudflareError as exc:
                message = str(exc)
                if f'"code":{_CAPACITY_ERROR_CODE}' in message and capacity_retries_left:
                    delay = _RETRY_DELAYS_SECONDS[len(_RETRY_DELAYS_SECONDS) - capacity_retries_left]
                    capacity_retries_left -= 1
                    time.sleep(delay)
                    continue
                if _CONTENT_REFUSAL_MARKER in message.lower() and paraphrase_attempts_left:
                    via_lang = _PARAPHRASE_VIA_LANGS[len(_PARAPHRASE_VIA_LANGS) - paraphrase_attempts_left]
                    paraphrase_attempts_left -= 1
                    on_progress(f"prompt was refused, rewording and retrying ({via_lang})")
                    base_prompt = translate.paraphrase(base_prompt, via_lang)
                    prompt = f"Using image 0 as the source photo, {base_prompt}"
                    continue
                raise

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
