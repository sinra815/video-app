import subprocess
from pathlib import Path

import imageio_ffmpeg

from .base import ProgressCallback, VideoGenerator


class SlideshowGenerator(VideoGenerator):
    """Builds an mp4 slideshow from images (+ optional background audio) using ffmpeg.

    Runs entirely locally via the static ffmpeg binary bundled by imageio-ffmpeg,
    so it needs no GPU and no Colab session.
    """

    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        image_paths = [Path(p) for p in params["image_paths"]]
        if not image_paths:
            raise ValueError("At least one image is required")
        audio_path = params.get("audio_path")
        show = float(params.get("seconds_per_image", 3.0))
        trans = float(params.get("transition_seconds", 0.8))
        resolution = params.get("resolution", "1280x720")
        fps = int(params.get("fps", 30))
        width, height = (int(x) for x in resolution.lower().split("x"))

        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        n = len(image_paths)
        # Disable crossfade transitions when there's only one image, or trans <= 0.
        use_xfade = trans > 0 and n > 1
        clip_duration = show + trans if use_xfade else show

        on_progress(f"preparing {n} image input(s)")

        cmd = [ffmpeg, "-y"]
        for img in image_paths:
            cmd += ["-loop", "1", "-t", f"{clip_duration}", "-i", str(img)]

        has_audio = bool(audio_path)
        if has_audio:
            cmd += ["-stream_loop", "-1", "-i", str(audio_path)]

        scale_pad = (
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,fps={fps}"
        )

        filter_parts = [f"[{i}:v]{scale_pad}[v{i}]" for i in range(n)]

        if n == 1:
            video_label = "v0"
        elif use_xfade:
            chain_label = "v0"
            cumulative = 0.0
            for i in range(1, n):
                cumulative += show
                out_label = f"vx{i}" if i < n - 1 else "vout"
                filter_parts.append(
                    f"[{chain_label}][v{i}]xfade=transition=fade:duration={trans}:"
                    f"offset={cumulative}[{out_label}]"
                )
                chain_label = out_label
            video_label = chain_label
        else:
            concat_inputs = "".join(f"[v{i}]" for i in range(n))
            filter_parts.append(f"{concat_inputs}concat=n={n}:v=1:a=0[vout]")
            video_label = "vout"

        filter_complex = ";".join(filter_parts)

        cmd += ["-filter_complex", filter_complex, "-map", f"[{video_label}]"]

        if has_audio:
            cmd += ["-map", f"{n}:a", "-shortest"]

        cmd += [
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-r", str(fps),
        ]
        if has_audio:
            cmd += ["-c:a", "aac", "-b:a", "192k"]

        cmd += [str(output_path)]

        on_progress("encoding video with ffmpeg")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-4000:]}")
        on_progress("done")
