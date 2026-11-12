"""FeiHou Easy H3 resumable chain sampler.

The existing chain sampler runs every clip in one pass and is left unchanged.
This node runs a closed segment range, one segment at a time, or assembles
segments that were already sampled. Continuation uses the same latent carry
and motion context as the chain sampler.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import torch

try:
    from .chain_sampler import (
        CARRY_AUDIO_STEPS,
        CARRY_AUDIO_STEPS_39,
        CARRY_FRAMES,
        CARRY_FRAMES_39,
        CARRY_TOKENS,
        CARRY_TOKENS_39,
        FeiHouEasyH3ChainSampler,
        _carry_latent,
        _ensure_shifted_sigmas,
        _ensure_sol_attn,
        _extract_bunny_bridge_params,
        _apply_bunny_bridge_to_conditioning,
        _latent_to_cpu,
        _patch_h3_dual_clock,
        _effective_selflift_lowres_scale,
        _resolve_selflift_avatar_sampler_cls,
        _safe_unpack_av,
        _zero_out_conditioning,
        sanitize_h3_conditioning,
        inject_h3_motion_context,
    )
    from .multi_clip_core import MultiClipContext
    from . import resume_cache
    from .vae_decoder import FeiHouEasyH3VAEDecode
except (ImportError, ValueError):
    from chain_sampler import (
        CARRY_AUDIO_STEPS,
        CARRY_AUDIO_STEPS_39,
        CARRY_FRAMES,
        CARRY_FRAMES_39,
        CARRY_TOKENS,
        CARRY_TOKENS_39,
        FeiHouEasyH3ChainSampler,
        _carry_latent,
        _ensure_shifted_sigmas,
        _ensure_sol_attn,
        _extract_bunny_bridge_params,
        _apply_bunny_bridge_to_conditioning,
        _latent_to_cpu,
        _patch_h3_dual_clock,
        _effective_selflift_lowres_scale,
        _resolve_selflift_avatar_sampler_cls,
        _safe_unpack_av,
        _zero_out_conditioning,
    )
    from motion_context_kernel import inject_h3_motion_context, sanitize_h3_conditioning
    from multi_clip_core import MultiClipContext
    import resume_cache
    from vae_decoder import FeiHouEasyH3VAEDecode

_LOG = logging.getLogger("feihou_resumable_sampler")
FPS = 24.0


def _overlap_plan(overlap_frames: str) -> dict[str, int]:
    if str(overlap_frames) == "39":
        return {
            "frames": CARRY_FRAMES_39,
            "tokens": CARRY_TOKENS_39,
            "audio_steps": CARRY_AUDIO_STEPS_39,
            "audio_context": 39,
        }
    return {
        "frames": CARRY_FRAMES,
        "tokens": CARRY_TOKENS,
        "audio_steps": CARRY_AUDIO_STEPS,
        "audio_context": 18,
    }


def _clip_seed(seed: int, behavior: str, position: int) -> int:
    """Seed by the clip's own index, never by where this run started."""
    import random

    if behavior == "fixed_all":
        return int(seed)
    if behavior == "random_all":
        return random.randint(0, 0xFFFFFFFFFFFFFFFF)
    return (int(seed) + int(position)) & 0xFFFFFFFFFFFFFFFF


def _resolve_range(clips, start_segment: int, end_segment: int, step_mode: bool) -> tuple[list, list[str]]:
    notes: list[str] = []
    if not clips:
        raise resume_cache.ResumeCacheError("多分镜素材配置里没有分镜。")
    ordered = sorted(clips, key=lambda clip: int(clip.index))
    by_index = {int(clip.index): clip for clip in ordered}
    last = max(by_index)
    start = max(1, int(start_segment))
    end = max(1, int(end_segment))
    if end > last:
        notes.append(f"结束段 {end} 超过实际分镜数，已截到第 {last} 段。")
        end = last
    if start > last:
        raise resume_cache.ResumeCacheError(f"起始段 {start} 超过实际分镜数 {last}。")
    if end < start:
        notes.append(f"结束段小于起始段，已对调为第 {end} 段到第 {start} 段。")
        start, end = end, start
    if step_mode:
        end = start
    missing = [n for n in range(start, end + 1) if n not in by_index]
    if missing:
        raise resume_cache.ResumeCacheError(f"分镜组件里没有第 {missing[0]} 段。")
    return [by_index[n] for n in range(start, end + 1)], notes


def _canvas(latent: dict[str, Any]) -> tuple[int, int]:
    video, _audio = _safe_unpack_av(latent)
    return int(video.shape[-1]), int(video.shape[-2])


def _trim_decoded(frames: torch.Tensor, audio: dict[str, Any] | None, carry_frames: int):
    if int(frames.shape[0]) > carry_frames:
        frames = frames[carry_frames:]
    if audio is not None and audio.get("waveform") is not None:
        rate = int(audio.get("sample_rate") or 0)
        trim = max(0, int(round(carry_frames / FPS * rate))) if rate else 0
        if trim and int(audio["waveform"].shape[-1]) > trim:
            audio = dict(audio)
            audio["waveform"] = audio["waveform"][..., trim:]
    return frames.detach().cpu(), audio


def _prepend_preview(frames, audio, previous, seconds: float):
    if previous is None or seconds <= 0:
        return frames, audio
    prev_frames = previous["frames"]
    keep = min(int(prev_frames.shape[0]), max(0, int(round(float(seconds) * FPS))))
    if keep <= 0:
        return frames, audio
    head = prev_frames[-keep:]
    if tuple(head.shape[1:]) != tuple(frames.shape[1:]):
        return frames, audio
    frames = torch.cat([head, frames], dim=0)
    prev_audio = previous.get("audio")
    if audio is not None and prev_audio is not None and prev_audio.get("waveform") is not None:
        rate = int(audio.get("sample_rate") or 0)
        samples = max(0, int(round(keep / FPS * rate))) if rate else 0
        wave = prev_audio["waveform"]
        if samples and int(wave.shape[-1]) >= samples:
            audio = dict(audio)
            audio["waveform"] = torch.cat([wave[..., -samples:], audio["waveform"]], dim=-1)
    return frames, audio


def _concat(parts: list[dict[str, Any]]) -> tuple[torch.Tensor, dict[str, Any] | None]:
    frames = torch.cat([part["frames"] for part in parts], dim=0)
    waves = []
    rate = None
    for part in parts:
        audio = part.get("audio")
        if not audio or audio.get("waveform") is None:
            continue
        rate = rate or int(audio.get("sample_rate") or 0)
        wave = audio["waveform"]
        if rate and int(audio.get("sample_rate") or rate) != rate:
            continue
        waves.append(wave)
    audio_out = {"waveform": torch.cat(waves, dim=-1), "sample_rate": rate} if waves and rate else None
    return frames, audio_out


class FeiHouEasyH3ResumableChainSampler(FeiHouEasyH3ChainSampler):
    """Run, preview and resume one segment range without touching the one-pass sampler."""

    CATEGORY = "FeiHou Easy H3"
    FUNCTION = "execute"
    RETURN_TYPES = ("IMAGE", "AUDIO", "LATENT", "STRING", "STRING")
    RETURN_NAMES = ("frames", "audio", "latent", "report", "segment_info")
    DESCRIPTION = "逐段预览、从某一段续跑，或把已经跑好的各段拼成完整视频。一次跑完请用链式采样器。"

    @classmethod
    def INPUT_TYPES(cls):
        base = FeiHouEasyH3ChainSampler.INPUT_TYPES()
        optional = {
            "start_segment": ("INT", {
                "default": 1, "min": 1, "max": 8,
                "tooltip": "从第几段开始，含本段。逐段预览时只跑这一段。",
            }),
            "end_segment": ("INT", {
                "default": 8, "min": 1, "max": 8,
                "tooltip": "跑到第几段，含本段。大于实际分镜数时截到最后一段。逐段预览时忽略。",
            }),
            "step_mode": ("BOOLEAN", {
                "default": False,
                "tooltip": "只跑起始段并保存，方便看完再决定重跑还是继续。输出是这一段，另带上一段结尾数秒用于看接缝。",
            }),
            "assemble_only": ("BOOLEAN", {
                "default": False,
                "tooltip": "不采样。把缓存里起始段到结束段已经跑好的片段拼成一条视频。缺段会报错。",
            }),
            "cache_key": ("STRING", {
                "default": "default",
                "tooltip": "这组成片的缓存名。同一条视频的逐段、重跑、拼接必须用同一个名字。换重叠帧数或换续接方式时换一个名字。",
            }),
            "reload_tail": ("BOOLEAN", {
                "default": True,
                "tooltip": "起始段大于 1 时，读取上一段的潜空间尾巴来衔接。关掉则这一段当开头，和上一段对不上。",
            }),
            "reset_cache": ("BOOLEAN", {
                "default": False,
                "tooltip": "本次运行前清空这个缓存名下的全部片段和尾巴。只在确定整条重来时打开，用完关掉。",
            }),
            "preview_tail_seconds": ("FLOAT", {
                "default": 2.0, "min": 0.0, "max": 5.0, "step": 0.1,
                "tooltip": "逐段预览时，在当前段前面附上一段结尾多少秒。0 表示只看当前段。只影响预览，不写入缓存。",
            }),
        }
        # Continuation controls stay where the chain sampler defines them, so the
        # shared tooltips are not forked. Resume controls go in front.
        optional.update(base["optional"])
        base["optional"] = optional
        return base

    def execute(
        self,
        model,
        multi_clip_context,
        vae,
        sampler,
        sigmas,
        seed: int = 0,
        cfg: float = 1.0,
        sampling_engine: str = "selflift_avatar",
        seed_behavior: str = "increment",
        start_segment: int = 1,
        end_segment: int = 8,
        step_mode: bool = False,
        assemble_only: bool = False,
        cache_key: str = "default",
        reload_tail: bool = True,
        reset_cache: bool = False,
        preview_tail_seconds: float = 2.0,
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
        cache_dir: str | None = None,
    ):
        del unique_id
        if not isinstance(multi_clip_context, MultiClipContext):
            raise resume_cache.ResumeCacheError("需要连接多分镜素材配置的输出。")
        if abs(float(cfg) - 1.0) > 1e-6:
            _LOG.warning("CFG %.3f 已按 1.0 使用。", float(cfg))
        cfg = 1.0

        plan = _overlap_plan(overlap_frames)
        selected, notes = _resolve_range(
            multi_clip_context.clips, start_segment, end_segment, bool(step_mode) and not assemble_only
        )
        root = resume_cache.cache_root(cache_key, cache_dir)
        if reset_cache:
            resume_cache.reset_cache(root)
            notes.append(f"已清空缓存 {resume_cache.validate_cache_key(cache_key)}。")

        if assemble_only:
            return self._assemble(root, selected, plan, notes, cache_key)

        return self._sample_range(
            root, selected, notes, plan,
            model=model, vae=vae, sampler=sampler, sigmas=sigmas, seed=int(seed),
            sampling_engine=sampling_engine, seed_behavior=seed_behavior,
            reload_tail=bool(reload_tail), preview_tail_seconds=float(preview_tail_seconds),
            step_mode=bool(step_mode), continuation_mode=continuation_mode,
            context_noise=float(context_noise), shift_video=float(shift_video),
            shift_audio=float(shift_audio), auto_shift_sigmas=bool(auto_shift_sigmas),
            second_sampling_model=second_sampling_model, audio_vae=audio_vae,
            negative=negative, positive=positive, transition_step=int(transition_step),
            lowres_scale=float(lowres_scale), rho=float(rho), w_min=float(w_min), w_max=float(w_max),
            upscaler_model=upscaler_model, highres_tiling=bool(highres_tiling),
            tiling_mode=tiling_mode, tiling_tiles=int(tiling_tiles), tiling_axis=tiling_axis,
            highres_tiling_mode=highres_tiling_mode, highres_token_chunk=int(highres_token_chunk),
            highres_weight_cache_gb=float(highres_weight_cache_gb),
            unload_between_segments=bool(unload_between_segments), cache_key=cache_key,
        )

    def _assemble(self, root, selected, plan, notes, cache_key):
        loaded = []
        for clip in selected:
            loaded.append(resume_cache.load_segment(root, int(clip.index)))
        frames, audio = _concat(loaded)
        notes.append(
            f"只拼接缓存 {resume_cache.validate_cache_key(cache_key)} 的第 {selected[0].index} 段到第 {selected[-1].index} 段，"
            f"共 {int(frames.shape[0])} 帧，没有重新采样。"
        )
        info = {
            "mode": "assemble_only",
            "cache_key": resume_cache.validate_cache_key(cache_key),
            "segments": [{"segment": int(c.index), "frames": int(p["frames"].shape[0]), "from_cache": True} for c, p in zip(selected, loaded)],
            "overlap_frames": plan["frames"],
        }
        return self._output(frames, audio, {"samples": torch.zeros(1, 4, 1, 1)}, notes, info)

    def _sample_range(self, root, selected, notes, plan, **kw):
        model = _patch_h3_dual_clock(kw["model"], shift_video=kw["shift_video"], shift_audio=kw["shift_audio"])
        second = kw["second_sampling_model"]
        if second is not None:
            second = _patch_h3_dual_clock(second, shift_video=kw["shift_video"], shift_audio=kw["shift_audio"])
        sigmas = kw["sigmas"]
        if kw["auto_shift_sigmas"] and isinstance(sigmas, torch.Tensor):
            sigmas = _ensure_shifted_sigmas(sigmas, shift_video=kw["shift_video"])

        selflift = None
        if kw["sampling_engine"] == "selflift_avatar":
            cls = _resolve_selflift_avatar_sampler_cls()
            if cls is None:
                raise RuntimeError("找不到 SelfLift-Avatar。安装 selflift-Avatar，或把采样引擎改成 standard_euler。")
            selflift = cls()
            if kw["highres_tiling"] and kw["highres_tiling_mode"] in ("global_stream", "global_ram"):
                model = _ensure_sol_attn(model)
                if second is not None:
                    second = _ensure_sol_attn(second)

        bridge = _extract_bunny_bridge_params(kw["positive"])
        prev = None
        first = selected[0]
        if int(first.index) > 1 and kw["reload_tail"]:
            width, height = _canvas(first.initial_latent)
            prev = resume_cache.load_tail(
                root, int(first.index) - 1,
                width=width, height=height,
                overlap_frames=plan["frames"], continuation_mode=kw["continuation_mode"],
            )
            notes.append(f"已载入第 {int(first.index) - 1} 段的尾巴。")
        elif int(first.index) > 1:
            notes.append("未载入上一段尾巴，这一段当开头处理，接缝对不上。")

        saved = []
        cleared: list[int] = []
        for offset, clip in enumerate(selected):
            sampled, used_seed, carried = self._sample_one(
                clip, prev, model, second, selflift, sigmas, bridge, plan,
                carried=(prev is not None),
                vae=kw["vae"], sampler=kw["sampler"], seed=kw["seed"],
                seed_behavior=kw["seed_behavior"], sampling_engine=kw["sampling_engine"],
                continuation_mode=kw["continuation_mode"], context_noise=kw["context_noise"],
                shift_video=kw["shift_video"], positive=kw["positive"], negative=kw["negative"],
                transition_step=kw["transition_step"], lowres_scale=kw["lowres_scale"],
                rho=kw["rho"], w_min=kw["w_min"], w_max=kw["w_max"],
                upscaler_model=kw["upscaler_model"], highres_tiling=kw["highres_tiling"],
                tiling_mode=kw["tiling_mode"], tiling_tiles=kw["tiling_tiles"],
                tiling_axis=kw["tiling_axis"], highres_tiling_mode=kw["highres_tiling_mode"],
                highres_token_chunk=kw["highres_token_chunk"],
                highres_weight_cache_gb=kw["highres_weight_cache_gb"],
            )
            cpu = _latent_to_cpu(sampled)
            prior_seed = resume_cache.recorded_seed(root, int(clip.index))
            if prior_seed is not None and prior_seed != int(used_seed):
                notes.append(f"第 {clip.index} 段这次的种子 {used_seed} 和上次记录的 {prior_seed} 不同。")
            removed = resume_cache.invalidate_from(root, int(clip.index))
            cleared.extend(n for n in removed if n != int(clip.index) and n not in cleared)

            frames, audio = self._decode(cpu, kw["vae"], kw["audio_vae"])
            if carried:
                frames, audio = _trim_decoded(frames, audio, plan["frames"])
            width, height = _canvas(cpu)
            resume_cache.save_segment(
                root, int(clip.index), frames=frames, audio=audio, seed=int(used_seed),
                width=width, height=height, overlap_frames=plan["frames"],
                continuation_mode=kw["continuation_mode"],
            )
            resume_cache.save_tail(
                root, int(clip.index), latent=cpu, width=width, height=height,
                overlap_frames=plan["frames"], continuation_mode=kw["continuation_mode"],
            )
            saved.append({"segment": int(clip.index), "frames": int(frames.shape[0]), "seed": int(used_seed), "carried": carried})
            notes.append(
                f"第 {clip.index} 段采样完成，种子 {used_seed}，输出 {int(frames.shape[0])} 帧"
                f"{'，已接上一段尾巴' if carried else ''}。"
            )
            prev = cpu
            if kw["unload_between_segments"] and offset < len(selected) - 1:
                notes.append("已按段间全卸载执行。逐段预览只有一段，这个开关不起作用。")

        if cleared:
            notes.append("已清除后续缓存：" + "、".join(f"第 {n} 段" for n in cleared) + "。这些段需要重跑。")
        if kw["step_mode"]:
            nxt = int(selected[0].index) + 1
            notes.append(f"满意后把起始段改成 {nxt} 再跑。不满意就保持起始段不变，改种子或提示词后重跑。")

        output_parts = [resume_cache.load_segment(root, int(clip.index)) for clip in selected]
        frames, audio = _concat(output_parts)
        if kw["step_mode"] and int(selected[0].index) > 1 and kw["preview_tail_seconds"] > 0:
            try:
                previous = resume_cache.load_segment(root, int(selected[0].index) - 1)
            except resume_cache.ResumeCacheError:
                previous = None
            frames, audio = _prepend_preview(frames, audio, previous, kw["preview_tail_seconds"])
            if previous is not None:
                notes.append(f"预览前面附了上一段结尾 {kw['preview_tail_seconds']:.1f} 秒，这段不写入缓存。")

        info = {
            "mode": "step" if kw["step_mode"] else "range",
            "cache_key": resume_cache.validate_cache_key(kw["cache_key"]),
            "segments": saved,
            "cleared": cleared,
            "overlap_frames": plan["frames"],
        }
        return self._output(frames, audio, prev or {"samples": torch.zeros(1, 4, 1, 1)}, notes, info)

    def _sample_one(self, clip, prev, model, second, selflift, sigmas, bridge, plan, *, carried, **kw):
        position = max(0, int(clip.index) - 1)
        clip_seed = _clip_seed(kw["seed"], kw["seed_behavior"], position)
        if getattr(clip, "override_seed", False) and int(getattr(clip, "seed", 0) or 0) > 0:
            clip_seed = int(clip.seed)

        active_sigmas = sigmas
        if getattr(clip, "override_steps", False) and int(getattr(clip, "steps", 0) or 0) > 0 and hasattr(model, "get_model_object"):
            import comfy.samplers
            ms = model.get_model_object("model_sampling")
            active_sigmas = comfy.samplers.calculate_sigmas(ms, "simple", int(clip.steps))
            active_sigmas = _ensure_shifted_sigmas(active_sigmas, shift_video=kw["shift_video"])
        total_steps = len(active_sigmas) - 1 if hasattr(active_sigmas, "__len__") else 8
        trans = getattr(clip, "transition_step", None)
        if trans is None:
            trans = kw["transition_step"]
        if kw["sampling_engine"] == "selflift_avatar" and total_steps - int(trans) < 2:
            trans = max(1, total_steps - 2)

        base = getattr(clip, "base_conditioning", None)
        if base is None:
            raise resume_cache.ResumeCacheError(f"第 {clip.index} 段没有条件。")
        if bridge is not None:
            base = base if int(clip.index) == 1 and kw["positive"] is not None else _apply_bunny_bridge_to_conditioning(base, bridge)
        elif kw["positive"] is not None and int(clip.index) == 1:
            base = kw["positive"]

        latent = getattr(clip, "initial_latent", None)
        if latent is None:
            raise resume_cache.ResumeCacheError(f"第 {clip.index} 段没有初始潜变量。")
        positive = base
        if carried and prev is not None:
            if kw["continuation_mode"] in ("latent_carry", "hybrid"):
                latent = _carry_latent(
                    prev, latent,
                    carry_tokens=plan["tokens"], carry_audio_steps=plan["audio_steps"],
                    context_noise=kw["context_noise"],
                )
            if kw["continuation_mode"] in ("motion_context", "hybrid"):
                positive, _trim = inject_h3_motion_context(
                    base, prev, context_length=plan["frames"], audio_context_length=plan["audio_context"],
                )
        negative = kw["negative"] if kw["negative"] is not None else _zero_out_conditioning(positive)
        positive = sanitize_h3_conditioning(positive)
        negative = sanitize_h3_conditioning(negative)

        if kw["sampling_engine"] == "selflift_avatar":
            effective_scale, target_mp, minimum_scale = _effective_selflift_lowres_scale(
                model, latent, kw["lowres_scale"]
            )
            if effective_scale > float(kw["lowres_scale"]):
                _LOG.info(
                    "第 %d 段：SelfLift 目标画布 %.3f MP，lowres_scale 从 %.3f 自动提高到 %.3f（当前画布下限 %.3f）",
                    clip.index, target_mp, float(kw["lowres_scale"]), effective_scale, minimum_scale,
                )
            res = selflift.sample(
                low_res_model=model, positive=positive, negative=negative, vae=kw["vae"],
                latent_image=latent, sampler=kw["sampler"], sigmas=active_sigmas, seed=int(clip_seed),
                cfg=1.0, transition_step=int(trans), lowres_scale=effective_scale, rho=kw["rho"],
                w_min=kw["w_min"], w_max=kw["w_max"], upscaler_model=kw["upscaler_model"],
                high_res_model=second if second is not None else model, highres_tiling=kw["highres_tiling"],
                tiling_mode=kw["tiling_mode"], tiling_tiles=kw["tiling_tiles"], tiling_axis=kw["tiling_axis"],
                highres_tiling_mode=kw["highres_tiling_mode"], highres_token_chunk=kw["highres_token_chunk"],
                highres_weight_cache_gb=kw["highres_weight_cache_gb"], unique_id=None,
            )
            sampled = res["result"][0] if isinstance(res, dict) and "result" in res else res[0]
        else:
            from comfy_extras import nodes_custom_sampler as cs
            guider = getattr(cs.CFGGuider, "execute", getattr(cs.CFGGuider, "get_guider"))(model, positive, negative, 1.0)[0]
            noise_cls = getattr(cs, "Noise_RandomNoise", getattr(cs, "RandomNoise"))
            noise = getattr(noise_cls, "get_noise", getattr(noise_cls, "execute"))(int(clip_seed))[0]
            sampler_fn = getattr(cs.SamplerCustomAdvanced, "execute", getattr(cs.SamplerCustomAdvanced, "sample"))
            sampled = sampler_fn(noise, guider, kw["sampler"], active_sigmas, latent)[0]
        return sampled, int(clip_seed), carried

    def _decode(self, latent, vae, audio_vae):
        frames, audio = FeiHouEasyH3VAEDecode().decode(latent, vae, audio_vae=audio_vae)
        if not isinstance(frames, torch.Tensor):
            raise resume_cache.ResumeCacheError("解码没有返回画面。")
        return frames.detach().cpu(), audio

    @staticmethod
    def _output(frames, audio, latent, notes, info):
        report = "\n".join(notes)
        _LOG.info("[FeiHou ResumableSampler]\n%s", report)
        return (frames, audio, latent, report, json.dumps(info, ensure_ascii=False, indent=2))
