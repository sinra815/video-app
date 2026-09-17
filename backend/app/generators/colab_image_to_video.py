import base64
import tempfile
import uuid
from pathlib import Path

from .. import colab_client, config
from .base import ProgressCallback, VideoGenerator

_TEMPLATE_PATH = Path(__file__).parent / "colab_image_to_video_template.py"

# LTX-Video (Lightricks/LTX-Video, Apache-2.0) documents "under 720x1280" as
# its best-quality range; height/width must both be divisible by 32. T4's
# entry matches the ~10GB VRAM configuration documented for this pipeline
# (704x480, 161 frames, 50 steps); L4/A100 have enough headroom to go higher.
_GPU_PROFILES = {
    "T4": {"height": 480, "width": 704},
    "L4": {"height": 608, "width": 896},
    "A100": {"height": 704, "width": 1280},
}

# LTX-Video is conditioned on a target frame rate as part of its trained
# motion prior; the API's user-facing `fps` field was tuned for the old
# I2VGenXL model's much lower typical values (default 8) and would feed this
# model a frame rate far outside what it was trained on, so it's not used
# here - duration_seconds still controls output length.
_LTX_FRAME_RATE = 24


def _ltx_num_frames(duration_seconds: float) -> int:
    # LTX-Video's temporal VAE compresses by 8x, so num_frames must be of the
    # form 8k+1. Round the requested duration to the nearest valid count.
    target = max(1, round(duration_seconds * _LTX_FRAME_RATE))
    k = max(1, round((target - 1) / 8))
    return 8 * k + 1


class ColabImageToVideoGenerator(VideoGenerator):
    """Image + text prompt -> short video, offloaded to a Google Colab GPU runtime.

    Uses diffusers' LTX-Video pipeline (Lightricks/LTX-Video, Apache-2.0), a
    more recent (Nov 2024) and actively maintained model than the previously
    used I2VGenXL. I2VGenXL showed severe temporal instability in practice -
    a coherent first frame that visibly collapsed into gray noise by the
    last frame of a 16-frame clip (confirmed against a real generation) -
    which raising resolution alone didn't fix.

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

        gpu = params.get("gpu", config.COLAB_DEFAULT_GPU)
        profile = _GPU_PROFILES.get(gpu, _GPU_PROFILES["T4"])
        duration = float(params.get("duration_seconds", 2.0))
        num_frames = _ltx_num_frames(duration)

        image_b64 = base64.b64encode(Path(params["image_path"]).read_bytes()).decode("ascii")

        script = _TEMPLATE_PATH.read_text(encoding="utf-8").format(
            image_b64=image_b64,
            prompt=params["prompt"],
            negative_prompt=params.get("negative_prompt") or "",
            num_frames=num_frames,
            frame_rate=_LTX_FRAME_RATE,
            height=profile["height"],
            width=profile["width"],
        )
        local_script = Path(tempfile.gettempdir()) / f"colab_job_{uuid.uuid4().hex}.py"
        local_script.write_text(script, encoding="utf-8")

        session_name = f"{config.COLAB_SESSION_PREFIX}-{uuid.uuid4().hex[:8]}"
        session = colab_client.ColabSession(session_name, gpu=gpu)
        try:
            on_progress("provisioning Colab GPU runtime")
            session.start(on_progress)

            on_progress("installing model dependencies")
            session.install(
                ["diffusers>=0.32,<1", "transformers", "accelerate", "sentencepiece", "protobuf"],
                on_progress,
            )

            on_progress("running image-to-video generation on GPU")
            session.exec_file(local_script, on_progress, success_marker="VIDEO_READY")

            on_progress("downloading generated video")
            session.download("/content/output.mp4", output_path, on_progress)
        finally:
            on_progress("tearing down Colab runtime")
            session.stop(on_progress)
            local_script.unlink(missing_ok=True)

        on_progress("done")
