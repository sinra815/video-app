"""Template executed on the remote Colab GPU VM via `colab exec -f`.

{{placeholders}} are filled in by ColabImageToVideoGenerator before upload.
Runs diffusers' LTX-Video image-to-video pipeline (Lightricks/LTX-Video,
Apache-2.0), and writes the result to /content/output.mp4, which the backend
then pulls back with `colab download`.
"""
import base64
import io
import os

import torch
from diffusers import LTXImageToVideoPipeline
from diffusers.utils import export_to_video
from PIL import Image

# An anonymous (unauthenticated) request to the HF Hub is rate-limited and
# can be slow enough to time out before the ~20GB of weights finish
# downloading (confirmed against a real run) - each job is a fresh Colab VM
# with no persistent cache, so this download happens every time.
hf_token = {hf_token!r}
if hf_token:
    os.environ["HF_TOKEN"] = hf_token

pipe = LTXImageToVideoPipeline.from_pretrained("Lightricks/LTX-Video", torch_dtype=torch.bfloat16)
# The T5-XXL text encoder alone is ~11B params; offload idle submodules to
# CPU instead of pipe.to("cuda") so the full pipeline fits a T4's 16GB.
pipe.enable_model_cpu_offload()

image_bytes = base64.b64decode({image_b64!r})
image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
prompt = {prompt!r}
negative_prompt = {negative_prompt!r} or "worst quality, inconsistent motion, blurry, jittery, distorted"

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
).frames[0]

export_to_video(frames, "/content/output.mp4", fps={frame_rate})
print("VIDEO_READY /content/output.mp4")
