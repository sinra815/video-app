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

from . import colab_client, config
from .jobs import job_store
from .models import AiImageToVideoParams, AiTextToVideoParams, Job, JobMode, SlideshowParams

app = FastAPI(title="Video Generator")

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
        "hf_token_configured": bool(config.HF_TOKEN),
    }


@app.post("/api/uploads")
async def upload_file(file: UploadFile = File(...)) -> dict:
    suffix = Path(file.filename or "").suffix
    stored_name = f"{uuid.uuid4().hex}{suffix}"
    dest = config.UPLOADS_DIR / stored_name
    with dest.open("wb") as f:
        f.write(await file.read())
    return {"file_id": stored_name, "path": str(dest)}


class SlideshowJobRequest(BaseModel):
    image_file_ids: list[str]
    audio_file_id: Optional[str] = None
    seconds_per_image: float = 3.0
    transition_seconds: float = 0.8
    resolution: str = "1280x720"
    fps: int = 30
    notify_email: Optional[str] = None


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
    duration_seconds: float = 2.0
    fps: int = 8
    gpu: str = "T4"
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


@app.post("/api/jobs/slideshow", response_model=Job)
def create_slideshow_job(req: SlideshowJobRequest) -> Job:
    image_paths = [str(_resolve_upload(fid)) for fid in req.image_file_ids]
    audio_path = str(_resolve_upload(req.audio_file_id)) if req.audio_file_id else None
    params = SlideshowParams(
        image_paths=image_paths,
        audio_path=audio_path,
        seconds_per_image=req.seconds_per_image,
        transition_seconds=req.transition_seconds,
        resolution=req.resolution,
        fps=req.fps,
    )
    return job_store.create(JobMode.SLIDESHOW, params.model_dump(), notify_email=req.notify_email)


@app.post("/api/jobs/ai", response_model=Job)
def create_ai_job(req: AiJobRequest) -> Job:
    params = AiTextToVideoParams(**req.model_dump(exclude={"notify_email"}))
    return job_store.create(JobMode.AI_TEXT_TO_VIDEO, params.model_dump(), notify_email=req.notify_email)


@app.post("/api/jobs/ai-image-to-video", response_model=Job)
def create_ai_image_to_video_job(req: AiImageToVideoJobRequest) -> Job:
    if req.image_file_id:
        image_path = _resolve_upload(req.image_file_id)
    elif req.image_url:
        image_path = _download_image_url(req.image_url)
    else:
        raise HTTPException(400, "image_file_id or image_url is required")

    params = AiImageToVideoParams(
        image_path=str(image_path),
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        duration_seconds=req.duration_seconds,
        fps=req.fps,
        gpu=req.gpu,
    )
    return job_store.create(JobMode.AI_IMAGE_TO_VIDEO, params.model_dump(), notify_email=req.notify_email)


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
    return FileResponse(job.output_path, media_type="video/mp4", filename=f"{job_id}.mp4")
