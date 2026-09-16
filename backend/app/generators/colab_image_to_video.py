import base64
import tempfile
import uuid
from pathlib import Path

from .. import colab_client, config
from .base import ProgressCallback, VideoGenerator

_TEMPLATE_PATH = Path(__file__).parent / "colab_image_to_video_template.py"


class ColabImageToVideoGenerator(VideoGenerator):
    """Image + text prompt -> short video, offloaded to a Google Colab GPU runtime.

    Uses diffusers' I2VGenXL pipeline (ali-vilab/i2vgen-xl), the standard
    diffusers model that takes both an image and a text prompt. Same
    provisioning lifecycle as ColabAiGenerator.

    The source image is embedded as base64 directly in the generated script
    (decoded and written to disk by the script itself) rather than sent via
    `colab upload`: that command's Jupyter Contents API payload hardcodes
    `"chunk": 1` and never sends a finalizing chunk, leaving the remote file
    truncated/unreadable (confirmed against a real session — `colab upload`
    reports success but the file fails to open with "broken data stream").
    """

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        if not colab_client.is_available():
            raise colab_client.ColabUnavailableError(
                "사진 기반 AI 영상 생성은 google-colab-cli(Linux/macOS 전용)가 "
                "설치 및 인증되어 있어야 합니다. 백엔드 README의 Colab 연동 섹션을 참고하세요."
            )

        fps = int(params.get("fps", 8))
        duration = float(params.get("duration_seconds", 2.0))
        num_frames = max(1, int(duration * fps))

        image_b64 = base64.b64encode(Path(params["image_path"]).read_bytes()).decode("ascii")

        script = _TEMPLATE_PATH.read_text(encoding="utf-8").format(
            image_b64=image_b64,
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
            # I2VGenXLPipeline is deprecated in current diffusers and reaches
            # into CLIPTextModel's internals (`text_encoder.text_model...`);
            # an unpinned "latest" transformers restructured that and broke
            # it with `AttributeError: 'CLIPTextModel' object has no
            # attribute 'text_model'` (confirmed against a real session, past
            # the point where an unrelated image-loading bug was fixed). Pin
            # to a version from before that restructuring.
            session.install(["diffusers", "transformers==4.46.3", "accelerate"], on_progress)

            on_progress("running image-to-video generation on GPU")
            session.exec_file(local_script, on_progress, success_marker="VIDEO_READY")

            on_progress("downloading generated video")
            session.download("/content/output.mp4", output_path, on_progress)
        finally:
            on_progress("tearing down Colab runtime")
            session.stop(on_progress)
            local_script.unlink(missing_ok=True)

        on_progress("done")
