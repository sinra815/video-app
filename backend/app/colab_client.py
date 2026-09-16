"""Thin wrapper around the `colab` CLI (google-colab-cli).

google-colab-cli only ships for Linux/macOS and needs a Google account
authenticated against the Colab API (OAuth2 or ADC) plus available compute
units. None of that is available in this dev environment, so this module is
the integration point: it is fully wired up to the documented CLI surface,
but every call first checks `is_available()` and raises a clear error if the
`colab` binary isn't on PATH, so the rest of the app can treat "Colab not
configured" as an ordinary, catchable failure instead of crashing.

Reference: https://github.com/googlecolab/google-colab-cli
"""
import re
import shutil
import subprocess
from pathlib import Path
from typing import Callable, Optional

from . import config

ProgressCallback = Callable[[str], None]

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


class ColabUnavailableError(RuntimeError):
    pass


def is_available() -> bool:
    return shutil.which(config.COLAB_BIN) is not None


def _run(args: list[str], on_progress: Optional[ProgressCallback] = None, timeout: Optional[int] = None) -> str:
    if not is_available():
        raise ColabUnavailableError(
            f"'{config.COLAB_BIN}' CLI not found on PATH. google-colab-cli only "
            "supports Linux/macOS and requires `uv tool install google-colab-cli` "
            "plus Google account authentication (see the project README)."
        )
    if on_progress:
        on_progress(f"colab {' '.join(args)}")
    result = subprocess.run(
        [config.COLAB_BIN, "--auth", config.COLAB_AUTH, *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(f"colab {' '.join(args)} failed: {_strip_ansi(result.stderr).strip()}")
    return result.stdout


class ColabSession:
    """Provision-run-teardown lifecycle for one job, mirroring `colab run`."""

    def __init__(self, session_name: str, gpu: str = config.COLAB_DEFAULT_GPU):
        self.session_name = session_name
        self.gpu = gpu
        self._started = False

    def start(self, on_progress: Optional[ProgressCallback] = None) -> None:
        _run(["new", "-s", self.session_name, "--gpu", self.gpu], on_progress, timeout=600)
        self._started = True

    def install(self, packages: list[str], on_progress: Optional[ProgressCallback] = None) -> None:
        _run(["install", "-s", self.session_name, *packages], on_progress, timeout=900)

    def exec_file(self, local_script: Path, on_progress: Optional[ProgressCallback] = None) -> str:
        # `colab exec`'s own --timeout (code execution deadline inside the
        # session) defaults to just 30s, far too short for a model download
        # plus GPU inference; our outer subprocess timeout is the real ceiling.
        return _run(
            ["exec", "-s", self.session_name, "-f", str(local_script), "--timeout", "1700"],
            on_progress,
            timeout=1800,
        )

    def download(self, remote_path: str, local_path: Path, on_progress: Optional[ProgressCallback] = None) -> None:
        _run(["download", "-s", self.session_name, remote_path, str(local_path)], on_progress, timeout=600)

    def stop(self, on_progress: Optional[ProgressCallback] = None) -> None:
        if not self._started:
            return
        try:
            _run(["stop", "-s", self.session_name], on_progress, timeout=120)
        finally:
            self._started = False

    def __enter__(self) -> "ColabSession":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()
