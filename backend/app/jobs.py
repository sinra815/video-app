import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from . import config, email_notify
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


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)

    def create(self, mode: JobMode, params: dict, notify_email: str | None = None) -> Job:
        job = Job(mode=mode, notify_email=notify_email)
        with self._lock:
            self._jobs[job.id] = job
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

        job = self.get(job_id)
        if job.notify_email:
            try:
                email_notify.send_job_notification(job, job.notify_email)
            except Exception:  # noqa: BLE001 - a notification failure shouldn't affect the job itself
                traceback.print_exc()


job_store = JobStore()
