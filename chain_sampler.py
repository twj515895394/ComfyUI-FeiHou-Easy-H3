"""FeiHou Easy H3 Chain Sampler.

Executes sequential multi-clip sampling with built-in Motion Context injection
and pure Latent-domain dual-channel (video and audio) stitching.
"""

from __future__ import annotations

import importlib
import logging
import os
import random
import time
from typing import Any, Sequence

import torch

try:
    import comfy.samplers
    import comfy.utils
    from comfy_extras import nodes_custom_sampler as cs
except ImportError:
    cs = None

try:
    import folder_paths
except ImportError:
    folder_paths = None

try:
    from .latent_stitcher import H3LatentStitcher, pack_h3_latent, unpack_h3_latent
    from .motion_context_kernel import inject_h3_motion_context, sanitize_h3_conditioning
    from .multi_clip_core import MultiClipContext
except (ImportError, ValueError):
    from latent_stitcher import H3LatentStitcher, pack_h3_latent, unpack_h3_latent
    from motion_context_kernel import inject_h3_motion_context, sanitize_h3_conditioning
    from multi_clip_core import MultiClipContext

_LOG = logging.getLogger("feihou_chain_sampler")

# Continuation constants matching ComfyUI-MiniMaxH3-lanxi:
# In H3's 5n+2 latent / 17n+5 pixel grid:
# - For 22 frames: 7 latent steps (1 + 4*4 + 1 + 4 = 22 frames), 36 audio steps, 18 frames audio context.
# - For 39 frames: 12 latent steps (22 + 17 = 39 frames), 65 audio steps, 39 frames audio context.
CARRY_TOKENS = 7
CARRY_FRAMES = 22
CARRY_AUDIO_STEPS = 36

CARRY_TOKENS_39 = 12
CARRY_FRAMES_39 = 39
CARRY_AUDIO_STEPS_39 = 65


def shift_sigma(base_sigma: torch.Tensor, shift: float) -> torch.Tensor:
    """MiniMax H3 Flow-Matching non-linear time shift."""
    return shift * base_sigma / (1.0 + (shift - 1.0) * base_sigma)


def _ensure_shifted_sigmas(sigmas: torch.Tensor, shift_video: float = 12.0) -> torch.Tensor:
    """Detect unshifted linear / simple schedules and map them into H3 Flow Matching shifted sigmas."""
    if not isinstance(sigmas, torch.Tensor) or sigmas.numel() < 3:
        return sigmas
    # In H3 flow matching with shift=12.0, for steps >= 4:
    # unshifted base_sigma[1] = 1 - 1/steps <= 0.875,
    # but shifted sigma[1] = 12 * (1 - 1/steps) / (1 + 11 * (1 - 1/steps)) >= 0.95!
    # If sigma[1] is < 0.92, it is definitely an unshifted linear or simple schedule.
    if sigmas[0].item() >= 0.99 and sigmas[1].item() < 0.92:
        shifted = shift_sigma(sigmas, shift_video)
        _LOG.info(
            "Auto-shifting linear sigmas to native H3 Flow Matching curve (shift=%.1f): %.4f -> %.4f...",
            shift_video,
            sigmas[1].item(),
            shifted[1].item(),
        )
        return shifted
    return sigmas


def _patch_h3_dual_clock(model, shift_video: float = 12.0, shift_audio: float = 3.0):
    """Patch model_sampling and transformer_options with H3 dual-clock Flow Matching shifts."""
    if model is None or not hasattr(model, "model_options"):
        return model
    try:
        patched = model.clone()
    except Exception:
        patched = model

    # 1. Patch transformer options for MiniMax DiT timestep mapping (comfy/ldm/minimax/model.py lines 612, 672)
    transformer_options = getattr(patched, "model_options", {}).get("transformer_options", {}).copy()
    transformer_options["minimax_h3_sigma_shift_video"] = float(shift_video)
    transformer_options["minimax_h3_sigma_shift_audio"] = float(shift_audio)
    patched.model_options["transformer_options"] = transformer_options

    # 2. Patch model_sampling if ModelSamplingAV is available
    try:
        import comfy.model_sampling
        native_av_cls = getattr(comfy.model_sampling, "ModelSamplingAV", None)
        if native_av_cls is not None:
            class FeiHouNativeAVSampling(native_av_cls, comfy.model_sampling.CONST):
                pass
            model_config = getattr(getattr(patched, "model", None), "model_config", None)
            if model_config is not None:
                orig_sampling = getattr(patched.model, "model_sampling", None)
                ms = FeiHouNativeAVSampling(model_config)
                ms.set_parameters(shift=float(shift_video), audio_shift=float(shift_audio))
                if hasattr(orig_sampling, "noise_scale"):
                    ms.set_noise_scale(orig_sampling.noise_scale)
                patched.add_object_patch("model_sampling", ms)
    except Exception as exc:
        _LOG.debug("Could not patch ModelSamplingAV: %s", exc)

    return patched


def _safe_unpack_av(latent_dict: dict[str, Any]) -> tuple[torch.Tensor, torch.Tensor | None]:
    """Safely unpack latent into (video, audio_or_none). Supports video-only latents."""
    if not isinstance(latent_dict, dict) or "samples" not in latent_dict:
        raise ValueError(f"Expected latent dictionary containing 'samples', got {type(latent_dict)}")
    samples = latent_dict["samples"]
    if hasattr(samples, "unbind"):
        parts = list(samples.unbind())
    elif isinstance(samples, (tuple, list)):
        parts = list(samples)
    elif isinstance(samples, torch.Tensor):
        parts = [samples]
    else:
        raise ValueError(f"Unexpected samples type {type(samples)}")

    video = parts[0]
    if video.ndim == 4:
        video = video.unsqueeze(0)
    audio = parts[1] if len(parts) > 1 else None
    if audio is not None and audio.ndim == 3:
        audio = audio.unsqueeze(0)
    return video, audio


def _carry_latent(
    prev_latent: dict[str, Any],
    cur_latent: dict[str, Any],
    carry_tokens: int = CARRY_TOKENS,
    carry_audio_steps: int = CARRY_AUDIO_STEPS,
    context_noise: float = 0.0,
) -> dict[str, Any]:
    """Carry over previous segment's tail latent into the start of the current segment.

    Adopts ComfyUI-MiniMaxH3-lanxi design:
    - carry_tokens (7 or 12) video tokens and carry_audio_steps (36 or 65) audio steps
      are copied to the head of the current latent.
    - A single-channel [B, 1, T, H, W] and [B, 1, 2, T] noise_mask is attached with context_noise
      (default 0.0) on the carried region, preserving it exactly during sampling.
    """
    prev_v, prev_a = _safe_unpack_av(prev_latent)
    cur_v, cur_a = _safe_unpack_av(cur_latent)

    tokens = min(int(carry_tokens), int(prev_v.shape[2]), int(cur_v.shape[2]))
    if tokens <= 0:
        return cur_latent

    video = cur_v.clone()
    video[..., :tokens, :, :] = prev_v[..., -tokens:, :, :].to(video)

    audio = None
    audio_steps = 0
    if prev_a is not None and cur_a is not None:
        audio_steps = min(int(carry_audio_steps), int(prev_a.shape[-1]), int(cur_a.shape[-1]))
        audio = cur_a.clone()
        if audio_steps > 0:
            audio[..., :audio_steps] = prev_a[..., -audio_steps:].to(audio)

    # Attach single-channel noise mask
    v_mask = torch.ones(
        (video.shape[0], 1, video.shape[2], video.shape[3], video.shape[4]),
        device=video.device,
        dtype=torch.float32,
    )
    v_mask[..., :tokens, :, :] = max(0.0, min(1.0, float(context_noise)))

    out = dict(cur_latent)
    if audio is not None:
        a_mask = torch.ones(
            (audio.shape[0], 1, audio.shape[2], audio.shape[3]),
            device=audio.device,
            dtype=torch.float32,
        )
        if audio_steps > 0:
            a_mask[..., :audio_steps] = 0.0
        if comfy is not None and hasattr(comfy.nested_tensor, "NestedTensor"):
            out["samples"] = comfy.nested_tensor.NestedTensor([video, audio])
            out["noise_mask"] = comfy.nested_tensor.NestedTensor([v_mask, a_mask])
        else:
            out["samples"] = (video, audio)
            out["noise_mask"] = (v_mask, a_mask)
    else:
        out["samples"] = video
        out["noise_mask"] = v_mask

    return out


def _latent_to_cpu(latent_dict: dict[str, Any]) -> dict[str, Any]:
    """Detach and transfer latent dictionary samples and masks to CPU memory.

    Prevents CUDA VRAM accumulation across many clips (e.g. 8-segment chains).
    """
    if not isinstance(latent_dict, dict):
        return latent_dict
    out = dict(latent_dict)
    samples = out.get("samples")
    if samples is not None:
        if hasattr(samples, "unbind"):
            parts = [p.detach().to("cpu") if isinstance(p, torch.Tensor) else p for p in samples.unbind()]
            if comfy is not None and hasattr(comfy.nested_tensor, "NestedTensor"):
                out["samples"] = comfy.nested_tensor.NestedTensor(parts)
            else:
                out["samples"] = tuple(parts)
        elif isinstance(samples, torch.Tensor):
            out["samples"] = samples.detach().to("cpu")
    masks = out.get("noise_mask")
    if masks is not None:
        if hasattr(masks, "unbind"):
            m_parts = [m.detach().to("cpu") if isinstance(m, torch.Tensor) else m for m in masks.unbind()]
            if comfy is not None and hasattr(comfy.nested_tensor, "NestedTensor"):
                out["noise_mask"] = comfy.nested_tensor.NestedTensor(m_parts)
            else:
                out["noise_mask"] = tuple(m_parts)
        elif isinstance(masks, torch.Tensor):
            out["noise_mask"] = masks.detach().to("cpu")
    return out


def _zero_out_conditioning(conditioning: list[list[Any]]) -> list[list[Any]]:
    """Produce zeroed-out negative conditioning without requiring an external node."""
    out = []
    for t in conditioning:
        emb = t[0]
        d = t[1].copy()
        pooled = d.get("pooled_output", None)
        if pooled is not None and isinstance(pooled, torch.Tensor):
            d["pooled_output"] = torch.zeros_like(pooled)
        zero_emb = torch.zeros_like(emb) if isinstance(emb, torch.Tensor) else emb
        out.append([zero_emb, d])
    return out


def _extract_bunny_bridge_params(conditioning: Any) -> dict[str, Any] | None:
    """Extract BUNNY H3 Conditioning Bridge metadata if present on conditioning."""
    if not conditioning or not isinstance(conditioning, list):
        return None
    for item in conditioning:
        if isinstance(item, (list, tuple)) and len(item) >= 2 and isinstance(item[1], dict):
            meta = item[1]
            if meta.get("bunny_h3_bridge"):
                return {
                    "adapter": meta.get("bunny_h3_bridge_adapter"),
                    "alpha": meta.get("bunny_h3_bridge_alpha", 0.1),
                    "magnitude_match": meta.get("bunny_h3_bridge_mode", "per_token"),
                }
    return None


_BUNNY_BRIDGE_RUNTIME_MODULE: Any = None


def _apply_bunny_bridge_to_conditioning(conditioning: Any, bridge_params: dict[str, Any]) -> Any:
    """Safely apply BUNNY H3 bridge MLP to a conditioning object using extracted parameters."""
    global _BUNNY_BRIDGE_RUNTIME_MODULE
    if not bridge_params or not conditioning:
        return conditioning
    try:
        if _BUNNY_BRIDGE_RUNTIME_MODULE is None:
            bridge_dirs = [
                "X:/ComfyUI-aki-v2/ComfyUI/custom_nodes/BUNNY_H3_Conditioning_Bridge",
            ]
            if folder_paths and hasattr(folder_paths, "base_path"):
                bridge_dirs.append(os.path.join(folder_paths.base_path, "custom_nodes", "BUNNY_H3_Conditioning_Bridge"))

            target_file = None
            for b_dir in bridge_dirs:
                if b_dir:
                    cand = os.path.join(b_dir, "nodes.py")
                    if os.path.isfile(cand):
                        target_file = cand
                        break

            if target_file is not None:
                import importlib.util
                spec = importlib.util.spec_from_file_location("bunny_bridge_runtime", target_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    if hasattr(mod, "_apply_bridge"):
                        # Cache the runtime module so the adapter weights are loaded once,
                        # not re-read from disk on every clip.
                        _BUNNY_BRIDGE_RUNTIME_MODULE = mod
        if _BUNNY_BRIDGE_RUNTIME_MODULE is not None:
            return _BUNNY_BRIDGE_RUNTIME_MODULE._apply_bridge(
                conditioning,
                adapter_name=bridge_params.get("adapter"),
                alpha=bridge_params.get("alpha", 0.1),
                magnitude_match=bridge_params.get("magnitude_match", "per_token"),
                enabled=True,
            )
    except Exception as exc:
        _LOG.warning("Could not apply BUNNY H3 bridge to conditioning: %s", exc)
    return conditioning


def _ensure_sol_attn(model):
    """Auto-attach native Model Sparse Attention (sol-attn) if not already patched on every block."""
    if model is None:
        return model
    try:
        from comfy_extras.nodes_sparse_attention import apply_block_sparse_attention
        options = getattr(model, "model_options", {}).get("transformer_options", {})
        dit = options.get("patches_replace", {}).get("dit", {})
        has_sparse = any(isinstance(k, tuple) and k[0] == "double_block" for k in dit.keys())
        if not has_sparse:
            _LOG.info("Auto-attaching native Model Sparse Attention (sol-attn) for SelfLift-Avatar...")
            return apply_block_sparse_attention(
                model,
                tau=1.3,
                topk_ratio=0.0,
                vsa=False,
                start_percent=0.2,
                end_percent=1.0,
                min_tokens=12288,
                dense_blocks=[],
                sink_conditioning="exact_kv_and_rows",
                extra_tokens=256,
                verbose=False,
            )
    except Exception as exc:
        _LOG.warning("Could not auto-apply sol-attn: %s", exc)
    return model


def _resolve_selflift_avatar_sampler_cls():
    """Dynamically resolve SelfLiftAvatarH3Sampler from custom_nodes without hard dependency."""
    try:
        import nodes
        cls = nodes.NODE_CLASS_MAPPINGS.get("SelfLiftAvatarH3Sampler")
        if cls is not None:
            return cls
    except Exception:
        pass

    for mod_name in ("custom_nodes.selflift-Avatar.nodes", "custom_nodes.selflift_avatar.nodes"):
        try:
            mod = importlib.import_module(mod_name)
            if hasattr(mod, "SelfLiftAvatarH3Sampler"):
                return getattr(mod, "SelfLiftAvatarH3Sampler")
        except Exception:
            pass
    return None


class FeiHouEasyH3ChainSampler:
    """Multi-clip long video chain sampler with built-in Motion Context and Latent stitching."""

    CATEGORY = "FeiHou Easy H3"
    FUNCTION = "execute"
    RETURN_TYPES = ("LATENT", "INT")
    RETURN_NAMES = ("latent", "clip_count")
    DESCRIPTION = "Sequentially sample multiple clips with automatic Motion Context pinning and pure Latent stitching."

    @classmethod
    def INPUT_TYPES(cls):
        upscaler_models = ["none"]
        if folder_paths is not None:
            for f_name in ("latent_upscale_models", "upscale_models"):
                try:
                    upscalers = folder_paths.get_filename_list(f_name)
                    if upscalers:
                        for u in upscalers:
                            if u not in upscaler_models:
                                upscaler_models.append(u)
                except Exception:
                    pass

        default_upscaler = "h3_upscaler_lms_v0.1_fp32.safetensors" if "h3_upscaler_lms_v0.1_fp32.safetensors" in upscaler_models else "none"

        return {
            "required": {
                "model": ("MODEL",),
                "multi_clip_context": ("FEIHOU_MULTI_CLIP_CONTEXT",),
                "vae": ("VAE",),
                "sampler": ("SAMPLER",),
                "sigmas": ("SIGMAS",),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFFFFFFFFFF, "control_after_generate": True, "tooltip": "全局初始随机种子，各分镜根据 seed_behavior 规律递增或固定"}),
                "cfg": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 100.0, "step": 0.1, "round": 0.01, "tooltip": "MiniMax H3 引导尺度（CFG）。H3 架构必须严格锁定 1.0，不可修改，修改会导致画质变灰或崩坏"}),
                "sampling_engine": (["selflift_avatar", "standard_euler"], {"default": "selflift_avatar", "tooltip": "采样引擎：selflift_avatar（推荐，一采低清二采超清两阶段极速推理，画质超清且速度快）；standard_euler（标准单阶段 Euler 采样）"}),
                "seed_behavior": (["increment", "fixed_all", "random_all"], {"default": "increment", "tooltip": "多分镜种子策略：increment（推荐，后一分镜种子自动递增+1，保持连贯微变）；fixed_all（所有分镜固定同一随机种子）；random_all（完全随机）"}),
            },
            "optional": {
                "continuation_mode": (["hybrid", "latent_carry", "motion_context"], {"default": "hybrid", "tooltip": "分段续接策略：hybrid（推荐，融合潜变量嵌入+引导特征注入）；latent_carry（对标lanxi，尾部潜变量嵌入+noise_mask冻结）；motion_context（仅引导特征注入）"}),
                "context_noise": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.01, "tooltip": "潜空间续接噪声强度：0.0表示完全保留上一段末尾潜变量；0.1-0.2允许微小重降噪除噪缝合"}),
                "shift_video": ("FLOAT", {"default": 12.0, "min": 0.01, "max": 100.0, "step": 0.1, "advanced": True, "tooltip": "MiniMax H3 视频 Flow-Matching Sigma Shift，默认 12.0"}),
                "shift_audio": ("FLOAT", {"default": 3.0, "min": 0.01, "max": 100.0, "step": 0.1, "advanced": True, "tooltip": "MiniMax H3 音频 Flow-Matching Sigma Shift，默认 3.0"}),
                "auto_shift_sigmas": ("BOOLEAN", {"default": True, "tooltip": "自动检测并纠正未进行 H3 时钟变换的线性调度步数 (如 BasicScheduler 'simple' 的无偏移调度)"}),
                "second_sampling_model": ("MODEL", {"tooltip": "SelfLift 二采高分辨率模型；如未连接则自动复用一采 model"}),
                "audio_vae": ("VAE", {"tooltip": "H3 音频 VAE 编解码器（与 Video VAE 独立分离）"}),
                "negative": ("CONDITIONING", {"tooltip": "负向提示词条件（可选；未连线时自动置零生成空负向）"}),
                "positive": ("CONDITIONING", {"tooltip": "正向提示词条件（可选；接入 BUNNY H3 语义桥或自定义 Conditioning）"}),
                # SelfLift parameters (transition_step 已由上游 Node 2 MultiClip 上下文全局及分镜统一传递，不再作为前端重复控件显示)
                "lowres_scale": ("FLOAT", {"default": 0.5, "min": 0.25, "max": 1.0, "step": 0.05, "tooltip": "SelfLift 一采低分辨率缩放比例（默认 0.5），先在 1/2 尺寸上极速构建骨架与大动态"}),
                "rho": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "SelfLift 噪声调度平滑参数（默认 0.0）"}),
                "w_min": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "SelfLift 一采向二采超分过渡的初始融合权重（默认 0.5）"}),
                "w_max": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.05, "tooltip": "SelfLift 二采超分阶段的最大精修权重（默认 1.0）"}),
                "upscaler_model": (upscaler_models, {"default": default_upscaler, "tooltip": "SelfLift 潜空间超分辨率放大模型（默认 h3_upscaler_lms_v0.1_fp32），负责一采与二采之间的潜变量升维"}),
                "highres_tiling": ("BOOLEAN", {"default": False, "tooltip": "【高分辨率低显存开关】：在 16G/24G 显卡上跑 2.0MP 开启可分块防爆显存；在 48G 显存显卡上建议保持 false 全屏整帧全速推理，画质无接缝最佳"}),
                "tiling_mode": (["auto", "manual"], {"default": "auto", "tooltip": "分块模式：auto（自动检测画面比例计算最佳分块）或 manual（手动指定块数）"}),
                "tiling_tiles": ("INT", {"default": 2, "min": 1, "max": 16, "tooltip": "分块数量（手动模式生效，默认切分 2 块）"}),
                "tiling_axis": (["auto", "horizontal", "vertical"], {"default": "auto", "tooltip": "分块切分轴向：auto（根据长宽比自动沿短边切分）、horizontal（水平切）、vertical（垂直切）"}),
                "highres_tiling_mode": (["spatial", "global_stream"], {"default": "global_stream", "tooltip": "分块流式传输模式：global_stream（推荐，搭配稀疏注意力大幅压降显存）；spatial（纯空间物理分块）"}),
                "highres_token_chunk": ("INT", {"default": 4096, "min": 256, "max": 65536, "tooltip": "分块单次 Attention 计算的最大 Token 块大小（默认 4096，数值越小显存越低）"}),
                "highres_weight_cache_gb": ("FLOAT", {"default": 4.0, "min": 0.0, "max": 64.0, "step": 0.5, "tooltip": "超分辨率阶段保留在 GPU 的模型权重显存缓存配额（GB，默认 4.0）"}),
                "overlap_frames": (["22", "39"], {"default": "22", "tooltip": "分镜衔接重叠帧数：22 帧（约 0.92 秒，7 个潜变量步长，速度更快）；39 帧（约 1.63 秒，12 个潜变量步长，65 步整音频，动作与声音衔接更平滑自然）"}),
                "unload_between_segments": ("BOOLEAN", {"default": False, "tooltip": "【段间全卸载保底开关】：默认关闭（不卸载模型，模型常驻显存/内存，下个片段零等待全速连续采样）；若开启，每段采样结束后强制全卸载所有模型并清空显存，适合超长片段、极高分辨率或显存极度紧绷的极端保底场景（牺牲速度确保能跑不爆显存）"}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            },
        }

    def execute(
        self,
        model,
        multi_clip_context: MultiClipContext,
        vae,
        sampler,
        sigmas,
        seed: int = 0,
        cfg: float = 1.0,
        sampling_engine: str = "selflift_avatar",
        seed_behavior: str = "increment",
        continuation_mode: str = "hybrid",
        context_noise: float = 0.0,
        shift_video: float = 12.0,
        shift_audio: float = 3.0,
        auto_shift_sigmas: bool = True,
        second_sampling_model=None,
        audio_vae=None,
        negative=None,
        positive=None,
        transition_step: int = 6,
        lowres_scale: float = 0.5,
        rho: float = 0.0,
        w_min: float = 0.5,
        w_max: float = 1.0,
        upscaler_model: str = "none",
        highres_tiling: bool = False,
        tiling_mode: str = "auto",
        tiling_tiles: int = 2,
        tiling_axis: str = "auto",
        highres_tiling_mode: str = "global_stream",
        highres_token_chunk: int = 4096,
        highres_weight_cache_gb: float = 4.0,
        overlap_frames: str = "22",
        unload_between_segments: bool = False,
        unique_id=None,
    ):
        if not isinstance(multi_clip_context, MultiClipContext):
            raise ValueError(f"Expected MultiClipContext, got {type(multi_clip_context)}.")

        clips = multi_clip_context.clips
        if not clips:
            raise ValueError("MultiClipContext contains 0 clips to sample.")

        # Resolve dynamic overlap parameters (22 frames vs 39 frames)
        overlap_n = int(overlap_frames) if str(overlap_frames).isdigit() else 22
        if overlap_n == 39:
            active_carry_tokens = CARRY_TOKENS_39              # 12
            active_carry_frames = CARRY_FRAMES_39              # 39
            active_carry_audio_steps = CARRY_AUDIO_STEPS_39      # 65
            active_audio_context_length = 39                   # 39 frames = 65 audio steps
            stitch_video_trim = 12
            stitch_audio_trim = 65
        else:
            active_carry_tokens = CARRY_TOKENS                 # 7
            active_carry_frames = CARRY_FRAMES                 # 22
            active_carry_audio_steps = CARRY_AUDIO_STEPS       # 36
            active_audio_context_length = 18                   # 18 frames = 30 audio steps
            stitch_video_trim = 7
            stitch_audio_trim = 30

        _LOG.info("=" * 60)
        if len(clips) == 1:
            _LOG.info("[FeiHou ChainSampler] [Stage 2/3] 单分镜模式（1个分镜，以标准单视频方式执行采样，无需片段衔接）")
        else:
            _LOG.info(
                "[FeiHou ChainSampler] [Stage 2/3] 多分镜链式采样（共 %d 个分镜，衔接模式: %s，采样引擎: %s）",
                len(clips), continuation_mode, sampling_engine
            )
        _LOG.info("  * 采样引擎: %s | 基础种子: %d (分配策略: %s)", sampling_engine, seed, seed_behavior)
        _LOG.info(
            "  * 衔接参数: 重叠=%d帧 (%d潜步, %d音步) | 模式=%s | 上下文噪声=%.2f | CFG=%.1f",
            active_carry_frames, active_carry_tokens, active_carry_audio_steps, continuation_mode, context_noise, cfg
        )
        _LOG.info(
            "  * 显存策略: 段间全卸载保底开关=%s (False=模型常驻显存零搬运连续采样; True=每段强制全卸载保底防OOM)",
            unload_between_segments
        )
        _LOG.info("  * 时序频移: 视频时钟Shift=%.1f, 音频时钟Shift=%.1f (自动对齐Sigmas: %s)", shift_video, shift_audio, auto_shift_sigmas)
        _LOG.info("=" * 60)

        # 1. Ensure MiniMax H3 Dual-Clock Flow Matching parameters on models
        model = _patch_h3_dual_clock(model, shift_video=shift_video, shift_audio=shift_audio)
        if second_sampling_model is not None:
            second_sampling_model = _patch_h3_dual_clock(second_sampling_model, shift_video=shift_video, shift_audio=shift_audio)

        # 2. Check and auto-shift schedule if sigmas were generated unshifted
        if auto_shift_sigmas and isinstance(sigmas, torch.Tensor):
            sigmas = _ensure_shifted_sigmas(sigmas, shift_video=shift_video)

        selflift_inst = None
        if sampling_engine == "selflift_avatar":
            cls = _resolve_selflift_avatar_sampler_cls()
            if cls is None:
                raise RuntimeError(
                    "SelfLift-Avatar sampler node is not found in custom_nodes/selflift-Avatar. "
                    "Please install selflift-Avatar or set sampling_engine to 'standard_euler'."
                )
            selflift_inst = cls()
            if highres_tiling and highres_tiling_mode in ("global_stream", "global_ram"):
                model = _ensure_sol_attn(model)
                if second_sampling_model is not None:
                    second_sampling_model = _ensure_sol_attn(second_sampling_model)

        clip_latents: list[dict[str, Any]] = []
        prev_latent: dict[str, Any] | None = None
        total_sample_start = time.perf_counter()

        for idx, clip in enumerate(clips):
            clip_start_time = time.perf_counter()
            # Compute seed for this clip
            if seed_behavior == "increment":
                clip_seed = (seed + idx) & 0xFFFFFFFFFFFFFFFF
            elif seed_behavior == "fixed_all":
                clip_seed = seed
            else:  # random_all
                clip_seed = random.randint(0, 0xFFFFFFFFFFFFFFFF)

            # Check if clip has explicit seed override
            if getattr(clip, "override_seed", False) and getattr(clip, "seed", 0) > 0:
                clip_seed = clip.seed

            # Step 1: Resolve transition_step (Node 2 MultiClip is single source of truth)
            clip_trans_step = getattr(clip, "transition_step", None)
            if clip_trans_step is None:
                clip_trans_step = transition_step

            # Step 2: Resolve total steps and dynamic sigmas
            # Rule: Incoming connected `sigmas` is the authoritative source of truth.
            # Only if this specific clip explicitly checked override_steps=True will it dynamically
            # recalculate its own sigmas schedule.
            clip_has_override = getattr(clip, "override_steps", False)
            clip_desired_steps = getattr(clip, "steps", None) if clip_has_override else None
            current_sigmas_steps = (len(sigmas) - 1) if (sigmas is not None and hasattr(sigmas, "__len__")) else None

            if clip_has_override and clip_desired_steps is not None and clip_desired_steps > 0 and (current_sigmas_steps != clip_desired_steps) and hasattr(model, "get_model_object"):
                _LOG.info(
                    "Clip %d (%s): 启用了分镜独立步数 (%d 步)，覆盖连线输入的 sigmas (%s 步)，正在动态重新计算 H3 调度...",
                    clip.index,
                    clip.name,
                    clip_desired_steps,
                    current_sigmas_steps,
                )
                try:
                    import comfy.samplers
                    ms = model.get_model_object("model_sampling")
                    active_sigmas = comfy.samplers.calculate_sigmas(ms, "simple", clip_desired_steps)
                    active_sigmas = _ensure_shifted_sigmas(active_sigmas, shift_video=shift_video)
                except Exception as exc:
                    _LOG.warning("Could not dynamically recalculate sigmas for clip %d (%s), using connected sigmas: %s", clip.index, clip.name, exc)
                    active_sigmas = sigmas
            else:
                active_sigmas = sigmas

            # Step 3: SelfLift step schedule rule enforcement (total_steps - transition_step >= 2)
            total_active_steps = len(active_sigmas) - 1 if hasattr(active_sigmas, "__len__") else 8
            if sampling_engine == "selflift_avatar" and (total_active_steps - clip_trans_step < 2):
                safe_trans_step = max(1, total_active_steps - 2)
                _LOG.warning(
                    "Clip %d: transition_step (%d) leaves fewer than 2 high-res steps for total steps %d. Auto-adjusting transition_step to %d to preserve sharp detail.",
                    clip.index, clip_trans_step, total_active_steps, safe_trans_step
                )
                clip_trans_step = safe_trans_step

            # Conditioning resolution
            base_cond = getattr(clip, "base_conditioning", None)
            if base_cond is None:
                raise ValueError(f"Clip {clip.index} is missing base_conditioning.")

            # External positive conditioning / BUNNY bridge integration
            if positive is not None:
                bridge_params = _extract_bunny_bridge_params(positive)
                if bridge_params is not None:
                    if idx == 0:
                        _LOG.info(
                            "Clip 1 (%s): 接入 BUNNY H3 Conditioning Bridge (Adapter: %s, Alpha: %.2f, Mode: %s)，应用语义桥增强",
                            clip.name, bridge_params["adapter"], bridge_params["alpha"], bridge_params["magnitude_match"]
                        )
                        base_cond = positive
                    else:
                        _LOG.info(
                            "Clip %d (%s): 自动对当前分镜独立条件动态广播应用 BUNNY H3 语义桥 (Adapter: %s, Alpha: %.2f)...",
                            clip.index, clip.name, bridge_params["adapter"], bridge_params["alpha"]
                        )
                        base_cond = _apply_bunny_bridge_to_conditioning(base_cond, bridge_params)
                else:
                    if len(clips) == 1 or idx == 0:
                        _LOG.info("Clip %d (%s): 使用外部连接的 positive 条件替代内部默认条件", clip.index, clip.name)
                        base_cond = positive

            # Initial latent
            latent_image = getattr(clip, "initial_latent", None)
            if latent_image is None:
                raise ValueError(f"Clip {clip.index} is missing initial_latent.")

            # Continuation handling for clips after the first
            trim_frames = 0
            active_pos_cond = base_cond
            if idx > 0 and prev_latent is not None:
                if continuation_mode in ("latent_carry", "hybrid"):
                    _LOG.info(
                        "Clip %d: applying latent carry-over (%d tokens, %d audio steps, context_noise=%.2f)...",
                        clip.index, active_carry_tokens, active_carry_audio_steps, context_noise
                    )
                    latent_image = _carry_latent(
                        prev_latent,
                        latent_image,
                        carry_tokens=active_carry_tokens,
                        carry_audio_steps=active_carry_audio_steps,
                        context_noise=context_noise,
                    )
                    trim_frames = active_carry_frames

                if continuation_mode in ("motion_context", "hybrid"):
                    _LOG.info(
                        "Clip %d: injecting Motion Context keyframe anchors (video=%d frames, audio=%d frames)...",
                        clip.index, active_carry_frames, active_audio_context_length
                    )
                    active_pos_cond, mc_trim = inject_h3_motion_context(
                        base_cond,
                        prev_latent,
                        context_length=active_carry_frames,
                        audio_context_length=active_audio_context_length,
                    )
                    if not trim_frames:
                        trim_frames = mc_trim

            # Negative conditioning
            active_neg_cond = negative if negative is not None else _zero_out_conditioning(active_pos_cond)

            # Defensive conditioning sanitization against third-party keyframe/ref bugs (e.g. PainterNodes)
            active_pos_cond = sanitize_h3_conditioning(active_pos_cond)
            active_neg_cond = sanitize_h3_conditioning(active_neg_cond)

            _LOG.info(
                "--- [FeiHou ChainSampler] 正在采样分镜 %d/%d (%s) ---",
                idx + 1,
                len(clips),
                clip.name,
            )
            _LOG.info(
                "  * 参数: Seed=%d (覆盖=%s), 总步数=%d, 一采转折=%d, 衔接裁切=%d帧",
                clip_seed,
                getattr(clip, "override_seed", False),
                total_active_steps,
                clip_trans_step,
                trim_frames,
            )

            if sampling_engine == "selflift_avatar" and selflift_inst is not None:
                high_model = second_sampling_model if second_sampling_model is not None else model
                res = selflift_inst.sample(
                    low_res_model=model,
                    positive=active_pos_cond,
                    negative=active_neg_cond,
                    vae=vae,
                    latent_image=latent_image,
                    sampler=sampler,
                    sigmas=active_sigmas,
                    seed=clip_seed,
                    cfg=cfg,
                    transition_step=clip_trans_step,
                    lowres_scale=lowres_scale,
                    rho=rho,
                    w_min=w_min,
                    w_max=w_max,
                    upscaler_model=upscaler_model,
                    high_res_model=high_model,
                    highres_tiling=highres_tiling,
                    tiling_mode=tiling_mode,
                    tiling_tiles=tiling_tiles,
                    tiling_axis=tiling_axis,
                    highres_tiling_mode=highres_tiling_mode,
                    highres_token_chunk=highres_token_chunk,
                    highres_weight_cache_gb=highres_weight_cache_gb,
                    unique_id=unique_id,
                )
                if isinstance(res, dict) and "result" in res:
                    sampled_latent = res["result"][0]
                else:
                    sampled_latent = res[0]
            else:
                # Standard Euler sampling via ComfyUI custom sampler nodes
                if cs is None:
                    raise RuntimeError("comfy_extras.nodes_custom_sampler is not available.")
                guider_fn = getattr(cs.CFGGuider, "execute", getattr(cs.CFGGuider, "get_guider", None))
                guider = guider_fn(model, active_pos_cond, active_neg_cond, cfg)[0]
                if hasattr(cs, "Noise_RandomNoise") and hasattr(cs.Noise_RandomNoise, "get_noise"):
                    noise = cs.Noise_RandomNoise.get_noise(clip_seed)[0]
                elif hasattr(cs, "RandomNoise"):
                    noise = getattr(cs.RandomNoise, "get_noise", getattr(cs.RandomNoise, "execute"))(clip_seed)[0]
                else:
                    noise_cls = getattr(cs, "RandomNoise", getattr(cs, "Noise_RandomNoise", None))
                    noise_fn = getattr(noise_cls, "get_noise", getattr(noise_cls, "execute", None))
                    noise = noise_fn(clip_seed)[0]
                sampler_fn = getattr(cs.SamplerCustomAdvanced, "execute", getattr(cs.SamplerCustomAdvanced, "sample", None))
                res = sampler_fn(noise, guider, sampler, active_sigmas, latent_image)
                sampled_latent = res[0]

            # Offload completed segment latent to CPU immediately to free VRAM for next segment
            cpu_latent = _latent_to_cpu(sampled_latent)
            prev_latent = cpu_latent
            clip_latents.append(cpu_latent)

            clip_elapsed = time.perf_counter() - clip_start_time
            v_part, a_part = unpack_h3_latent(cpu_latent)
            _LOG.info(
                "  * 分镜 %d/%d (%s) 采样完成: 耗时 %.2fs (约 %.1f 分钟) | 视频 Latent Shape=%s (%d steps) | 音频 Latent Shape=%s (%d steps)",
                idx + 1,
                len(clips),
                clip.name,
                clip_elapsed,
                clip_elapsed / 60.0,
                tuple(v_part.shape),
                v_part.shape[2],
                tuple(a_part.shape),
                a_part.shape[-1],
            )

            # Segment memory management
            if idx < len(clips) - 1:
                if unload_between_segments:
                    # 保底模式：每段采样结束强制全卸载所有模型，以“牺牲搬运速度换取 100% 跑通不爆显存”
                    if torch.cuda.is_available():
                        try:
                            import comfy.model_management as mm
                            if hasattr(model, "model"):
                                mm.unload_model_and_clones(model, unload_additional_models=True)
                            if second_sampling_model is not None and second_sampling_model is not model:
                                if hasattr(second_sampling_model, "model"):
                                    mm.unload_model_and_clones(second_sampling_model, unload_additional_models=True)
                            mm.soft_empty_cache()
                            _LOG.info("[FeiHou ChainSampler] 【段间全卸载保底触发】已强制卸载所有模型并清空显存（分镜 %d 完成）。", idx + 1)
                        except Exception as exc:
                            _LOG.debug("Segment forced unload exception: %s", exc)
                        import gc
                        gc.collect()
                else:
                    # 默认高速模式：有用的模型留存在显存/内存中，不卸载模型，避免重复向 GPU 搬运 38.4GB
                    _LOG.info(
                        "[FeiHou ChainSampler] 【高速智能留存】保留模型权重于显存中，跳过段间卸载，下个分镜零搬运直接推理。"
                    )

        # Stitch all sampled latents into a continuous latent (for backward compatibility)
        stitcher = H3LatentStitcher(video_trim_steps=stitch_video_trim, audio_trim_steps=stitch_audio_trim)
        final_latent = dict(stitcher.stitch(clip_latents, trim_overlap=True))
        v_stitched, a_stitched = unpack_h3_latent(final_latent)
        _LOG.info("=" * 60)
        _LOG.info(
            "[FeiHou LatentStitcher] Latent 缝合完毕: 包含 %d 个分镜，最终连续视频 Latent Shape=%s (%d steps)，音频 Latent Shape=%s (%d steps)",
            len(clip_latents),
            tuple(v_stitched.shape),
            v_stitched.shape[2],
            tuple(a_stitched.shape),
            a_stitched.shape[-1],
        )

        # Attach raw individual segment latents and metadata for pixel-space decoding in FeiHouEasyH3VAEDecode
        final_latent["clip_latents"] = clip_latents
        final_latent["feihou_multiclip_meta"] = {
            "clip_count": len(clip_latents),
            "carry_tokens": active_carry_tokens,
            "carry_frames": active_carry_frames,
            "carry_audio_steps": active_carry_audio_steps,
            "overlap_frames": str(active_carry_frames),
            "unload_between_segments": bool(unload_between_segments),
            "continuation_mode": continuation_mode,
            "context_noise": float(context_noise),
            "shift_video": float(shift_video),
            "shift_audio": float(shift_audio),
        }

        # Release transformer weights and empty CUDA cache so VAE Decode has full VRAM available
        if torch.cuda.is_available():
            try:
                import comfy.model_management as mm
                if hasattr(model, "model"):
                    mm.unload_model_and_clones(model, unload_additional_models=True)
                if second_sampling_model is not None and second_sampling_model is not model:
                    if hasattr(second_sampling_model, "model"):
                        mm.unload_model_and_clones(second_sampling_model, unload_additional_models=True)
                mm.soft_empty_cache()
                _LOG.info("[FeiHou ChainSampler] 已卸载全部采样模型与辅助权重并清空显存缓存，让渡 18GB+ 显存供后续 VAE 解码全速使用。")
            except Exception as exc:
                _LOG.debug("Unable to unload model after chain sampling: %s", exc)
            import gc
            gc.collect()

        total_sample_elapsed = time.perf_counter() - total_sample_start
        _LOG.info(
            "[FeiHou ChainSampler] [Stage 2/3] 全部 %d 个分镜采样执行成功！总采样耗时: %.2fs (约 %.1f 分钟)",
            len(clips),
            total_sample_elapsed,
            total_sample_elapsed / 60.0,
        )
        _LOG.info("=" * 60)
        return (final_latent, len(clips))
