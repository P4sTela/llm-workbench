#!/usr/bin/env python3
"""Download and verify the files described by a model manifest."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path, PureWindowsPath
from typing import Any
from urllib.parse import quote

SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


class ManifestError(ValueError):
    """The manifest is not valid for this downloader."""


class DownloadError(RuntimeError):
    """A download or verification step failed."""


def non_empty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ManifestError(f"{field} must be a non-empty string")
    if "\x00" in value:
        raise ManifestError(f"{field} must not contain NUL")
    return value


def safe_relative_parts(value: str, field: str) -> list[str]:
    if value.startswith("/") or "\\" in value:
        raise ManifestError(f"{field} must be a safe relative path")
    windows_path = PureWindowsPath(value)
    if windows_path.is_absolute() or windows_path.drive:
        raise ManifestError(f"{field} must be a safe relative path")

    parts = value.split("/")
    if not parts or any(not part or part in {".", ".."} for part in parts):
        raise ManifestError(
            f"{field} must not contain empty, '.', or '..' path components"
        )
    return parts


def validate_manifest(data: Any) -> tuple[str, str, list[dict[str, Any]]]:
    if not isinstance(data, dict):
        raise ManifestError("top-level JSON value must be an object")

    name = non_empty_string(data.get("name"), "name")
    non_empty_string(data.get("format"), "format")
    repo = non_empty_string(data.get("repo"), "repo")
    revision = non_empty_string(data.get("revision"), "revision")

    repo_parts = safe_relative_parts(repo, "repo")
    if len(repo_parts) != 2:
        raise ManifestError("repo must be in 'owner/name' form")
    safe_relative_parts(revision, "revision")

    files = data.get("files")
    if not isinstance(files, list) or not files:
        raise ManifestError("files must be a non-empty array")

    validated_files: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(files):
        field_prefix = f"files[{index}]"
        if not isinstance(item, dict):
            raise ManifestError(f"{field_prefix} must be an object")

        file_name = non_empty_string(item.get("file"), f"{field_prefix}.file")
        safe_relative_parts(file_name, f"{field_prefix}.file")
        if file_name in seen:
            raise ManifestError(f"duplicate file: {file_name}")
        seen.add(file_name)

        byte_count = item.get("bytes")
        if (
            isinstance(byte_count, bool)
            or not isinstance(byte_count, int)
            or byte_count < 0
        ):
            raise ManifestError(f"{field_prefix}.bytes must be a non-negative integer")

        sha256 = non_empty_string(item.get("sha256"), f"{field_prefix}.sha256")
        if not SHA256_RE.fullmatch(sha256):
            raise ManifestError(
                f"{field_prefix}.sha256 must be a 64-character hexadecimal digest"
            )

        validated_files.append(
            {"file": file_name, "bytes": byte_count, "sha256": sha256.lower()}
        )

    return (
        name,
        f"https://huggingface.co/{quote(repo, safe='/')}/resolve/{quote(revision, safe='/')}",
        validated_files,
    )


def load_manifest(path: Path) -> tuple[str, str, list[dict[str, Any]]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ManifestError(f"manifest not found: {path}") from exc
    except OSError as exc:
        raise ManifestError(f"cannot read manifest {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ManifestError(
            f"invalid JSON in {path}: {exc.msg} at line {exc.lineno}"
        ) from exc
    return validate_manifest(data)


def output_directory(repository_root: Path) -> Path:
    configured = os.environ.get("MODEL_DIR") or os.environ.get("NINFER_MODEL_DIR")
    return Path(configured).expanduser() if configured else repository_root / "models"


def ensure_regular_or_missing(path: Path, description: str) -> bool:
    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError as exc:
        raise DownloadError(f"cannot inspect {description} {path}: {exc}") from exc

    if path.is_symlink() or not path.is_file():
        raise DownloadError(f"{description} is not a regular file: {path}")
    return True


def is_verified(path: Path, expected_bytes: int, expected_sha256: str) -> bool:
    if path.stat().st_size != expected_bytes:
        return False

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest() == expected_sha256


def verify_or_raise(path: Path, spec: dict[str, Any], description: str) -> None:
    if not is_verified(path, spec["bytes"], spec["sha256"]):
        raise DownloadError(
            f"{description} mismatch for {path}; expected {spec['bytes']} bytes "
            f"and SHA-256 {spec['sha256']}"
        )


def handle_existing_target(
    part_path: Path, final_path: Path, spec: dict[str, Any]
) -> None:
    if ensure_regular_or_missing(final_path, "existing model file") and is_verified(
        final_path, spec["bytes"], spec["sha256"]
    ):
        part_path.unlink()
        return
    raise DownloadError(
        f"refusing to overwrite an existing mismatched file: {final_path}"
    )


def promote_verified(part_path: Path, final_path: Path, spec: dict[str, Any]) -> None:
    try:
        os.link(part_path, final_path)
    except OSError as exc:
        if exc.errno == errno.EEXIST:
            handle_existing_target(part_path, final_path, spec)
            return
        raise DownloadError(
            f"cannot install verified file {final_path}: {exc}"
        ) from exc

    try:
        part_path.unlink()
    except OSError as exc:
        raise DownloadError(
            f"verified file installed but cannot remove {part_path}: {exc}"
        ) from exc


def safe_output_path(output_dir: Path, path_parts: list[str]) -> Path:
    candidate = output_dir.joinpath(*path_parts)
    root = output_dir.resolve()
    resolved = candidate.resolve(strict=False)
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise DownloadError(
            f"output path escapes the model directory through a symlink: {candidate}"
        ) from exc

    try:
        candidate.lstat()
    except FileNotFoundError:
        candidate_exists = False
    else:
        candidate_exists = True
    if candidate_exists and candidate.is_symlink():
        raise DownloadError(f"output file must not be a symlink: {candidate}")
    return resolved


def download_file(base_url: str, output_dir: Path, spec: dict[str, Any]) -> None:
    file_name = spec["file"]
    path_parts = safe_relative_parts(file_name, f"files entry {file_name}")
    final_path = safe_output_path(output_dir, path_parts)
    part_path = Path(f"{final_path}.part")

    if ensure_regular_or_missing(final_path, "existing model file"):
        verify_or_raise(final_path, spec, "existing model file")
        print(f"Model already verified: {final_path}")
        return

    final_path.parent.mkdir(parents=True, exist_ok=True)
    if ensure_regular_or_missing(part_path, "partial model file"):
        partial_size = part_path.stat().st_size
        if partial_size > spec["bytes"]:
            raise DownloadError(
                f"partial file is larger than expected: {part_path} "
                f"({partial_size} > {spec['bytes']} bytes)"
            )
        if partial_size == spec["bytes"]:
            verify_or_raise(part_path, spec, "partial model file")
            promote_verified(part_path, final_path, spec)
            print(f"Model ready and verified: {final_path}")
            return

    url = f"{base_url}/{quote(file_name, safe='/')}?download=true"
    print(f"Downloading {file_name}...", flush=True)
    command = [
        "curl",
        "--fail",
        "--location",
        "--silent",
        "--show-error",
        "--retry",
        "3",
        "--retry-delay",
        "2",
        "--continue-at",
        "-",
        "--output",
        str(part_path),
        url,
    ]
    try:
        result = subprocess.run(
            command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True
        )
    except FileNotFoundError as exc:
        raise DownloadError("curl is required but was not found on PATH") from exc
    except OSError as exc:
        raise DownloadError(f"could not start curl: {exc}") from exc

    if result.returncode != 0:
        raise DownloadError(
            f"curl failed for {file_name} with exit status {result.returncode}; "
            f"partial data left at {part_path}"
        )

    if not ensure_regular_or_missing(part_path, "downloaded partial model file"):
        raise DownloadError(f"curl completed without creating {part_path}")
    verify_or_raise(part_path, spec, "downloaded file")
    promote_verified(part_path, final_path, spec)
    print(f"Model ready and verified: {final_path}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download and verify a Hugging Face model manifest"
    )
    parser.add_argument("manifest", type=Path, help="path to the model manifest JSON")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        manifest_path = args.manifest.expanduser()
        _name, base_url, files = load_manifest(manifest_path)
        repository_root = Path(__file__).resolve().parents[1]
        target_dir = output_directory(repository_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        for spec in files:
            download_file(base_url, target_dir, spec)
        return 0
    except (ManifestError, DownloadError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
