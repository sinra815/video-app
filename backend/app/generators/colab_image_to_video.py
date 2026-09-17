import base64
import tempfile
import uuid
from pathlib import Path

from .. import colab_client, config
from .base import ProgressCallback, VideoGenerator

_TEMPLATE_PATH = Path(__file__).parent / "colab_image_to_video_template.py"

# I2VGenXL's native resolution is height=704, width=1280. A T4's 16GB VRAM
# can't fit that alongside inference activations even with CPU offload
# (confirmed OOM, ~3.4GiB over a ~14.5GiB budget), so it runs at a reduced
# resolution instead - see the "raised resolution" note in
# colab_image_to_video_template.py. L4 (24GB) and A100 (40GB+) have enough
# headroom to run at native resolution, which noticeably improves output
# quality since this model degrades outside its trained scale.
_GPU_PROFILES = {
    # 512x896 (the original T4 fallback) is only ~51% of native pixel count -
    # a big, untested jump down from the point that actually OOM'd (native,
    # 100%). 576x1024 (~66% of native) is a real attempt to claw back some of
    # that unused headroom; if it OOMs, step back down.
    "T4": {"height": 576, "width": 1024, "cpu_offload": True},
    "L4": {"height": 704, "width": 1280, "cpu_offload": True},
    "A100": {"height": 704, "width": 1280, "cpu_offload": False},
}


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

        gpu = params.get("gpu", config.COLAB_DEFAULT_GPU)
        profile = _GPU_PROFILES.get(gpu, _GPU_PROFILES["T4"])

        script = _TEMPLATE_PATH.read_text(encoding="utf-8").format(
            image_b64=image_b64,
            prompt=params["prompt"],
            negative_prompt=params.get("negative_prompt") or "",
            num_frames=num_frames,
            fps=fps,
            height=profile["height"],
            width=profile["width"],
            use_cpu_offload=profile["cpu_offload"],
        )
        local_script = Path(tempfile.gettempdir()) / f"colab_job_{uuid.uuid4().hex}.py"
        local_script.write_text(script, encoding="utf-8")

        session_name = f"{config.COLAB_SESSION_PREFIX}-{uuid.uuid4().hex[:8]}"
        session = colab_client.ColabSession(session_name, gpu=gpu)
        try:
            on_progress("provisioning Colab GPU runtime")
            session.start(on_progress)

            on_progress("installing model dependencies")
            # I2VGenXLPipeline is deprecated (dropped from active maintenance
            # after diffusers 0.33.1) and reaches into CLIPTextModel
            # internals that current transformers restructured. Pinning only
            # transformers older then breaks the other direction: unpinned
            # "latest" diffusers expects newer transformers exports
            # (confirmed against real sessions both ways -
            # `AttributeError: 'CLIPTextModel' object has no attribute
            # 'text_model'` with everything unpinned, then
            # `ImportError: cannot import name 'Dinov2WithRegistersConfig'`
            # with only transformers pinned old). Pin both to a matching,
            # contemporary pair from while I2VGenXL was still maintained.
            session.install(["diffusers==0.31.0", "transformers==4.46.3", "accelerate"], on_progress)

            on_progress("running image-to-video generation on GPU")
            session.exec_file(local_script, on_progress, success_marker="VIDEO_READY")

            on_progress("downloading generated video")
            session.download("/content/output.mp4", output_path, on_progress)
        finally:
            on_progress("tearing down Colab runtime")
            session.stop(on_progress)
            local_script.unlink(missing_ok=True)

        on_progress("done")
