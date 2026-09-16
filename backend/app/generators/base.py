from abc import ABC, abstractmethod
from pathlib import Path
from typing import Callable

# Called with a short human-readable progress string as the job advances.
ProgressCallback = Callable[[str], None]


class VideoGenerator(ABC):
    """Common interface for anything that turns job params into an mp4 file."""

    @abstractmethod
    def generate(self, params: dict, output_path: Path, on_progress: ProgressCallback) -> None:
        """Produce a video at output_path. Raise on failure."""
        raise NotImplementedError
