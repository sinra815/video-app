"""Template executed on the remote Colab GPU VM via `colab exec -f`.

{{placeholders}} are filled in by ColabAiGenerator before upload. This runs
diffusers' text-to-video pipeline and writes the result to /content/output.mp4,
which the backend then pulls back with `colab download`.
"""
import torch
from diffusers import DiffusionPipeline
from diffusers.utils import export_to_video

pipe = DiffusionPipeline.from_pretrained(
    "damo-vilab/text-to-video-ms-1.7b",
    torch_dtype=torch.float16,
    variant="fp16",
)
pipe = pipe.to("cuda")

prompt = {prompt!r}
negative_prompt = {negative_prompt!r}
num_frames = {num_frames}

result = pipe(
    prompt,
    negative_prompt=negative_prompt or None,
    num_inference_steps=25,
    num_frames=num_frames,
)
export_to_video(result.frames[0], "/content/output.mp4", fps={fps})
print("VIDEO_READY /content/output.mp4")
