from __future__ import annotations

import shutil
from collections.abc import Iterable
from pathlib import Path

from puild.logging import log_action


def _to_path_list(item: str | Path | Iterable[str | Path]) -> list[Path]:
    if isinstance(item, (str, Path)):
        return [Path(item)]
    return [Path(p) for p in item]


def needs_rebuild(
    target: str | Path | Iterable[str | Path],
    sources: str | Path | Iterable[str | Path],
    *,
    log: bool = False,
) -> bool:
    """Check if target needs to be rebuilt based on source modification times.

    Returns True if:
    - Any target file does not exist.
    - Any source file is newer than the oldest target file.

    Returns False if:
    - All targets exist and are newer than all source files.
    """
    targets = _to_path_list(target)
    src_list = _to_path_list(sources)

    targets_display = ", ".join(str(t) for t in targets)

    # If any target does not exist, we must rebuild
    missing_targets = [t for t in targets if not t.exists()]
    if missing_targets:
        if log:
            log_action("Rebuild", f"{targets_display} (target missing)", "yellow")
        return True

    # If no sources are specified, target exists so no rebuild
    if not src_list:
        if log:
            log_action("Up-to-date", targets_display, "green")
        return False

    # Check for missing sources
    for s in src_list:
        if not s.exists():
            raise FileNotFoundError(f"Source file does not exist: {s}")

    oldest_target_mtime = min(t.stat().st_mtime for t in targets)
    newest_source_mtime = max(s.stat().st_mtime for s in src_list)

    if newest_source_mtime > oldest_target_mtime:
        if log:
            log_action("Rebuild", f"{targets_display} (sources modified)", "yellow")
        return True

    if log:
        log_action("Up-to-date", targets_display, "green")
    return False


def mkdir(
    path: str | Path,
    *,
    parents: bool = True,
    exist_ok: bool = True,
    log: bool = True,
) -> Path:
    """Create a directory with parents and exist_ok enabled by default."""
    p = Path(path)
    p.mkdir(parents=parents, exist_ok=exist_ok)
    if log:
        log_action("Mkdir", str(p), "blue")
    return p


def rm(
    path: str | Path,
    *,
    recursive: bool = True,
    missing_ok: bool = True,
    log: bool = True,
) -> None:
    """Remove a file or directory."""
    p = Path(path)
    if not p.exists():
        if missing_ok:
            return
        raise FileNotFoundError(f"Path does not exist: {p}")

    if p.is_dir():
        if recursive:
            shutil.rmtree(p)
        else:
            p.rmdir()
    else:
        p.unlink()

    if log:
        log_action("Remove", str(p), "yellow")


def copy(
    src: str | Path,
    dst: str | Path,
    *,
    log: bool = True,
) -> Path:
    """Copy a file or directory to a destination."""
    src_path = Path(src)
    dst_path = Path(dst)

    if not src_path.exists():
        raise FileNotFoundError(f"Source does not exist: {src_path}")

    if src_path.is_dir():
        shutil.copytree(src_path, dst_path, dirs_exist_ok=True)
    else:
        if dst_path.is_dir():
            shutil.copy2(src_path, dst_path / src_path.name)
        else:
            dst_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src_path, dst_path)

    if log:
        log_action("Copy", f"{src_path} -> {dst_path}", "blue")

    return dst_path


def find_files(
    directory: str | Path = ".",
    pattern: str = "*",
    *,
    recursive: bool = True,
) -> list[Path]:
    """Find files matching pattern in directory."""
    dir_path = Path(directory)
    if recursive:
        matches = dir_path.rglob(pattern)
    else:
        matches = dir_path.glob(pattern)

    return sorted([p for p in matches if p.is_file()])
