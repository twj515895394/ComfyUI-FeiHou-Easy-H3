"""FeiHou Easy H3 Multi-Clip Core Domain Model & Quota Engine.

Manages global assets, clip-specific assets, dynamic capacity deduction,
sequential index offsetting, and prompt cascading for multi-stage long video generation.
"""

from __future__ import annotations

import dataclasses
from typing import Any, Sequence

MAX_IMAGES = 9
MAX_VIDEOS = 3
MAX_AUDIOS = 3


@dataclasses.dataclass(frozen=True)
class MultiClipQuota:
    """Calculates and validates dynamic asset quota for global and clip scopes."""

    global_images: int = 0
    global_videos: int = 0
    global_audios: int = 0
    refmod_count: int = 0  # Each video refmod occupies one global video slot

    def __post_init__(self):
        if self.global_images < 0 or self.global_images > MAX_IMAGES:
            raise ValueError(f"Global images count {self.global_images} must be in [0, {MAX_IMAGES}].")
        total_vid = self.global_videos + self.refmod_count
        if total_vid < 0 or total_vid > MAX_VIDEOS:
            raise ValueError(
                f"Global videos ({self.global_videos}) + RefMod ({self.refmod_count}) = {total_vid} exceeds MAX_VIDEOS ({MAX_VIDEOS})."
            )
        if self.global_audios < 0 or self.global_audios > MAX_AUDIOS:
            raise ValueError(f"Global audios count {self.global_audios} must be in [0, {MAX_AUDIOS}].")

    @property
    def clip_image_capacity(self) -> int:
        return max(0, MAX_IMAGES - self.global_images)

    @property
    def clip_video_capacity(self) -> int:
        return max(0, MAX_VIDEOS - (self.global_videos + self.refmod_count))

    @property
    def clip_audio_capacity(self) -> int:
        return max(0, MAX_AUDIOS - self.global_audios)

    @property
    def clip_image_start_index(self) -> int:
        return self.global_images + 1

    @property
    def clip_video_start_index(self) -> int:
        return self.refmod_count + self.global_videos + 1

    @property
    def clip_audio_start_index(self) -> int:
        return self.global_audios + 1

    def validate_clip_assets(self, clip_index: int, images: int, videos: int, audios: int) -> None:
        if images > self.clip_image_capacity:
            raise ValueError(
                f"Clip {clip_index} has {images} images, exceeding remaining capacity of {self.clip_image_capacity} "
                f"(global used {self.global_images}/{MAX_IMAGES})."
            )
        if videos > self.clip_video_capacity:
            raise ValueError(
                f"Clip {clip_index} has {videos} videos, exceeding remaining capacity of {self.clip_video_capacity} "
                f"(global used {self.global_videos} + RefMod {self.refmod_count}/{MAX_VIDEOS})."
            )
        if audios > self.clip_audio_capacity:
            raise ValueError(
                f"Clip {clip_index} has {audios} audios, exceeding remaining capacity of {self.clip_audio_capacity} "
                f"(global used {self.global_audios}/{MAX_AUDIOS})."
            )


def cascade_prompts(global_prompt: str | None, clip_prompt: str | None) -> str:
    """Cascade global prompt and clip prompt with a newline prefix."""
    g = (global_prompt or "").strip()
    c = (clip_prompt or "").strip()
    if g and c:
        return f"{g}\n{c}"
    return g or c


@dataclasses.dataclass
class MultiClipSpec:
    """Specification of an individual clip segment."""

    index: int
    name: str
    raw_prompt: str
    merged_prompt: str
    images: list[Any] = dataclasses.field(default_factory=list)
    videos: list[Any] = dataclasses.field(default_factory=list)
    audios: list[Any] = dataclasses.field(default_factory=list)
    seconds: float = 8.0
    seed: int = 0
    steps: int = 8
    transition_step: int = 6
    override_steps: bool = False
    override_seed: bool = False
    reference_map: str = ""
    base_conditioning: Any = None
    initial_latent: Any = None


@dataclasses.dataclass
class MultiClipContext:
    """Aggregated container holding the complete multi-clip specification."""

    generation_mode: str
    megapixels: str
    aspect_ratio: str
    global_prompt: str
    clips: list[MultiClipSpec]
    quota: MultiClipQuota
    enable_global: bool = True
    prompt_preview: str = ""

    def __post_init__(self):
        if not self.prompt_preview:
            self.prompt_preview = self._format_preview()

    def _format_preview(self) -> str:
        lines = []
        lines.append("=== FeiHou Easy H3 多分镜展开预览 ===")
        if not self.enable_global:
            lines.append("全局共享: [已关闭]（分镜独立使用提示词与素材，不继承全局内容）")
        lines.append(f"生成模式: {self.generation_mode} | 分辨率: {self.megapixels}M ({self.aspect_ratio})")
        if self.enable_global:
            lines.append(
                f"全局配额: 图 {self.quota.global_images}/{MAX_IMAGES}, "
                f"视 {self.quota.global_videos + self.quota.refmod_count}/{MAX_VIDEOS} (RefMod: {self.quota.refmod_count}), "
                f"音 {self.quota.global_audios}/{MAX_AUDIOS}"
            )
            if self.global_prompt.strip():
                lines.append(f"全局提示词:\n{self.global_prompt.strip()}")
        else:
            lines.append("分镜独立配额: 图 9/9, 视 3/3, 音 3/3")
        lines.append("-" * 40)
        for clip in self.clips:
            lines.append(f"[分镜 {clip.index}: {clip.name}] (时长: {clip.seconds:.1f}s, Seed: {clip.seed}, 步数: {clip.steps}/{clip.transition_step})")
            lines.append(f"合成提示词:\n{clip.merged_prompt}")
            if clip.reference_map.strip():
                lines.append(f"素材映射表:\n{clip.reference_map.strip()}")
            lines.append("-" * 40)
        return "\n".join(lines)
