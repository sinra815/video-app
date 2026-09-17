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
# instead of pipe.to("cuda"), matching diffusers' own I2VGenXL example.
pipe.enable_model_cpu_offload()
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
    # The pipeline's own defaults (height=704, width=1280) produce latents
    # too large for a T4's 16GB once num_frames is folded into the batch
    # dim for the temporal transformer (confirmed OOM mid-forward, inside
    # transformer_in's feed-forward block - but the overshoot was modest,
    # ~3.4GiB against a ~14.5GiB budget). An earlier fix cut all the way to
    # 320x576 to be safe, but going that far below the model's trained
    # resolution introduced visible morphing/warping artifacts (confirmed
    # against a real generation) - this model degrades noticeably outside
    # its native scale. Halving native resolution (rather than quartering
    # it) keeps proportionally much more headroom against that ~23%
    # overshoot while staying far closer to the trained scale.
    height=512,
    width=896,
    negative_prompt=negative_prompt or None,
    num_inference_steps=50,
    num_frames=num_frames,
    guidance_scale=9.0,
    generator=generator,
).frames[0]

export_to_video(frames, "/content/output.mp4", fps={fps})
print("VIDEO_READY /content/output.mp4")
