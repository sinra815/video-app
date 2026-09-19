import ipaddress
import mimetypes
import socket
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import colab_client, config, email_notify, translate
from .generators import magic_hour_image_to_video
from .generators.magic_hour_image_to_video import MagicHourError
from .jobs import job_store
from .models import (
    AiImageEditParams,
    AiImageToVideoParams,
    AiTextToVideoParams,
    Job,
    JobMode,
)

app = FastAPI(title="컨텐츠 생성기")

_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_extra_origins = [o.strip() for o in config.ALLOWED_ORIGINS.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_default_origins + _extra_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "colab_cli_available": colab_client.is_available(),
        "magic_hour_configured": bool(config.MAGIC_HOUR_API_KEY),
        "email_notifications_configured": email_notify.is_configured(),
        "default_notify_email": config.DEFAULT_NOTIFY_EMAIL,
    }


# Hosted providers, keyed by the id the frontend sends back in
# AiImageToVideoJobRequest.provider / AiImageEditJobRequest.provider (and
# jobs.py dispatches on). Image-to-video and image-edit are listed
# separately because a provider that only does one (e.g. Cloudflare Workers
# AI only edits stills) must not be offered - and accepted - for the other.
# Add an entry to the relevant catalog plus a matching generator in jobs.py's
# _IMAGE_TO_VIDEO_GENERATORS / _IMAGE_EDIT_GENERATORS to wire up another
# provider.
_IMAGE_TO_VIDEO_PROVIDERS = {"magic_hour": "Magic Hour"}
_IMAGE_EDIT_PROVIDERS = {
    "magic_hour": "Magic Hour",
    "cloudflare": "Cloudflare Workers AI",
}


def _provider_entry(provider_id: str, label: str, mode: str) -> dict:
    entry = {"id": provider_id, "label": label, "configured": False, "credits": None, "error": None}
    if provider_id == "magic_hour" and mode == "edit":
        # Confirmed against a real job: Magic Hour's /ai-image-editor 402s
        # with plan_upgrade_required regardless of credit balance - a
        # trial/free-tier account can never use this endpoint, so there's
        # no balance worth checking here.
        entry["error"] = "이 계정 플랜에서는 이미지 편집이 지원되지 않습니다 (유료 플랜 필요)"
    elif provider_id == "magic_hour":
        entry["configured"] = bool(config.MAGIC_HOUR_API_KEY)
        if entry["configured"]:
            try:
                entry["credits"] = magic_hour_image_to_video.get_account().get("credits")
            except MagicHourError as exc:
                entry["error"] = str(exc)
    elif provider_id == "cloudflare":
        # Workers AI uses a daily neuron quota rather than a queryable
        # credit balance, so there's nothing to fetch here.
        entry["configured"] = bool(config.CLOUDFLARE_ACCOUNT_ID and config.CLOUDFLARE_API_TOKEN)

    entry["usable"] = bool(
        entry["configured"] and not entry["error"] and (entry["credits"] is None or entry["credits"] > 0)
    )
    return entry


def _provider_catalog(mode: str) -> dict:
    return _IMAGE_EDIT_PROVIDERS if mode == "edit" else _IMAGE_TO_VIDEO_PROVIDERS


@app.get("/api/providers")
def list_providers(mode: str = "video") -> list[dict]:
    return [_provider_entry(provider_id, label, mode) for provider_id, label in _provider_catalog(mode).items()]


@app.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = config.UPLOADS_DIR / stored_name
    with dest.open("wb") as f:
        f.write(await file.read())
    return {"file_id": stored_name, "path": str(dest)}


class AiJobRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    duration_seconds: float = 4.0
    fps: int = 8
    resolution: str = "512x512"
    gpu: str = "T4"
    notify_email: Optional[str] = None


class AiImageToVideoJobRequest(BaseModel):
    image_file_id: Optional[str] = None
    # Alternative to uploading a file: the server fetches the source image
    # itself. Useful when the client's network blocks outbound file uploads
    # but the job request (a small JSON body) still gets through.
    image_url: Optional[str] = None
    prompt: str
    negative_prompt: Optional[str] = None
    duration_seconds: float = 5.0
    provider: str = "magic_hour"
    notify_email: Optional[str] = None


class AiImageEditJobRequest(BaseModel):
    image_file_id: Optional[str] = None
    image_url: Optional[str] = None
    prompt: str
    provider: str = "magic_hour"
    notify_email: Optional[str] = None


def _resolve_upload(file_id: str) -> Path:
    path = config.UPLOADS_DIR / file_id
    if not path.exists():
        raise HTTPException(404, f"Unknown uploaded file: {file_id}")
    return path


MAX_IMAGE_URL_BYTES = 20 * 1024 * 1024


def _is_public_hostname(hostname: str) -> bool:
    """Reject hostnames that resolve to non-public addresses (SSRF guard).

    Blocks the server from being used to reach private networks, loopback,
    link-local, or cloud metadata endpoints (e.g. 169.254.169.254) via a
    user-supplied image_url.
    """
    try:
        infos = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False
    return all(
        not (ip := ipaddress.ip_address(info[4][0])).is_private
        and not ip.is_loopback
        and not ip.is_link_local
        and not ip.is_reserved
        and not ip.is_multicast
        and not ip.is_unspecified
        for info in infos
    )


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def _download_image_url(url: str) -> Path:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(400, "image_url must be http:// or https://")
    if not parsed.hostname or not _is_public_hostname(parsed.hostname):
        raise HTTPException(400, "image_url must point to a public address")

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "video-app/1.0"})
        with opener.open(req, timeout=20) as resp:
            content_type = resp.headers.get("Content-Type", "").split(";")[0].strip()
            data = resp.read(MAX_IMAGE_URL_BYTES + 1)
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        raise HTTPException(400, f"Failed to fetch image_url: {exc}")
    if len(data) > MAX_IMAGE_URL_BYTES:
        raise HTTPException(400, "image_url content exceeds 20MB limit")
    suffix = mimetypes.guess_extension(content_type) or ".jpg"
    dest = config.UPLOADS_DIR / f"{uuid.uuid4().hex}{suffix}"
    dest.write_bytes(data)
    return dest


@app.post("/api/jobs/ai", response_model=Job)
def create_ai_job(req: AiJobRequest) -> Job:
    data = req.model_dump(exclude={"notify_email"})
    data["prompt"] = translate.to_english(data["prompt"])
    if data.get("negative_prompt"):
        data["negative_prompt"] = translate.to_english(data["negative_prompt"])
    params = AiTextToVideoParams(**data)
    return job_store.create(JobMode.AI_TEXT_TO_VIDEO, params.model_dump(), notify_email=req.notify_email)


def _require_usable_provider(provider_id: str, mode: str) -> None:
    catalog = _provider_catalog(mode)
    if provider_id not in catalog:
        raise HTTPException(400, f"Unknown provider: {provider_id}")
    entry = _provider_entry(provider_id, catalog[provider_id], mode)
    if not entry["usable"]:
        raise HTTPException(400, entry["error"] or f"{catalog[provider_id]} is not currently usable")


@app.post("/api/jobs/ai-image-to-video", response_model=Job)
def create_ai_image_to_video_job(req: AiImageToVideoJobRequest) -> Job:
    _require_usable_provider(req.provider, "video")

    if req.image_file_id:
        image_path = _resolve_upload(req.image_file_id)
    elif req.image_url:
        image_path = _download_image_url(req.image_url)
    else:
        raise HTTPException(400, "image_file_id or image_url is required")

    params = AiImageToVideoParams(
        image_path=str(image_path),
        prompt=translate.to_english(req.prompt),
        negative_prompt=translate.to_english(req.negative_prompt) if req.negative_prompt else None,
        duration_seconds=req.duration_seconds,
        provider=req.provider,
    )
    return job_store.create(JobMode.AI_IMAGE_TO_VIDEO, params.model_dump(), notify_email=req.notify_email)


@app.post("/api/jobs/ai-image-edit", response_model=Job)
def create_ai_image_edit_job(req: AiImageEditJobRequest) -> Job:
    _require_usable_provider(req.provider, "edit")

    if req.image_file_id:
        image_path = _resolve_upload(req.image_file_id)
    elif req.image_url:
        image_path = _download_image_url(req.image_url)
    else:
        raise HTTPException(400, "image_file_id or image_url is required")

    params = AiImageEditParams(
        image_path=str(image_path),
        prompt=translate.to_english(req.prompt),
        provider=req.provider,
    )
    return job_store.create(JobMode.AI_IMAGE_EDIT, params.model_dump(), notify_email=req.notify_email)


@app.get("/api/jobs", response_model=list[Job])
def list_jobs() -> list[Job]:
    return job_store.list_all()


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs/{job_id}/download")
def download_job(job_id: str) -> FileResponse:
    job = job_store.get(job_id)
    if job is None:
        raise HTTPException(404, "Job not found")
    if not job.output_path:
        raise HTTPException(409, "Job has no output yet")
    if job.mode == JobMode.AI_IMAGE_EDIT:
        return FileResponse(job.output_path, media_type="image/png", filename=f"{job_id}.png")
    return FileResponse(job.output_path, media_type="video/mp4", filename=f"{job_id}.mp4")
