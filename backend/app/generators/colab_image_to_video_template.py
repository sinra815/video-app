"""Template executed on the remote Colab GPU VM via `colab exec -f`.

{{placeholders}} are filled in by ColabImageToVideoGenerator before upload.
Runs diffusers' I2VGenXL pipeline (image + text prompt -> video), and writes
the result to /content/output.mp4, which the backend then pulls back with
`colab download`.
"""
import base64
import io

import torch
from diffusers import I2VGenXLPipeline
from diffusers.utils import export_to_video
from PIL import Image

pipe = I2VGenXLPipeline.from_pretrained(
    "ali-vilab/i2vgen-xl",
    torch_dtype=torch.float16,
    variant="fp16",
)
# The full model doesn't comfortably fit in a T4's 16GB VRAM alongside
# activations for 50 inference steps; offload submodules to CPU when idle
# instead of pipe.to("cuda"), matching diffusers' own I2VGenXL example. GPUs
# with more headroom (L4/A100) skip offload for speed - see _GPU_PROFILES in
# colab_image_to_video.py.
if {use_cpu_offload}:
    pipe.enable_model_cpu_offload()
else:
    pipe.to("cuda")
# Extra memory headroom: slice VAE decode and attention so peak activation
# memory doesn't scale with the full batch at once.
pipe.enable_vae_slicing()
pipe.enable_attention_slicing()

image_bytes = base64.b64decode({image_b64!r})
image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
prompt = {prompt!r}
negative_prompt = {negative_prompt!r}
num_frames = {num_frames}

generator = torch.manual_seed(8888)
frames = pipe(
    prompt=prompt,
    image=image,
    # Resolution is picked per-GPU (see _GPU_PROFILES in
    # colab_image_to_video.py): T4's 16GB can't fit the pipeline's native
    # height=704, width=1280 alongside inference activations (confirmed OOM
    # mid-forward, inside transformer_in's feed-forward block - overshoot
    # was ~3.4GiB against a ~14.5GiB budget), so it falls back to a reduced
    # resolution. Below that native scale this model shows visible
    # morphing/warping (confirmed against a real generation at 320x576), so
    # GPUs with enough VRAM (L4/A100) run at native resolution instead.
    height={height},
    width={width},
    negative_prompt=negative_prompt or None,
    num_inference_steps=50,
    num_frames=num_frames,
    guidance_scale=9.0,
    generator=generator,
).frames[0]

export_to_video(frames, "/content/output.mp4", fps={fps})
print("VIDEO_READY /content/output.mp4")
