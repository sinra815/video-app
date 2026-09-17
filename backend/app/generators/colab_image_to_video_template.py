"""Template executed on the remote Colab GPU VM via `colab exec -f`.

{{placeholders}} are filled in by ColabImageToVideoGenerator before upload.
Runs diffusers' LTX-Video image-to-video pipeline (Lightricks/LTX-Video,
Apache-2.0), and writes the result to /content/output.mp4, which the backend
then pulls back with `colab download`.
"""
import base64
import io
import time

import torch
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import export_to_video
from PIL import Image

_t0 = time.time()


def _mark(label: str) -> None:
    print(f"PROGRESS {{label}} t+{{time.time() - _t0:.0f}}s", flush=True)


# An anonymous (unauthenticated) request to the HF Hub is rate-limited and
# can be slow enough to time out before the ~20GB of weights finish
# downloading (confirmed against a real run) - each job is a fresh Colab VM
# with no persistent cache, so this download happens every time.
#
# Passed explicitly to from_pretrained rather than via the HF_TOKEN env var:
# inside a real Colab runtime, huggingface_hub instead tries to pull a token
# from Colab's own "Secrets" panel (google.colab.userdata) and that lookup
# hangs/times out when there's no interactive Colab UI to grant it (as here,
# via `colab exec`).
hf_token = {hf_token!r} or None
_mark(f"start (hf_token set: {{bool(hf_token)}}, len: {{len(hf_token) if hf_token else 0}})")

pipe = LTXImageToVideoPipeline.from_pretrained(
    "Lightricks/LTX-Video", torch_dtype=torch.bfloat16, token=hf_token
)
_mark("model loaded")
# The T5-XXL text encoder alone is ~11B params; offload idle submodules to
# CPU instead of pipe.to("cuda") so the full pipeline fits a T4's 16GB.
pipe.enable_model_cpu_offload()
_mark("cpu offload enabled")

image_bytes = base64.b64decode({image_b64!r})
image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
prompt = {prompt!r}
negative_prompt = {negative_prompt!r} or "worst quality, inconsistent motion, blurry, jittery, distorted"


def _on_step(pipeline, step, timestep, kwargs):
    _mark(f"inference step {{step}}")
    return kwargs


generator = torch.manual_seed(8888)
frames = pipe(
    image=image,
    prompt=prompt,
    negative_prompt=negative_prompt,
    height={height},
    width={width},
    num_frames={num_frames},
    frame_rate={frame_rate},
    num_inference_steps=50,
    generator=generator,
    callback_on_step_end=_on_step,
).frames[0]
_mark("inference done")

export_to_video(frames, "/content/output.mp4", fps={frame_rate})
_mark("video exported")
print("VIDEO_READY /content/output.mp4")
