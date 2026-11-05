"""FeiHou Easy H3 Chunked & Segmented VAE Decoder.

Decodes MiniMax H3 latents (both video and audio). Supports:
1. Individual segment decoding + pixel-space / waveform-space trimming and concatenation
   (adopting the ComfyUI-MiniMaxH3-lanxi architecture to eliminate VAE causal temporal phase distortion).
2. Streaming in-place CPU pre-allocation to prevent 2x RAM spikes on large (up to 8-segment) renders.
3. Direct single-pass decoding for single-clip latents or legacy workflows.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

import torch

try:
    from .latent_stitcher import unpack_h3_latent
except (ImportError, ValueError):
    from latent_stitcher import unpack_h3_latent

_LOG = logging.getLogger("feihou_vae_decoder")

# H3 token grid constants matching lanxi:
# In H3's 5n+2 latent / 17n+5 pixel grid:
# 7 latent steps correspond to 1 + 4*4 + 1 + 4 = 22 pixel frames.
CARRY_FRAMES = 22
FPS = 24.0


def _audio_samples(audio: dict[str, Any] | None, seconds: float) -> int:
    """Compute number of audio samples corresponding to a duration in seconds."""
    if not audio:
        return 0
    sample_rate = int(audio.get("sample_rate") or 0)
    return max(0, int(round(float(seconds) * sample_rate))) if sample_rate else 0


def _resample_audio(waveform: torch.Tensor, source_rate: int, target_rate: int) -> torch.Tensor:
    """Resample waveform tensor to target sample rate."""
    if source_rate == target_rate:
        return waveform
    try:
        import torchaudio
        return torchaudio.functional.resample(waveform, source_rate, target_rate)
    except Exception:
        ratio = target_rate / float(source_rate)
        length = max(1, int(round(waveform.shape[-1] * ratio)))
        indices = torch.linspace(0, waveform.shape[-1] - 1, length).round().long()
        return waveform[..., indices]


def _concat_audio(clips: Sequence[dict[str, Any] | None]) -> dict[str, Any] | None:
    """Concatenate multiple decoded audio clips along the temporal axis."""
    valid = [c for c in clips if c is not None and c.get("waveform") is not None]
    if not valid:
        return None
    sample_rate = int(valid[0].get("sample_rate") or 32000)
    waveforms = []
    for clip in valid:
        wf = clip["waveform"]
        clip_sr = int(clip.get("sample_rate") or sample_rate)
        if clip_sr != sample_rate:
            wf = _resample_audio(wf, clip_sr, sample_rate)
        waveforms.append(wf)
    if not waveforms:
        return None
    return {"waveform": torch.cat(waveforms, dim=-1), "sample_rate": sample_rate}


def _decode_single_audio(audio_vae, audio_tensor: torch.Tensor) -> dict[str, Any] | None:
    """Decode a single H3 audio latent tensor [B, 32, 2, T]."""
    if audio_vae is None or audio_tensor is None:
        return None

    # If audio_vae has a concrete int audio_sample_rate, use direct decode first
    # (preserves mock / explicit configuration without mock autovivification)
    sr = getattr(audio_vae, "audio_sample_rate", None)
    if isinstance(sr, int):
        try:
            decoded = audio_vae.decode(audio_tensor)
            if hasattr(decoded, "movedim"):
                waveform = decoded.movedim(-1, 1).to(audio_tensor.device)
            else:
                waveform = decoded
            return {"waveform": waveform, "sample_rate": sr}
        except Exception:
            pass

    try:
        from comfy_extras.nodes_audio import vae_decode_audio
        res = vae_decode_audio(audio_vae, {"samples": audio_tensor})
        if res is not None and isinstance(res.get("sample_rate"), int):
            return res
    except Exception:
        pass

    try:
        decoded = audio_vae.decode(audio_tensor)
        if hasattr(decoded, "movedim"):
            waveform = decoded.movedim(-1, 1).to(audio_tensor.device)
        else:
            waveform = decoded
        calc_sr = getattr(
            audio_vae,
            "audio_sample_rate",
            getattr(getattr(audio_vae, "first_stage_model", None), "output_sample_rate", 32000),
        )
        final_sr = int(calc_sr) if isinstance(calc_sr, (int, float)) else 32000
        return {"waveform": waveform, "sample_rate": final_sr}
    except Exception as exc:
        _LOG.warning("Audio VAE decoding failed: %s", exc)
        return None


class FeiHouEasyH3VAEDecode:
    """High-fidelity VAE decoder for MiniMax H3 video and audio latents."""

    CATEGORY = "FeiHou Easy H3"
    FUNCTION = "decode"
    RETURN_TYPES = ("IMAGE", "AUDIO")
    RETURN_NAMES = ("image", "audio")
    DESCRIPTION = "High-fidelity VAE decoder for MiniMax H3. Decodes clips individually and trims in pixel/waveform space to eliminate temporal phase distortion with streaming memory optimization."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "samples": ("LATENT",),
                "vae": ("VAE",),
                "tile_temporal": ("BOOLEAN", {"default": True, "tooltip": "兼容旧工作流；时序分块由 H3 VAE 原生解码器管理"}),
                "tile_size": ("INT", {"default": 27, "min": 10, "max": 100, "step": 5, "tooltip": "兼容旧工作流；H3 VAE 原生解码器决定分块大小"}),
                "overlap": ("INT", {"default": 5, "min": 1, "max": 10, "tooltip": "兼容旧工作流；H3 VAE 原生解码器决定时间重叠"}),
            },
            "optional": {
                "audio_vae": ("VAE", {"tooltip": "H3 音频 VAE 模型，用于解码音轨"}),
            },
        }

    def decode(
        self,
        samples: dict[str, Any],
        vae,
        tile_temporal: bool = True,
        tile_size: int = 27,
        overlap: int = 5,
        audio_vae=None,
    ):
        # Check if samples contains multi-segment latents for pixel-space decoding (lanxi design)
        clip_latents = samples.get("clip_latents") if isinstance(samples, dict) else None
        if clip_latents and isinstance(clip_latents, list) and len(clip_latents) > 1:
            _LOG.info("=" * 60)
            _LOG.info(
                "[FeiHou VAEDecode] [Stage 3/3] 多分镜逐段解码与像素空间拼接（共 %d 个分镜，衔接裁切: %d 帧）",
                len(clip_latents),
                CARRY_FRAMES,
            )
            _LOG.info("=" * 60)
            # Pre-clean VRAM
            if torch.cuda.is_available():
                try:
                    import comfy.model_management as mm
                    mm.soft_empty_cache()
                except Exception:
                    pass
                import gc
                gc.collect()

            frames_out: list[torch.Tensor] = []
            audio_out: list[dict[str, Any]] = []
            assembled_frames: torch.Tensor | None = None
            write_pos = 0
            use_preallocated = True

            for idx, seg_latent in enumerate(clip_latents):
                seg_v, seg_a = unpack_h3_latent(seg_latent)
                _LOG.info(
                    "  -> 解码分镜 %d/%d (视频 Latent 形状: %s, 音频 Latent: %s)...",
                    idx + 1,
                    len(clip_latents),
                    tuple(seg_v.shape),
                    "存在" if seg_a is not None else "无",
                )
                seg_frames = vae.decode(seg_v)
                del seg_v  # Eagerly drop GPU latent

                if not isinstance(seg_frames, torch.Tensor) or seg_frames.ndim != 5:
                    shape = tuple(seg_frames.shape) if isinstance(seg_frames, torch.Tensor) else type(seg_frames).__name__
                    raise ValueError(f"Expected H3 VAE decoded video in [B, T, H, W, C] layout, got {shape}.")
                if seg_frames.shape[-1] not in (1, 3, 4):
                    raise ValueError(
                        f"Expected H3 VAE decoded video to have 1, 3, or 4 channels last, got shape {tuple(seg_frames.shape)}."
                    )

                b, t, h, w, c = seg_frames.shape
                seg_frames = seg_frames.reshape(b * t, h, w, c).detach().to("cpu")
                _LOG.info("     分镜 %d 像素解码完成: 帧数=%d, 分辨率=%dx%d", idx + 1, seg_frames.shape[0], w, h)

                seg_audio = None
                if audio_vae is not None and seg_a is not None:
                    seg_audio = _decode_single_audio(audio_vae, seg_a)
                    if seg_audio is not None and seg_audio.get("waveform") is not None:
                        seg_audio = dict(seg_audio)
                        seg_audio["waveform"] = seg_audio["waveform"].detach().to("cpu")
                del seg_a  # Eagerly drop GPU audio latent

                # Pixel-space & waveform-space trimming for carried clips
                if idx > 0:
                    if int(seg_frames.shape[0]) > CARRY_FRAMES:
                        _LOG.info(
                            "     分镜 %d: 裁切前 %d 帧衔接重复帧 (剩余有效帧数: %d)",
                            idx + 1,
                            CARRY_FRAMES,
                            seg_frames.shape[0] - CARRY_FRAMES,
                        )
                        seg_frames = seg_frames[CARRY_FRAMES:]
                    if seg_audio is not None and seg_audio.get("waveform") is not None:
                        trim_samples = _audio_samples(seg_audio, CARRY_FRAMES / FPS)
                        if trim_samples and seg_audio["waveform"].shape[-1] > trim_samples:
                            _LOG.info(
                                "     分镜 %d: 裁切前 %d 采样点音频 (%.2fs)",
                                idx + 1,
                                trim_samples,
                                CARRY_FRAMES / FPS,
                            )
                            seg_audio["waveform"] = seg_audio["waveform"][..., trim_samples:]

                # Stream into preallocated buffer to avoid 2x RAM spike on large (e.g. 8-segment) runs
                if idx == 0 and use_preallocated:
                    seg0_len = seg_frames.shape[0]
                    # Estimate total frame count assuming consistent segment lengths
                    tot_est = seg0_len + (len(clip_latents) - 1) * max(0, seg0_len - CARRY_FRAMES)
                    try:
                        assembled_frames = torch.empty((tot_est, h, w, c), dtype=torch.float32, device="cpu")
                        assembled_frames[:seg0_len] = seg_frames
                        write_pos = seg0_len
                        del seg_frames
                    except Exception as exc:
                        _LOG.debug("Pre-allocation skipped (%s), falling back to list concatenation.", exc)
                        use_preallocated = False
                        frames_out.append(seg_frames)
                elif use_preallocated and assembled_frames is not None:
                    cur_len = seg_frames.shape[0]
                    if write_pos + cur_len <= assembled_frames.shape[0]:
                        assembled_frames[write_pos : write_pos + cur_len] = seg_frames
                        write_pos += cur_len
                        del seg_frames
                    else:
                        # Length mismatch fallback
                        use_preallocated = False
                        frames_out = [assembled_frames[:write_pos], seg_frames]
                        assembled_frames = None
                else:
                    frames_out.append(seg_frames)

                if seg_audio is not None:
                    audio_out.append(seg_audio)

                # Free VRAM immediately between segments
                if torch.cuda.is_available():
                    try:
                        import comfy.model_management as mm
                        mm.soft_empty_cache()
                    except Exception:
                        pass
                    import gc
                    gc.collect()

            if use_preallocated and assembled_frames is not None:
                all_frames = assembled_frames[:write_pos]
            else:
                all_frames = torch.cat(frames_out, dim=0)

            all_audio = _concat_audio(audio_out)
            _LOG.info(
                "[FeiHou VAEDecode] [Stage 3/3] 多分镜拼接解码完成: 合成总帧数=%d (约 %.2fs @ 24fps) | 音轨: %s",
                all_frames.shape[0],
                all_frames.shape[0] / 24.0,
                f"已生成 (采样率: {all_audio.get('sample_rate', 44100)}Hz)" if (all_audio and "sample_rate" in all_audio) else ("已生成" if all_audio else "无"),
            )
            _LOG.info("=" * 60)
            return (all_frames, all_audio)

        # Direct single-pass decoding for 1-clip or pre-stitched latents
        video, audio = unpack_h3_latent(samples)
        total_steps = int(video.shape[2])
        _LOG.info("=" * 60)
        _LOG.info("[FeiHou VAEDecode] [Stage 3/3] 单分镜直接解码模式（视频 Latent 步长/帧数: %d）", total_steps)
        _LOG.info("=" * 60)

        decoded_video = vae.decode(video)
        if not isinstance(decoded_video, torch.Tensor) or decoded_video.ndim != 5:
            shape = tuple(decoded_video.shape) if isinstance(decoded_video, torch.Tensor) else type(decoded_video).__name__
            raise ValueError(f"Expected H3 VAE decoded video in [B, T, H, W, C] layout, got {shape}.")
        if decoded_video.shape[-1] not in (1, 3, 4):
            raise ValueError(
                f"Expected H3 VAE decoded video to have 1, 3, or 4 channels last, got shape {tuple(decoded_video.shape)}."
            )

        batch, frames, height, width, channels = decoded_video.shape
        video_images = decoded_video.reshape(batch * frames, height, width, channels)

        audio_output = None
        if audio_vae is not None and audio is not None:
            audio_output = _decode_single_audio(audio_vae, audio)

        _LOG.info(
            "[FeiHou VAEDecode] [Stage 3/3] 单分镜解码完成: 输出图像形状=%s (共 %d 帧, 约 %.2fs @ 24fps) | 音轨: %s",
            tuple(video_images.shape),
            video_images.shape[0],
            video_images.shape[0] / 24.0,
            f"已生成 (采样率: {audio_output.get('sample_rate', 44100)}Hz)" if (audio_output and "sample_rate" in audio_output) else ("已生成" if audio_output else "无"),
        )
        _LOG.info("=" * 60)
        return (video_images, audio_output)
