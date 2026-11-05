"""FeiHou Easy H3 Multi-Clip long video node.

Manages tabbed global and clip-level reference assets, calculates quota chaining,
builds conditioning per clip, and outputs the MultiClipContext for the chain sampler.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import nodes
import torch

try:
    from .multi_clip_core import (
        MAX_AUDIOS,
        MAX_IMAGES,
        MAX_VIDEOS,
        MultiClipContext,
        MultiClipQuota,
        MultiClipSpec,
        cascade_prompts,
    )
except (ImportError, ValueError):
    from multi_clip_core import (
        MAX_AUDIOS,
        MAX_IMAGES,
        MAX_VIDEOS,
        MultiClipContext,
        MultiClipQuota,
        MultiClipSpec,
        cascade_prompts,
    )
MAX_RESOLUTION = 16384

try:
    from .nodes import (
        ASPECT_RATIOS,
        ASPECT_WIDESCREEN,
        RESOLUTIONS,
        RESOLUTION_DEFAULT,
        MiniMaxH3Bundle,
        _MediaInput,
        _as_bool,
        _canvas_dimensions,
        _clone_h3_model_with_memory_features,
        _empty_image_conditioning,
        _frame_length,
        _load_embedded_media,
        _reference_conditioning,
        _trim_reference_video,
        refmod_compat,
    )
except (ImportError, ValueError):
    from nodes import (
        ASPECT_RATIOS,
        ASPECT_WIDESCREEN,
        RESOLUTIONS,
        RESOLUTION_DEFAULT,
        MiniMaxH3Bundle,
        _MediaInput,
        _as_bool,
        _canvas_dimensions,
        _clone_h3_model_with_memory_features,
        _empty_image_conditioning,
        _frame_length,
        _load_embedded_media,
        _reference_conditioning,
        _trim_reference_video,
        refmod_compat,
    )

_LOG = logging.getLogger("feihou_multi_clip")


MODE_REFERENCE = "reference"
MODE_IMAGE = "image"
MODE_TEXT = "text"
GENERATION_MODES = [MODE_REFERENCE, MODE_IMAGE, MODE_TEXT]

_RE_MENTION_VIDEO = re.compile(
    r"@(?:视频|Video)\s*(\d+)(?:\s*[:：]\s*\[?[^\]\s\n,，。！？]+\]?)?",
    re.IGNORECASE,
)
_RE_MENTION_IMAGE = re.compile(
    r"@(?:图|图片|Picture|Image)\s*(\d+)(?:\s*[:：]\s*\[?[^\]\s\n,，。！？]+\]?)?",
    re.IGNORECASE,
)
_RE_MENTION_AUDIO = re.compile(
    r"@(?:音频|Audio)\s*(\d+)(?:\s*[:：]\s*\[?[^\]\s\n,，。！？]+\]?)?",
    re.IGNORECASE,
)


def normalize_prompt_mentions(prompt: str) -> str:
    """Normalize frontend user-facing @ mentions (@视频1, @图1, @音频1, @Video 1, etc.)
    into official MiniMax H3 reference tags (<Video 1>, <Picture 1>, <Audio 1>).
    """
    if not prompt:
        return ""
    p = _RE_MENTION_VIDEO.sub(r"<Video \1>", prompt)
    p = _RE_MENTION_IMAGE.sub(r"<Picture \1>", p)
    p = _RE_MENTION_AUDIO.sub(r"<Audio \1>", p)
    return p


class FeiHouEasyH3MultiClip:
    """Multi-clip long video asset manager and conditioning container."""

    CATEGORY = "FeiHou Easy H3"
    FUNCTION = "generate"
    RETURN_TYPES = ("MODEL", "MODEL", "FEIHOU_MULTI_CLIP_CONTEXT", "VAE", "VAE", "STRING", "INT")
    RETURN_NAMES = ("model", "second_sampling_model", "multi_clip_context", "vae", "audio_vae", "prompt_preview", "steps")
    DESCRIPTION = "Multi-clip long video container with global/clip tabbed asset gallery, automatic quota chaining, and cascaded prompts."

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "h3_bundle": ("MINIMAX_H3_BUNDLE",),
                "mode": (GENERATION_MODES, {"default": MODE_REFERENCE, "tooltip": "生成模式：reference（参考生视频，多模态素材与@引用，调用 ref2va 模型）；image（首尾帧/图生视频，仅需首尾1~2张图片，调用 fl2va 模型）；text（文生视频，纯提示词驱动无需素材，调用 fl2va 模型）"}),
                "resolution": (list(RESOLUTIONS), {"default": RESOLUTION_DEFAULT, "tooltip": "视频分辨率预设（2.0MP 约 1080P/1440P，0.9MP 约 720P，自定义时展开手动宽高输入框）"}),
                "aspect_ratio": (list(ASPECT_RATIOS), {"default": ASPECT_WIDESCREEN, "tooltip": "视频画幅比例预设（16:9, 9:16, 4:3, 1:1 等），选定后自动计算对应像素尺寸"}),
                "width": ("INT", {"default": 1344, "min": 32, "max": MAX_RESOLUTION, "step": 32, "tooltip": "手动指定视频像素宽度（需为 32 的倍数，仅在 resolution 设为 custom 时生效）"}),
                "height": ("INT", {"default": 768, "min": 32, "max": MAX_RESOLUTION, "step": 32, "tooltip": "手动指定视频像素高度（需为 32 的倍数，仅在 resolution 设为 custom 时生效）"}),
                "seconds": ("FLOAT", {"default": 8.0, "min": 1.0, "max": 12.0, "step": 0.1, "tooltip": "全局默认分镜秒数"}),
                "steps": ("INT", {"default": 8, "min": 1, "max": 100, "tooltip": "全局默认总采样步数"}),
                "transition_step": ("INT", {"default": 6, "min": 1, "max": 100, "tooltip": "全局默认一采转折步数"}),
                "global_prompt": ("STRING", {"multiline": True, "dynamicPrompts": True, "default": "", "tooltip": "全局共享提示词，将作为前缀换行自动拼接到各分镜"}),
            },
            "optional": {
                "refmods": ("H3_REF_MODS", {"forceInput": True, "tooltip": "接入 RefMod 将计入全局视频配额，自动占据 Video 1。"}),
                "lora_stack": ("LORA_STACK", {"forceInput": True, "tooltip": "一采 LoRA 堆叠输入"}),
                "second_lora_stack": ("LORA_STACK", {"forceInput": True, "tooltip": "二采高分辨率 LoRA 堆叠输入"}),
                "multi_clip_data": ("STRING", {"default": "{}", "hidden": True}),
                "force_offload": ("BOOLEAN", {"default": False, "tooltip": "采样完成后主动释放显存缓存并清理多余模型"}),
                "low_vram_streamed_attention": ("BOOLEAN", {"default": False, "tooltip": "启用 H3 深度分块流式注意力，大幅降低 DiT 采样峰值显存"}),
            },
        }

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        return float("nan")

    def generate(
        self,
        h3_bundle: MiniMaxH3Bundle,
        resolution: str = RESOLUTION_DEFAULT,
        aspect_ratio: str = ASPECT_WIDESCREEN,
        width: int = 1344,
        height: int = 768,
        seconds: float = 8.0,
        steps: int = 8,
        transition_step: int = 6,
        global_prompt: str = "",
        mode: str = MODE_REFERENCE,
        refmods=None,
        lora_stack=None,
        second_lora_stack=None,
        multi_clip_data: str = "{}",
        force_offload: bool = False,
        low_vram_streamed_attention: bool = False,
        **kwargs,
    ):
        if not isinstance(h3_bundle, MiniMaxH3Bundle):
            raise ValueError("Connect a valid FeiHou Easy H3 Loader bundle.")

        mode_str = str(mode or MODE_REFERENCE).lower().strip()
        if mode_str in {"reference", "参考生视频", "参考生成视频"}:
            normalized_mode = MODE_REFERENCE
        elif mode_str in {"image", "首尾帧", "首/尾帧", "首/尾帧视频", "首尾帧/图生视频", "图生或首尾帧", "图生视频", "i2v", "fl2v"}:
            normalized_mode = MODE_IMAGE
        elif mode_str in {"text", "文生视频", "纯文生视频", "t2v"}:
            normalized_mode = MODE_TEXT
        else:
            normalized_mode = MODE_REFERENCE

        h3_bundle.force_offload_enabled = _as_bool(force_offload)
        if h3_bundle.force_offload_enabled:
            h3_bundle.release_residual_second_sampling_model()

        # Parse multi_clip_data JSON from frontend
        try:
            data = json.loads(multi_clip_data) if isinstance(multi_clip_data, str) and multi_clip_data.strip() else {}
        except Exception as exc:
            _LOG.warning("Failed to parse multi_clip_data JSON (%s), using defaults.", exc)
            data = {}

        enable_global = _as_bool(data.get("enable_global", True))
        effective_global_prompt = global_prompt if enable_global else ""

        global_media = data.get("global_media", {}) if enable_global else {}
        raw_clips = data.get("clips", [])
        if not raw_clips:
            # Default to 1 clip (Clip 1 is mandatory)
            raw_clips = [
                {"index": 1, "name": "分镜 1", "prompt": "", "seconds": seconds, "steps": steps, "transition_step": transition_step},
            ]

        # Process refmods (only valid in reference mode)
        norm_refmods = refmod_compat.normalize_refmods(refmods)
        if norm_refmods and normalized_mode != MODE_REFERENCE:
            raise ValueError("RefMod requires reference mode / 接入 RefMod 后请将模式切换为参考生视频。")
        refmod_data = refmod_compat.present_refmods(norm_refmods, h3_bundle.video_vae) if norm_refmods else None
        refmod_count = len([m for m, _ in norm_refmods if m.kind == "video"]) if norm_refmods else 0

        # Calculate media quotas according to mode and global toggle
        if normalized_mode == MODE_TEXT or not enable_global:
            g_images = []
            g_videos = []
            g_audios = []
        elif normalized_mode == MODE_IMAGE:
            g_images = [img for img in global_media.get("images", []) if str(img).strip()][:2]
            g_videos = []
            g_audios = []
        else:
            g_images = [img for img in global_media.get("images", []) if str(img).strip()]
            g_videos = [vid for vid in global_media.get("videos", []) if str(vid).strip()]
            g_audios = [aud for aud in global_media.get("audios", []) if str(aud).strip()]

        quota = MultiClipQuota(
            global_images=len(g_images),
            global_videos=len(g_videos),
            global_audios=len(g_audios),
            refmod_count=refmod_count,
        )

        # Canvas sizing
        canvas_w, canvas_h = _canvas_dimensions(resolution, aspect_ratio, width, height)

        _LOG.info("=" * 60)
        _LOG.info("[FeiHou MultiClip] [Stage 1/3] 开始分镜提示词与素材条件解析")
        _LOG.info("  * 生成模式: %s | 分辨率: %s (%s, %dx%d)", normalized_mode, resolution, aspect_ratio, canvas_w, canvas_h)
        _LOG.info("  * 全局共享状态: %s", "【已开启】" if enable_global else "【已关闭】（各分镜独立配额与提示词）")
        if enable_global and effective_global_prompt.strip():
            _LOG.info("  * 全局提示词: %s...", effective_global_prompt.strip()[:80].replace("\n", " "))
        _LOG.info(
            "  * 素材配额: 全局已占用 (图=%d, 视=%d, 音=%d, RefMod=%d) | 分镜可用容量 (图=%d, 视=%d, 音=%d)",
            quota.global_images,
            quota.global_videos,
            quota.global_audios,
            quota.refmod_count,
            quota.clip_image_capacity,
            quota.clip_video_capacity,
            quota.clip_audio_capacity,
        )
        _LOG.info("=" * 60)

        # Load global media items
        global_media_items: list[_MediaInput] = []
        for idx, filename in enumerate(g_images, 1):
            val = _load_embedded_media(filename, "image")
            global_media_items.append(_MediaInput(len(global_media_items) + 1, "image", val, media_ordinal=idx))

        vid_start = quota.refmod_count + 1
        for idx, filename in enumerate(g_videos):
            val = _load_embedded_media(filename, "video")
            trimmed_val = _trim_reference_video(val, "")
            global_media_items.append(_MediaInput(len(global_media_items) + 1, "video", trimmed_val, media_ordinal=vid_start + idx))

        for idx, filename in enumerate(g_audios, 1):
            val = _load_embedded_media(filename, "audio")
            global_media_items.append(_MediaInput(len(global_media_items) + 1, "audio", val, media_ordinal=idx))

        clip_specs: list[MultiClipSpec] = []
        for idx, clip_dict in enumerate(raw_clips, 1):
            clip_index = int(clip_dict.get("index", idx))
            clip_name = str(clip_dict.get("name") or f"分镜 {clip_index}").strip()
            raw_prompt = str(clip_dict.get("prompt") or "").strip()
            merged_prompt = cascade_prompts(effective_global_prompt, raw_prompt)

            override_steps = _as_bool(clip_dict.get("override_steps", False))
            override_seed = _as_bool(clip_dict.get("override_seed", False))

            clip_sec = float(clip_dict.get("seconds", seconds)) if override_steps else float(seconds)
            clip_steps = int(clip_dict.get("steps", steps)) if override_steps else int(steps)
            clip_trans_step = int(clip_dict.get("transition_step", transition_step)) if override_steps else int(transition_step)
            clip_seed = int(clip_dict.get("seed", 0))

            clip_media = clip_dict.get("media", {})
            if normalized_mode == MODE_TEXT:
                c_images = []
                c_videos = []
                c_audios = []
            elif normalized_mode == MODE_IMAGE:
                c_images = [img for img in clip_media.get("images", []) if str(img).strip()][:2]
                c_videos = []
                c_audios = []
            else:
                c_images = [img for img in clip_media.get("images", []) if str(img).strip()]
                c_videos = [vid for vid in clip_media.get("videos", []) if str(vid).strip()]
                c_audios = [aud for aud in clip_media.get("audios", []) if str(aud).strip()]

            # Validate against remaining capacity
            quota.validate_clip_assets(clip_index, len(c_images), len(c_videos), len(c_audios))

            clip_length = _frame_length(clip_sec, fps=24.0)

            # Build conditioning and empty latent based on mode
            if normalized_mode == MODE_TEXT:
                conditioning, latent = _empty_image_conditioning(
                    h3_bundle,
                    merged_prompt,
                    canvas_w,
                    canvas_h,
                    clip_length,
                    first_frame=None,
                    last_frame=None,
                )
                try:
                    import node_helpers
                    conditioning = node_helpers.conditioning_set_values(conditioning, {"minimax_frame_count": clip_length})
                except Exception:
                    pass
                ref_map_str = ""

            elif normalized_mode == MODE_IMAGE:
                # Resolve first_frame and last_frame
                first_frame = None
                last_frame = None
                active_imgs = c_images if c_images else (g_images if enable_global else [])
                if len(active_imgs) >= 1 and active_imgs[0]:
                    first_frame = _load_embedded_media(active_imgs[0], "image")
                if len(active_imgs) >= 2 and active_imgs[1]:
                    last_frame = _load_embedded_media(active_imgs[1], "image")

                conditioning, latent = _empty_image_conditioning(
                    h3_bundle,
                    merged_prompt,
                    canvas_w,
                    canvas_h,
                    clip_length,
                    first_frame=first_frame,
                    last_frame=last_frame,
                )
                try:
                    import node_helpers
                    conditioning = node_helpers.conditioning_set_values(conditioning, {"minimax_frame_count": clip_length})
                except Exception:
                    pass

                ref_parts = []
                if first_frame is not None:
                    ref_parts.append("@图1(首帧)")
                if last_frame is not None:
                    ref_parts.append("@图2(尾帧)")
                ref_map_str = ", ".join(ref_parts)

            else:  # MODE_REFERENCE
                # Assemble this clip's local media items with offset ordinals
                clip_media_items: list[_MediaInput] = []
                img_offset = quota.clip_image_start_index
                for i, filename in enumerate(c_images):
                    val = _load_embedded_media(filename, "image")
                    clip_media_items.append(_MediaInput(len(global_media_items) + len(clip_media_items) + 1, "image", val, media_ordinal=img_offset + i))

                vid_offset = quota.clip_video_start_index
                for i, filename in enumerate(c_videos):
                    val = _load_embedded_media(filename, "video")
                    trimmed_val = _trim_reference_video(val, "")
                    clip_media_items.append(_MediaInput(len(global_media_items) + len(clip_media_items) + 1, "video", trimmed_val, media_ordinal=vid_offset + i))

                aud_offset = quota.clip_audio_start_index
                for i, filename in enumerate(c_audios):
                    val = _load_embedded_media(filename, "audio")
                    clip_media_items.append(_MediaInput(len(global_media_items) + len(clip_media_items) + 1, "audio", val, media_ordinal=aud_offset + i))

                all_clip_items = list(global_media_items) + clip_media_items
                clip_has_visual_media = any(it.media_type in {"image", "video"} for it in all_clip_items) or bool(refmod_data)

                effective_prompt = normalize_prompt_mentions(merged_prompt)
                if clip_has_visual_media:
                    conditioning, latent, _ = _reference_conditioning(
                        h3_bundle,
                        effective_prompt,
                        canvas_w,
                        canvas_h,
                        clip_length,
                        ref_image_size="match",
                        items=all_clip_items,
                        refmod_data=refmod_data,
                    )
                else:
                    conditioning, latent = _empty_image_conditioning(
                        h3_bundle,
                        effective_prompt,
                        canvas_w,
                        canvas_h,
                        clip_length,
                        first_frame=None,
                        last_frame=None,
                    )
                    try:
                        import node_helpers
                        conditioning = node_helpers.conditioning_set_values(conditioning, {"minimax_frame_count": clip_length})
                    except Exception:
                        pass

                # Build reference mapping summary
                ref_map_lines = []
                if refmod_data and norm_refmods:
                    for mod_idx, (mod, _) in enumerate(norm_refmods, 1):
                        mod_kind = getattr(mod, "kind", "video")
                        mod_kind_label = "视频" if mod_kind == "video" else ("图" if mod_kind == "image" else "音频")
                        mod_name = getattr(mod, "name", "") or f"mod_{mod_idx}"
                        ref_map_lines.append(f"@{mod_kind_label}{mod_idx}(RefMod:{mod_name})")
                for it in all_clip_items:
                    label = {"image": "图", "video": "视频", "audio": "音频"}.get(it.media_type, it.media_type)
                    ref_map_lines.append(f"@{label}{it.media_ordinal}")
                ref_map_str = ", ".join(ref_map_lines)

            spec = MultiClipSpec(
                index=clip_index,
                name=clip_name,
                raw_prompt=raw_prompt,
                merged_prompt=effective_prompt if normalized_mode == MODE_REFERENCE else merged_prompt,
                images=c_images,
                videos=c_videos,
                audios=c_audios,
                seconds=clip_sec,
                seed=clip_seed,
                steps=clip_steps,
                transition_step=clip_trans_step,
                override_steps=override_steps,
                override_seed=override_seed,
                reference_map=ref_map_str,
                base_conditioning=conditioning,
                initial_latent=latent,
            )
            clip_specs.append(spec)

        if normalized_mode == MODE_REFERENCE:
            any_visual_media = any(
                bool(c.images or c.videos) for c in clip_specs
            ) or bool(global_media_items) or bool(refmod_data)
            model_kind = "ref2va" if any_visual_media else "fl2va"
        else:
            model_kind = "fl2va"

        context = MultiClipContext(
            generation_mode=normalized_mode,
            megapixels=resolution,
            aspect_ratio=aspect_ratio,
            global_prompt=effective_global_prompt,
            clips=clip_specs,
            quota=quota,
            enable_global=enable_global,
        )

        # Build models
        base_model = h3_bundle.model_for(model_kind)
        if lora_stack is not None:
            base_model = h3_bundle._apply_loras(base_model, lora_stack)

        streamed_attention = _as_bool(low_vram_streamed_attention)
        model = _clone_h3_model_with_memory_features(
            base_model,
            force_offload=h3_bundle.force_offload_enabled,
            streamed_attention=streamed_attention,
        )

        second_model = None
        if h3_bundle.second_sampling_enabled:
            second_model = h3_bundle.second_sampling_model_for(model_kind)
            if second_lora_stack is not None:
                second_model = h3_bundle._apply_loras(second_model, second_lora_stack)
            second_model = _clone_h3_model_with_memory_features(
                second_model,
                force_offload=h3_bundle.force_offload_enabled,
                streamed_attention=streamed_attention,
            )

        # Ensure H3 dual-clock sigma shift options are mounted for DiT timestep mapping
        def _apply_h3_flow_options(m):
            if m is None or not hasattr(m, "model_options"):
                return m
            opts = getattr(m, "model_options", {}).get("transformer_options", {}).copy()
            opts["minimax_h3_sigma_shift_video"] = 12.0
            opts["minimax_h3_sigma_shift_audio"] = 3.0
            m.model_options["transformer_options"] = opts
            return m

        model = _apply_h3_flow_options(model)
        if second_model is not None:
            second_model = _apply_h3_flow_options(second_model)

        _LOG.info("[FeiHou MultiClip] [Stage 1/3] 条件解析完成: 共 %d 个分镜，模型调度目标: %s", len(clip_specs), model_kind)
        for c in clip_specs:
            _LOG.info(
                "  - [%s] 时长: %.1fs (%d帧) | 步数: %d (一采转折: %d) | 独立Seed: %s | 提示词: %s%s",
                c.name, c.seconds, _frame_length(c.seconds, fps=24.0), c.steps, c.transition_step,
                str(c.seed) if c.override_seed else "无",
                c.merged_prompt[:50].replace("\n", " "),
                f" | 引用: {c.reference_map}" if c.reference_map else ""
            )
        _LOG.info("=" * 60)
        return (model, second_model or model, context, h3_bundle.video_vae, h3_bundle.audio_vae, context.prompt_preview, int(steps))
