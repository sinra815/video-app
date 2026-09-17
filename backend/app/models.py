import time
import uuid
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class JobMode(str, Enum):
    SLIDESHOW = "slideshow"
    AI_TEXT_TO_VIDEO = "ai_text_to_video"
    AI_IMAGE_TO_VIDEO = "ai_image_to_video"


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class SlideshowParams(BaseModel):
    image_paths: list[str]
    audio_path: Optional[str] = None
    seconds_per_image: float = 3.0
    transition_seconds: float = 0.8
    resolution: str = "1280x720"
    fps: int = 30


class AiTextToVideoParams(BaseModel):
    prompt: str
    negative_prompt: Optional[str] = None
    duration_seconds: float = 4.0
    fps: int = 8
    resolution: str = "512x512"
    gpu: str = "T4"


class AiImageToVideoParams(BaseModel):
    image_path: str
    prompt: str
    negative_prompt: Optional[str] = None
    duration_seconds: float = 5.0


class Job(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    mode: JobMode
    status: JobStatus = JobStatus.QUEUED
    progress: str = "queued"
    error: Optional[str] = None
    output_path: Optional[str] = None
    notify_email: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    class Config:
        use_enum_values = True
