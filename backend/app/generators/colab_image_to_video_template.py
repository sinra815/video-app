"""Template executed on the remote Colab GPU VM via `colab exec -f`.

{{placeholders}} are filled in by ColabImageToVideoGenerator before upload.
Runs diffusers' I2VGenXL pipeline (image + text prompt -> video) against an
image already pushed to the session with `colab upload`, and writes the
result to /content/output.mp4, which the backend then pulls back with
`colab download`.
"""
import torch
from diffusers import I2VGenXLPipeline
from diffusers.utils import export_to_video, load_image

pipe = I2VGenXLPipeline.from_pretrained(
    "ali-vilab/i2vgen-xl",
    torch_dtype=torch.float16,
    variant="fp16",
)
pipe = pipe.to("cuda")

image = load_image("/content/input_image.png")
prompt = {prompt!r}
negative_prompt = {negative_prompt!r}
num_frames = {num_frames}

generator = torch.manual_seed(8888)
frames = pipe(
    prompt=prompt,
    image=image,
    negative_prompt=negative_prompt or None,
    num_inference_steps=50,
    num_frames=num_frames,
    generator=generator,
).frames[0]

export_to_video(frames, "/content/output.mp4", fps={fps})
print("VIDEO_READY /content/output.mp4")
