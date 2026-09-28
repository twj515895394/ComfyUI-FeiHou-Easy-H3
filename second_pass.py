"""Second-pass H3 conditioning adapter.

Keeps first-pass encode untouched. After a latent upscaler changes the canvas,
PackedLayout still sizes fl2va keyframe rows from the *target* spatial grid.
This module either resizes `minimax_keyframes` video latents to that grid, or
drops them. `minimax_refs` are never rewritten.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
import logging


import torch
import torch.nn.functional as F

MODE_SCALE = "缩放首帧到目标画布"
MODE_DROP = "丢掉首帧约束"
DEFAULT_MODE = MODE_SCALE
SECOND_PASS_MODES = (MODE_SCALE, MODE_DROP)


def adapt_second_pass(positive, latent, mode: str = DEFAULT_MODE):
    """Return (positive, latent) for the second-pass sampler.

    `latent` is always the same object. Scale mode requires `latent["samples"]`.
    Drop mode does not read spatial size.
    """
    if not isinstance(latent, Mapping):
        raise ValueError("二采条件适配需要目标 latent")
    resolved = str(mode or DEFAULT_MODE)
    src_sizes = _keyframe_video_sizes(positive)
    if resolved == MODE_DROP:
        adapted = _drop_keyframes(positive)
        if src_sizes:
            logging.info(
                "[Easy H3 二采] 丢掉 %s 条 keyframe (%s)",
                len(src_sizes),
                _fmt_wh(src_sizes),
            )
        else:
            logging.info("[Easy H3 二采] 丢掉 空操作 (无 keyframe)")
        return adapted, latent
    if resolved != MODE_SCALE:
        raise ValueError(f"未知二采 mode: {mode}")
    samples = latent.get("samples")
    if samples is None:
        raise ValueError("缩放首帧需要目标 latent 含 samples")
    height, width = _target_hw(samples)
    adapted = _scale_keyframes(positive, height, width)
    target = f"{width}x{height}"
    if not src_sizes:
        logging.info("[Easy H3 二采] 缩放 空操作 (无 keyframe) 目标 %s", target)
    elif all(hw == (height, width) for hw in src_sizes):
        logging.info("[Easy H3 二采] 缩放 已是 %s (%s keyframe)", target, len(src_sizes))
    else:
        logging.info(
            "[Easy H3 二采] 缩放 %s -> %s (%s keyframe)",
            _fmt_wh(src_sizes),
            target,
            len(src_sizes),
        )
    return adapted, latent


def _tensor_hw(video) -> tuple[int, int] | None:
    if not isinstance(video, torch.Tensor):
        return None
    if video.ndim == 5:
        return int(video.shape[3]), int(video.shape[4])
    if video.ndim == 4:
        return int(video.shape[-2]), int(video.shape[-1])
    return None


def _keyframe_video_sizes(positive) -> list[tuple[int, int]]:
    sizes = []
    if not positive:
        return sizes
    for _embedding, extras in positive:
        frames = extras.get("minimax_keyframes") if isinstance(extras, Mapping) else None
        if not frames:
            continue
        for frame in frames:
            video = frame.get("latent") if isinstance(frame, Mapping) else None
            hw = _tensor_hw(video)
            if hw is not None:
                sizes.append(hw)
    return sizes


def _fmt_wh(sizes: list[tuple[int, int]]) -> str:
    tokens = []
    seen = set()
    for height, width in sizes:
        token = f"{width}x{height}"
        if token not in seen:
            seen.add(token)
            tokens.append(token)
    return "+".join(tokens)


def _target_hw(samples) -> tuple[int, int]:
    video = _as_video_tensor(samples)
    if not isinstance(video, torch.Tensor):
        raise ValueError("目标 latent samples 不是 tensor")
    if video.ndim == 5:
        return int(video.shape[3]), int(video.shape[4])
    if video.ndim == 4:
        return int(video.shape[-2]), int(video.shape[-1])
    raise ValueError(f"无法从 samples 读取目标空间尺寸: ndim={video.ndim}")


def _as_video_tensor(samples):
    tensors = getattr(samples, "tensors", None)
    if tensors:
        return tensors[0]
    return samples


def _drop_keyframes(positive):
    if not _any_keyframes(positive):
        return positive
    adapted = []
    for embedding, extras in positive:
        copied = extras.copy()
        copied.pop("minimax_keyframes", None)
        adapted.append([embedding, copied])
    return adapted


def _scale_keyframes(positive, height: int, width: int):
    if not _any_keyframes(positive):
        return positive
    adapted = []
    changed_any = False
    for embedding, extras in positive:
        keyframes = extras.get("minimax_keyframes")
        if not keyframes:
            adapted.append([embedding, extras])
            continue
        next_frames = []
        changed = False
        for frame in keyframes:
            video = frame.get("latent") if isinstance(frame, Mapping) else None
            resized, did = _resize_video_latent(video, height, width)
            if not did:
                next_frames.append(frame)
                continue
            copied = dict(frame)
            copied["latent"] = resized
            next_frames.append(copied)
            changed = True
        if not changed:
            adapted.append([embedding, extras])
            continue
        copied = extras.copy()
        copied["minimax_keyframes"] = next_frames
        adapted.append([embedding, copied])
        changed_any = True
    return adapted if changed_any else positive


def _any_keyframes(positive) -> bool:
    if not positive:
        return False
    for _embedding, extras in positive:
        frames = extras.get("minimax_keyframes") if isinstance(extras, Mapping) else None
        if frames:
            return True
    return False


def _resize_video_latent(latent: Any, height: int, width: int) -> tuple[Any, bool]:
    if not isinstance(latent, torch.Tensor):
        return latent, False
    if latent.ndim == 5:
        _, _, _, src_h, src_w = latent.shape
        if src_h == height and src_w == width:
            return latent, False
        batch, channels, time, _, _ = latent.shape
        flat = latent.reshape(batch * time, channels, src_h, src_w)
        scaled = F.interpolate(
            flat.float(),
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )
        scaled = scaled.to(dtype=latent.dtype).reshape(batch, channels, time, height, width)
        return scaled, True
    if latent.ndim == 4:
        src_h, src_w = int(latent.shape[-2]), int(latent.shape[-1])
        if src_h == height and src_w == width:
            return latent, False
        scaled = F.interpolate(
            latent.float(),
            size=(height, width),
            mode="bilinear",
            align_corners=False,
        )
        return scaled.to(dtype=latent.dtype), True
    return latent, False
