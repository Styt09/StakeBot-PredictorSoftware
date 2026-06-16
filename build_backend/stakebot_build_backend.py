"""Tiny local PEP 517/660 backend for offline editable installs.

The repository intentionally avoids runtime dependencies.  This backend lets
`pip install -e '.[dev]'` succeed in restricted environments where downloading
setuptools is not possible by emitting an editable wheel with a .pth to src/.
"""
from __future__ import annotations

import base64
import csv
import hashlib
from pathlib import Path
import zipfile

NAME = "stakebot-predictorsoftware"
VERSION = "0.1.0"
DIST = "stakebot_predictorsoftware"
DIST_INFO = f"{DIST}-{VERSION}.dist-info"


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def _metadata() -> str:
    return "\n".join(
        [
            "Metadata-Version: 2.1",
            f"Name: {NAME}",
            f"Version: {VERSION}",
            "Summary: Institutional quantitative trading platform foundation with governance-first signal gating.",
            "Requires-Python: >=3.10",
            "Provides-Extra: dev",
            'Requires-Dist: pytest>=8; extra == "dev"',
            "",
        ]
    )


def _wheel() -> str:
    return "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: stakebot-build-backend 0.1",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
            "",
        ]
    )


def _hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def _write_metadata_dir(path: Path) -> str:
    dist_info = path / DIST_INFO
    dist_info.mkdir(parents=True, exist_ok=True)
    (dist_info / "METADATA").write_text(_metadata(), encoding="utf-8")
    (dist_info / "WHEEL").write_text(_wheel(), encoding="utf-8")
    (dist_info / "RECORD").write_text("", encoding="utf-8")
    return DIST_INFO


def get_requires_for_build_wheel(config_settings=None):
    return []


def get_requires_for_build_editable(config_settings=None):
    return []


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    return _write_metadata_dir(Path(metadata_directory))


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return _write_metadata_dir(Path(metadata_directory))


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _build_editable_wheel(Path(wheel_directory))


def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _build_editable_wheel(Path(wheel_directory))


def _build_editable_wheel(wheel_directory: Path) -> str:
    wheel_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{DIST}-{VERSION}-py3-none-any.whl"
    wheel_path = wheel_directory / filename
    src_path = str((_root() / "src").resolve()) + "\n"
    files = {
        f"{DIST}.pth": src_path.encode("utf-8"),
        f"{DIST_INFO}/METADATA": _metadata().encode("utf-8"),
        f"{DIST_INFO}/WHEEL": _wheel().encode("utf-8"),
    }
    record_rows: list[list[str]] = []
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in files.items():
            zf.writestr(arcname, data)
            record_rows.append([arcname, _hash(data), str(len(data))])
        record_name = f"{DIST_INFO}/RECORD"
        record_rows.append([record_name, "", ""])
        record_text = _record_text(record_rows)
        zf.writestr(record_name, record_text.encode("utf-8"))
    return filename


def _record_text(rows: list[list[str]]) -> str:
    from io import StringIO

    handle = StringIO()
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerows(rows)
    return handle.getvalue()
