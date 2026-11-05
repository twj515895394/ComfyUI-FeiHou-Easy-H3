"""FeiHou Easy H3 Motion Context Kernel.

Inlined and self-contained Motion Context mathematical pinning engine
derived from H3 tokenization principles. Slices tail video and audio tokens
from the previous clip's sampled latent and injects them as keyframe anchors
into the current clip's conditioning.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import torch
try:
    from .latent_stitcher import unpack_h3_latent
except (ImportError, ValueError):
    from latent_stitcher import unpack_h3_latent

_LOG = logging.getLogger("feihou_motion_context")

FRAME_PER_TOKEN = (1, 4, 4, 4, 4)
FPS = 24.0
FRAME_RESCALE = 5.0 / 3.0
AUDIO_HZ = 40.0
VIDEO_RUN_GRID = (124, 107, 90, 73, 56, 39, 22, 5, 1)


def pixel_frames(latent_t: int) -> int:
    """Pixel frames covered by latent_t latent steps."""
    return sum(FRAME_PER_TOKEN[k % 5] for k in range(latent_t))


def step_offsets(latent_t: int) -> list[int]:
    """Pixel-frame index at which each latent step begins."""
    out, acc = [], 0
    for k in range(latent_t):
        out.append(acc)
        acc += FRAME_PER_TOKEN[k % 5]
    return out


def steps_for_frames(n: int) -> int | None:
    """Latent steps covering exactly n pixel frames from cycle position 0."""
    k, covered = 0, 0
    while covered < n:
        covered += FRAME_PER_TOKEN[k % 5]
        k += 1
    return k if covered == n else None


def video_tail_from_latent(latent: dict[str, Any], n: int) -> tuple[list[torch.Tensor], list[int], int]:
    """Slice the last n pixel frames of video straight out of a generated H3 latent."""
    video, _ = unpack_h3_latent(latent)
    total = int(video.shape[2])
    steps = steps_for_frames(n)
    if steps is None:
        raise ValueError(
            f"feihou_motion_context: a {n} frame window is not a whole number of latent steps. "
            "Use 5, 22, 39 or 56."
        )
    if steps > total:
        raise ValueError(f"feihou_motion_context: asked for {steps} latent steps, but latent only has {total}.")
    start = total - steps
    if start % 5 != 0:
        raise RuntimeError(
            f"feihou_motion_context: the {steps} step tail of a {total} step latent starts at cycle position {start % 5}, not 0."
        )
    covered = pixel_frames(steps)
    if covered != n:
        raise RuntimeError(f"feihou_motion_context: {steps} steps cover {covered} frames, expected {n}.")
    blocks = [video[:1, :, start + k : start + k + 1].clone() for k in range(steps)]
    return blocks, step_offsets(steps), covered


def audio_tail_from_latent(latent: dict[str, Any], a_frames: int) -> tuple[torch.Tensor | None, int, float]:
    """Slice the last a_frames worth of audio steps straight out of a generated H3 latent."""
    video, audio = unpack_h3_latent(latent)
    if audio is None:
        return None, 0, 0.0
    total_t = int(audio.shape[-1])
    frames = pixel_frames(int(video.shape[2]))
    overhang = total_t - FRAME_RESCALE * frames
    if not (-0.5 < overhang < 0.5):
        _LOG.warning("feihou_motion_context: audio grid unexpected (%d steps for %d frames); assuming no overhang.", total_t, frames)
        overhang = 0.0
    rt = int(round(a_frames / float(FPS) * AUDIO_HZ))
    if rt > total_t:
        _LOG.warning("feihou_motion_context: asked for %d audio steps, latent only has %d. Pinning all of it.", rt, total_t)
        rt = total_t
    if rt < 1:
        return None, 0, float(overhang)
    tail = audio[:1, ..., total_t - rt :].clone()
    return tail, rt, float(overhang)


def inject_h3_motion_context(
    conditioning: list[list[Any]],
    prev_latent: dict[str, Any] | None,
    context_length: int = 22,
    audio_context_length: int = 18,
) -> tuple[list[list[Any]], int]:
    """Inject Motion Context keyframe anchors into conditioning from prev_latent.

    Returns (new_conditioning, trim_frames).
    """
    if prev_latent is None:
        return conditioning, 0

    context_length = int(context_length)
    audio_context_length = int(audio_context_length)

    blocks, offsets, covered = video_tail_from_latent(prev_latent, context_length)
    audio_latent, ref_audio_t, overhang = audio_tail_from_latent(prev_latent, audio_context_length)

    # Build video keyframes (strictly contain 'latent' to prevent third-party KeyError crashes)
    keyframes = [{"resolved_frame_index": p, "latent": blk} for p, blk in zip(offsets, blocks)]

    # Build audio reference block (conforms to MiniMax H3 minimax_refs standard)
    audio_ref = None
    if audio_latent is not None and ref_audio_t > 0:
        audio_ref = {
            "kind": "audio",
            "ref_audio_t": ref_audio_t,
            "audio_latent": audio_latent,
        }

    # Merge into conditioning
    out = []
    for emb, extra in conditioning:
        d = extra.copy()
        prior = d.get("minimax_keyframes") or []
        prior_refs = list(d.get("minimax_refs") or [])
        kept = []
        for kf in prior:
            p = kf.get("resolved_frame_index", 0)
            if p >= covered:
                if "latent" in kf and kf["latent"] is not None:
                    kept.append(dict(kf))
                elif kf.get("audio_latent") is not None:
                    # Migrate audio-only keyframe to minimax_refs
                    prior_refs.append({
                        "kind": "audio",
                        "ref_audio_t": int(kf["audio_latent"].shape[-1]),
                        "audio_latent": kf["audio_latent"],
                    })

        d["minimax_keyframes"] = kept + keyframes
        if audio_ref is not None:
            prior_refs.append(audio_ref)
        if prior_refs:
            d["minimax_refs"] = prior_refs

        out.append([emb, d])

    return out, covered


def sanitize_h3_conditioning(conditioning: list[list[Any]]) -> list[list[Any]]:
    """Defensive sanitizer for MiniMax H3 conditioning.

    Guarantees:
    - Every entry in `minimax_keyframes` strictly contains a valid 'latent' tensor.
    - Any entry lacking 'latent' but possessing 'audio_latent' is migrated to `minimax_refs`.
    - Completely prevents third-party monkey patches (e.g. ComfyUI-PainterNodes)
      from crashing with KeyError: 'latent'.
    """
    if not conditioning:
        return conditioning
    sanitized = []
    for item in conditioning:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            sanitized.append(item)
            continue
        emb, extra = item[0], item[1]
        if not isinstance(extra, dict):
            sanitized.append(item)
            continue
        d = extra.copy()
        if "minimax_keyframes" in d:
            kfs = d["minimax_keyframes"] or []
            valid_kfs = []
            migrated_refs = list(d.get("minimax_refs") or [])
            for kf in kfs:
                if isinstance(kf, dict):
                    if "latent" in kf and kf["latent"] is not None:
                        valid_kfs.append(kf)
                    elif kf.get("audio_latent") is not None:
                        migrated_refs.append({
                            "kind": "audio",
                            "ref_audio_t": int(kf["audio_latent"].shape[-1]),
                            "audio_latent": kf["audio_latent"],
                        })
                else:
                    valid_kfs.append(kf)
            d["minimax_keyframes"] = valid_kfs
            if migrated_refs:
                d["minimax_refs"] = migrated_refs
        sanitized.append([emb, d])
    return sanitized
