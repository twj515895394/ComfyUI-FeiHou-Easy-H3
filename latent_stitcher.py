"""FeiHou Easy H3 Latent Stitcher.

Implements pure Latent-domain dual-channel (video and audio) periodic slicing
and temporal concatenation for MiniMax H3 AV latents.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import torch

try:
    import comfy.nested_tensor
except ImportError:
    comfy = None

LOGGER = logging.getLogger("feihou_latent_stitcher")

# In H3 tokenization: 1 + 4 + 4 + 4 + 4 + 1 + 4 = 22 frames = 7 latent steps.
H3_VIDEO_TRIM_STEPS = 7
H3_VIDEO_TRIM_STEPS_22 = 7
H3_VIDEO_TRIM_STEPS_39 = 12

# In H3 audio tokenization: 40 Hz audio against 24 fps video.
# 18 frames * (5 / 3) = 30 audio steps.
# 39 frames * (5 / 3) = 65 audio steps.
H3_AUDIO_TRIM_STEPS = 30
H3_AUDIO_TRIM_STEPS_22 = 30
H3_AUDIO_TRIM_STEPS_39 = 65


def get_h3_trim_steps(overlap_frames: int | str = 22) -> tuple[int, int]:
    """Return (video_trim_steps, audio_trim_steps) for a given overlap frame count."""
    frames = int(overlap_frames)
    if frames == 39:
        return H3_VIDEO_TRIM_STEPS_39, H3_AUDIO_TRIM_STEPS_39
    return H3_VIDEO_TRIM_STEPS_22, H3_AUDIO_TRIM_STEPS_22


def unpack_h3_latent(latent: dict[str, Any]) -> tuple[torch.Tensor, torch.Tensor]:
    """Unpack an H3 AV latent dictionary into (video_tensor, audio_tensor)."""
    if not isinstance(latent, dict) or "samples" not in latent:
        raise ValueError(f"Expected a latent dictionary containing 'samples', got {type(latent)}.")
    samples = latent["samples"]
    if hasattr(samples, "unbind"):
        parts = list(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = list(samples)
    else:
        raise ValueError(f"Expected H3 AV latent samples to be a NestedTensor or tuple, got {type(samples)}.")

    if len(parts) < 2:
        raise ValueError(f"H3 AV latent must contain at least 2 streams (video and audio), found {len(parts)}.")

    video = parts[0]
    audio = parts[1]

    if video.ndim == 4:  # [C, T, H, W] -> unbatched
        video = video.unsqueeze(0)
    if video.ndim != 5:
        raise ValueError(f"Expected video latent [B, C, T, H, W], got shape {tuple(video.shape)}.")

    if audio.ndim == 3:  # [C, 2, T_audio] -> unbatched
        audio = audio.unsqueeze(0)
    if audio.ndim != 4:
        raise ValueError(f"Expected audio latent [B, C, 2, T_audio], got shape {tuple(audio.shape)}.")

    return video, audio


def pack_h3_latent(video: torch.Tensor, audio: torch.Tensor) -> dict[str, Any]:
    """Pack video and audio tensors into a standard H3 AV latent dictionary."""
    if comfy is not None and hasattr(comfy.nested_tensor, "NestedTensor"):
        nested = comfy.nested_tensor.NestedTensor([video, audio])
    else:
        nested = (video, audio)
    return {"samples": nested}


class H3LatentStitcher:
    """Slices overlap steps and stitches video and audio latents along the temporal axis."""

    def __init__(self, video_trim_steps: int = H3_VIDEO_TRIM_STEPS, audio_trim_steps: int = H3_AUDIO_TRIM_STEPS):
        self.video_trim_steps = int(video_trim_steps)
        self.audio_trim_steps = int(audio_trim_steps)

    def stitch(self, latents: Sequence[dict[str, Any]], trim_overlap: bool = True) -> dict[str, Any]:
        """Stitch a sequence of clip latents into a single continuous AV latent."""
        if not latents:
            raise ValueError("No latents provided for stitching.")
        if len(latents) == 1:
            return latents[0]

        stitched_videos: list[torch.Tensor] = []
        stitched_audios: list[torch.Tensor] = []

        ref_w: int | None = None
        ref_h: int | None = None
        ref_channels: int | None = None
        ref_device: torch.device | None = None
        ref_dtype: torch.dtype | None = None

        for idx, latent_dict in enumerate(latents):
            v, a = unpack_h3_latent(latent_dict)

            # Spatial consistency check
            b, c, t, h, w = v.shape
            if idx == 0:
                ref_channels = c
                ref_h = h
                ref_w = w
                ref_device = v.device
                ref_dtype = v.dtype
            else:
                if c != ref_channels or h != ref_h or w != ref_w:
                    raise ValueError(
                        f"Clip {idx + 1} video latent spatial dimensions [C={c}, H={h}, W={w}] "
                        f"do not match clip 1 [C={ref_channels}, H={ref_h}, W={ref_w}]. Cannot stitch in latent space."
                    )
                if v.device != ref_device:
                    v = v.to(device=ref_device)
                if v.dtype != ref_dtype:
                    v = v.to(dtype=ref_dtype)
                if a.device != ref_device:
                    a = a.to(device=ref_device)

            if idx > 0 and trim_overlap:
                if t <= self.video_trim_steps:
                    raise ValueError(
                        f"Clip {idx + 1} video latent has {t} steps, which is <= trim steps {self.video_trim_steps}."
                    )
                if a.shape[-1] <= self.audio_trim_steps:
                    raise ValueError(
                        f"Clip {idx + 1} audio latent has {a.shape[-1]} steps, which is <= trim steps {self.audio_trim_steps}."
                    )
                v = v[:, :, self.video_trim_steps :, :, :]
                a = a[:, :, :, self.audio_trim_steps :]

            stitched_videos.append(v)
            stitched_audios.append(a)

        final_video = torch.cat(stitched_videos, dim=2)
        final_audio = torch.cat(stitched_audios, dim=-1)

        LOGGER.info(
            "H3LatentStitcher stitched %d clips: final video latent %s, final audio latent %s",
            len(latents),
            tuple(final_video.shape),
            tuple(final_audio.shape),
        )

        return pack_h3_latent(final_video, final_audio)
