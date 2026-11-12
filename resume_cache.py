"""Disk cache for the resumable chain sampler.

One directory per cache key holds the decoded segment (for preview and
assembly) and the latent tail (for the next segment's continuation).
The cache never resamples and never resizes a tail to fit a new canvas.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
from typing import Any

import torch

_KEY_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class ResumeCacheError(ValueError):
    """A cache operation the user can fix by changing a widget."""


def validate_cache_key(cache_key: str | None) -> str:
    """Return a safe cache key, or raise ResumeCacheError."""
    key = str(cache_key if cache_key is not None else "").strip()
    if not key:
        key = "default"
    if not _KEY_RE.fullmatch(key):
        raise ResumeCacheError("缓存名只能用字母、数字、下划线和短横线。")
    return key


def cache_root(cache_key: str, base_dir: str | None = None) -> str:
    """Directory that holds one production's segments and tails."""
    key = validate_cache_key(cache_key)
    if base_dir is None:
        try:
            import folder_paths
            base_dir = folder_paths.get_temp_directory()
        except Exception:
            base_dir = os.path.join(tempfile.gettempdir(), "feihou_h3_resume_root")
    path = os.path.join(base_dir, "feihou_h3_resume", key)
    os.makedirs(path, exist_ok=True)
    return path


def _manifest_path(root: str) -> str:
    return os.path.join(root, "manifest.json")


def load_manifest(root: str) -> dict[str, Any]:
    path = _manifest_path(root)
    if not os.path.isfile(path):
        return {"segments": {}}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, ValueError):
        return {"segments": {}}
    if not isinstance(data, dict):
        return {"segments": {}}
    data.setdefault("segments", {})
    return data


def save_manifest(root: str, manifest: dict[str, Any]) -> None:
    path = _manifest_path(root)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def reset_cache(root: str) -> None:
    """Delete every segment and tail under this cache key."""
    if os.path.isdir(root):
        shutil.rmtree(root, ignore_errors=True)
    os.makedirs(root, exist_ok=True)


def segment_path(root: str, index: int) -> str:
    return os.path.join(root, f"seg_{int(index):02d}.pt")


def tail_path(root: str, index: int) -> str:
    return os.path.join(root, f"tail_{int(index):02d}.pt")


def _torch_save(payload: dict[str, Any], path: str) -> None:
    tmp = path + ".tmp"
    torch.save(payload, tmp)
    os.replace(tmp, path)


def _torch_load(path: str) -> dict[str, Any]:
    try:
        payload = torch.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        payload = torch.load(path, map_location="cpu")
    if not isinstance(payload, dict):
        raise ResumeCacheError(f"缓存文件损坏：{os.path.basename(path)}")
    return payload


def save_segment(
    root: str,
    index: int,
    *,
    frames: torch.Tensor,
    audio: dict[str, Any] | None,
    seed: int,
    width: int,
    height: int,
    overlap_frames: int,
    continuation_mode: str,
) -> None:
    """Store one decoded, already-trimmed segment."""
    _torch_save(
        {"frames": frames.detach().cpu(), "audio": _cpu_audio(audio), "index": int(index)},
        segment_path(root, index),
    )
    manifest = load_manifest(root)
    _check_settings(manifest, width, height, overlap_frames, continuation_mode, writing=True)
    manifest["width"] = int(width)
    manifest["height"] = int(height)
    manifest["overlap_frames"] = int(overlap_frames)
    manifest["continuation_mode"] = str(continuation_mode)
    entry = manifest["segments"].get(str(index), {})
    entry.update({"seed": int(seed), "frames": int(frames.shape[0]), "segment": True})
    manifest["segments"][str(index)] = entry
    save_manifest(root, manifest)


def save_tail(
    root: str,
    index: int,
    *,
    latent: dict[str, Any],
    width: int,
    height: int,
    overlap_frames: int,
    continuation_mode: str,
) -> None:
    """Store the latent tail the next segment continues from.

    The caller passes a latent that is already detached on CPU. Importing the
    sampler here breaks under ComfyUI, which does not put this folder on the
    module path.
    """
    _torch_save(
        {
            "latent": latent,
            "width": int(width),
            "height": int(height),
            "overlap_frames": int(overlap_frames),
            "continuation_mode": str(continuation_mode),
            "index": int(index),
        },
        tail_path(root, index),
    )
    manifest = load_manifest(root)
    entry = manifest["segments"].get(str(index), {})
    entry["tail"] = True
    manifest["segments"][str(index)] = entry
    save_manifest(root, manifest)


def load_tail(
    root: str,
    index: int,
    *,
    width: int,
    height: int,
    overlap_frames: int,
    continuation_mode: str,
) -> dict[str, Any]:
    """Load a previous segment's latent tail, refusing a mismatched canvas."""
    path = tail_path(root, index)
    if not os.path.isfile(path):
        raise ResumeCacheError(
            f"缓存里没有第 {index} 段的尾巴。先跑那一段，或把起始段改成 1。"
        )
    payload = _torch_load(path)
    manifest = load_manifest(root)
    _check_settings(manifest, width, height, overlap_frames, continuation_mode, writing=False)
    if int(payload.get("width", -1)) != int(width) or int(payload.get("height", -1)) != int(height):
        raise ResumeCacheError("缓存是按另一种画布跑的。换一个缓存名，或打开「清空缓存」后从头跑。")
    if int(payload.get("overlap_frames", -1)) != int(overlap_frames):
        raise ResumeCacheError("缓存是按另一种重叠帧数跑的。换一个缓存名，或打开「清空缓存」后从头跑。")
    if str(payload.get("continuation_mode", "")) != str(continuation_mode):
        raise ResumeCacheError("缓存是按另一种续接方式跑的。换一个缓存名，或打开「清空缓存」后从头跑。")
    latent = payload.get("latent")
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ResumeCacheError(f"第 {index} 段的尾巴缓存损坏。")
    return latent


def load_segment(root: str, index: int) -> dict[str, Any]:
    path = segment_path(root, index)
    if not os.path.isfile(path):
        raise ResumeCacheError(f"缓存缺第 {index} 段，不能拼接。先把这一段跑完。")
    payload = _torch_load(path)
    frames = payload.get("frames")
    if not isinstance(frames, torch.Tensor) or frames.ndim != 4 or frames.shape[0] < 1:
        raise ResumeCacheError(f"第 {index} 段的成片缓存损坏。")
    return payload


def recorded_seed(root: str, index: int) -> int | None:
    manifest = load_manifest(root)
    entry = manifest.get("segments", {}).get(str(index), {})
    seed = entry.get("seed")
    return int(seed) if seed is not None else None


def invalidate_from(root: str, index: int) -> list[int]:
    """Drop this segment and every later one. Their tails were built on the old cut."""
    removed: list[int] = []
    manifest = load_manifest(root)
    kept = {}
    for key, entry in list(manifest.get("segments", {}).items()):
        try:
            number = int(key)
        except (TypeError, ValueError):
            continue
        if number >= int(index):
            for path in (segment_path(root, number), tail_path(root, number)):
                if os.path.isfile(path):
                    os.remove(path)
            if number not in removed:
                removed.append(number)
        else:
            kept[key] = entry
    manifest["segments"] = kept
    save_manifest(root, manifest)
    return sorted(removed)


def _check_settings(manifest, width, height, overlap_frames, continuation_mode, *, writing: bool) -> None:
    if not manifest.get("segments"):
        return
    mismatches = []
    if "width" in manifest and int(manifest["width"]) != int(width):
        mismatches.append("画布")
    if "height" in manifest and int(manifest["height"]) != int(height):
        mismatches.append("画布")
    if "overlap_frames" in manifest and int(manifest["overlap_frames"]) != int(overlap_frames):
        mismatches.append("重叠帧数")
    if "continuation_mode" in manifest and str(manifest["continuation_mode"]) != str(continuation_mode):
        mismatches.append("续接方式")
    if mismatches:
        action = "不能写入" if writing else "不能续接"
        raise ResumeCacheError(
            f"缓存是按另一种{'、'.join(dict.fromkeys(mismatches))}跑的，{action}。"
            "换一个缓存名，或打开「清空缓存」后从头跑。"
        )


def _cpu_audio(audio: dict[str, Any] | None) -> dict[str, Any] | None:
    if not audio or audio.get("waveform") is None:
        return None
    out = dict(audio)
    waveform = audio["waveform"]
    if isinstance(waveform, torch.Tensor):
        out["waveform"] = waveform.detach().cpu()
    return out
