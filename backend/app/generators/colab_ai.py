import tempfile
import uuid
from pathlib import Path

from .. import colab_client, config
from .base import ProgressCallback, VideoGenerator

_TEMPLATE_PATH = Path(__file__).parent / "colab_ai_template.py"


class ColabAiGenerator(VideoGenerator):
    """Text-to-video generation offloaded to a Google Colab GPU runtime.

    Uses google-colab-cli's documented commands (`colab new/install/exec/
    download/stop`). google-colab-cli only runs on Linux/macOS with an
    authenticated Google/Colab account; on any other platform (or without
    auth) this raises colab_client.ColabUnavailableError, which the job
    runner surfaces as a normal failed-job message.
    """

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        if not colab_client.is_available():
            raise colab_client.ColabUnavailableError(
                "AI 텍스트-투-비디오 생성은 google-colab-cli(Linux/macOS 전용)가 "
                "설치 및 인증되어 있어야 합니다. 백엔드 README의 Colab 연동 섹션을 참고하세요."
            )

        fps = int(params.get("fps", 8))
        duration = float(params.get("duration_seconds", 4.0))
        num_frames = max(1, int(duration * fps))

        script = _TEMPLATE_PATH.read_text(encoding="utf-8").format(
            prompt=params["prompt"],
            negative_prompt=params.get("negative_prompt") or "",
            num_frames=num_frames,
            fps=fps,
        )
        local_script = Path(tempfile.gettempdir()) / f"colab_job_{uuid.uuid4().hex}.py"
        local_script.write_text(script, encoding="utf-8")

        session_name = f"{config.COLAB_SESSION_PREFIX}-{uuid.uuid4().hex[:8]}"
        session = colab_client.ColabSession(session_name, gpu=params.get("gpu", config.COLAB_DEFAULT_GPU))
        try:
            on_progress("provisioning Colab GPU runtime")
            session.start(on_progress)

            on_progress("installing model dependencies")
            session.install(["diffusers", "transformers", "accelerate"], on_progress)

            on_progress("running text-to-video generation on GPU")
            session.exec_file(local_script, on_progress, success_marker="VIDEO_READY")

            on_progress("downloading generated video")
            session.download("/content/output.mp4", output_path, on_progress)
        finally:
            on_progress("tearing down Colab runtime")
            session.stop(on_progress)
            local_script.unlink(missing_ok=True)

        on_progress("done")
