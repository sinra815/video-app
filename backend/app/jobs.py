import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from . import config
from .generators.cloudflare_image_edit import CloudflareImageEditGenerator
from .generators.colab_ai import ColabAiGenerator
from .generators.fal_image_edit import FalImageEditGenerator
from .generators.fal_image_to_video import FalImageToVideoGenerator
from .generators.magic_hour_image_edit import MagicHourImageEditGenerator
from .generators.magic_hour_image_to_video import MagicHourImageToVideoGenerator
from .generators.slideshow import SlideshowGenerator
from .models import Job, JobMode, JobStatus

_GENERATORS = {
    JobMode.SLIDESHOW: SlideshowGenerator(),
    JobMode.AI_TEXT_TO_VIDEO: ColabAiGenerator(),
}

# AI_IMAGE_TO_VIDEO and AI_IMAGE_EDIT each have multiple interchangeable
# providers (see main.py's _IMAGE_TO_VIDEO_PROVIDERS /
# _IMAGE_EDIT_PROVIDERS), selected per-job via params["provider"] rather
# than a single fixed generator like the other modes above.
_IMAGE_TO_VIDEO_GENERATORS = {
    "magic_hour": MagicHourImageToVideoGenerator(),
    "fal": FalImageToVideoGenerator(),
}

_IMAGE_EDIT_GENERATORS = {
    "magic_hour": MagicHourImageEditGenerator(),
    "fal": FalImageEditGenerator(),
    "cloudflare": CloudflareImageEditGenerator(),
}

# File extension for each job mode's output, since providers return
# different media types (video vs. still image).
_OUTPUT_EXTENSIONS = {
    JobMode.AI_IMAGE_EDIT: ".png",
}

# Job records used to live only in this process's memory - a free-tier
# container restart (e.g. an OOM kill during a long Cloudflare FLUX.2 retry
# loop, confirmed against a real job that vanished with 404 mid-retry)
# wiped every job silently, with the frontend left polling a 404 forever
# (see JobStatus.jsx). Persisting to a file survives a same-container
# restart (though not a fresh deploy - Render's free-tier disk isn't
# preserved across those either, per the README's storage caveat).
_JOBS_FILE = config.STORAGE_DIR / "jobs.json"


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._load()

    def _load(self) -> None:
        if not _JOBS_FILE.exists():
            return
        try:
            raw = json.loads(_JOBS_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        for entry in raw:
            job = Job(**entry)
            if job.status in (JobStatus.QUEUED, JobStatus.RUNNING):
                # No generator thread survives a process restart, so a job
                # left in-flight here can never finish on its own - mark it
                # failed instead of leaving it stuck for the frontend to
                # poll forever.
                job.status = JobStatus.FAILED
                job.progress = "failed"
                job.error = "서버가 재시작되어 작업이 중단되었습니다. 다시 시도해주세요."
            self._jobs[job.id] = job

    def _save(self) -> None:
        data = [job.model_dump() for job in self._jobs.values()]
        _JOBS_FILE.write_text(json.dumps(data), encoding="utf-8")

    def create(self, mode: JobMode, params: dict) -> Job:
        job = Job(mode=mode)
        with self._lock:
            self._jobs[job.id] = job
            self._save()
        self._executor.submit(self._run, job.id, params)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list_all(self) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = time.time()
            self._save()

    def _run(self, job_id: str, params: dict) -> None:
        self._update(job_id, status=JobStatus.RUNNING, progress="starting")
        job = self.get(job_id)
        mode = JobMode(job.mode)
        output_path = config.OUTPUTS_DIR / f"{job_id}{_OUTPUT_EXTENSIONS.get(mode, '.mp4')}"
        if mode == JobMode.AI_IMAGE_TO_VIDEO:
            generator = _IMAGE_TO_VIDEO_GENERATORS[params["provider"]]
        elif mode == JobMode.AI_IMAGE_EDIT:
            generator = _IMAGE_EDIT_GENERATORS[params["provider"]]
        else:
            generator = _GENERATORS[mode]

        def on_progress(message: str) -> None:
            self._update(job_id, progress=message)

        try:
            generator.generate(params, output_path, on_progress)
            self._update(job_id, status=JobStatus.DONE, progress="done", output_path=str(output_path))
        except Exception as exc:  # noqa: BLE001 - surface any failure to the job status
            traceback.print_exc()
            self._update(job_id, status=JobStatus.FAILED, progress="failed", error=str(exc))


job_store = JobStore()
