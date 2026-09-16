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
    return {"status": "ok", "colab_cli_available": colab_client.is_available()}


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


class AiJobRequest(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    duration_seconds: float = 4.0
    fps: int = 8
    resolution: str = "512x512"
    gpu: str = "T4"


class AiImageToVideoJobRequest(BaseModel):
    image_file_id: str
    prompt: str
    negative_prompt: Optional[str] = None
    duration_seconds: float = 2.0
    fps: int = 8
    gpu: str = "T4"


def _resolve_upload(file_id: str) -> Path:
    path = config.UPLOADS_DIR / file_id
    if not path.exists():
        raise HTTPException(404, f"Unknown uploaded file: {file_id}")
    return path


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
    return job_store.create(JobMode.SLIDESHOW, params.model_dump())


@app.post("/api/jobs/ai", response_model=Job)
def create_ai_job(req: AiJobRequest) -> Job:
    params = AiTextToVideoParams(**req.model_dump())
    return job_store.create(JobMode.AI_TEXT_TO_VIDEO, params.model_dump())


@app.post("/api/jobs/ai-image-to-video", response_model=Job)
def create_ai_image_to_video_job(req: AiImageToVideoJobRequest) -> Job:
    params = AiImageToVideoParams(
        image_path=str(_resolve_upload(req.image_file_id)),
        prompt=req.prompt,
        negative_prompt=req.negative_prompt,
        duration_seconds=req.duration_seconds,
        fps=req.fps,
        gpu=req.gpu,
    )
    return job_store.create(JobMode.AI_IMAGE_TO_VIDEO, params.model_dump())


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
