import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from threading import Lock

from . import config
from .generators.colab_ai import ColabAiGenerator
from .generators.slideshow import SlideshowGenerator
from .models import Job, JobMode, JobStatus

_GENERATORS = {
    JobMode.SLIDESHOW: SlideshowGenerator(),
    JobMode.AI_TEXT_TO_VIDEO: ColabAiGenerator(),
}


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = Lock()
        self._executor = ThreadPoolExecutor(max_workers=2)

    def create(self, mode: JobMode, params: dict) -> Job:
        job = Job(mode=mode)
        with self._lock:
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id, params)
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def _update(self, job_id: str, **fields) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in fields.items():
                setattr(job, key, value)
            job.updated_at = time.time()

    def _run(self, job_id: str, params: dict) -> None:
        self._update(job_id, status=JobStatus.RUNNING, progress="starting")
        job = self.get(job_id)
        output_path = config.OUTPUTS_DIR / f"{job_id}.mp4"
        generator = _GENERATORS[JobMode(job.mode)]

        def on_progress(message: str) -> None:
            self._update(job_id, progress=message)

        try:
            generator.generate(params, output_path, on_progress)
            self._update(job_id, status=JobStatus.DONE, progress="done", output_path=str(output_path))
        except Exception as exc:  # noqa: BLE001 - surface any failure to the job status
            traceback.print_exc()
            self._update(job_id, status=JobStatus.FAILED, progress="failed", error=str(exc))


job_store = JobStore()
