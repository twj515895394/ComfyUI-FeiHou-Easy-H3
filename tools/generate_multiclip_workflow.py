"""Generate pristine 7-node FeiHou Easy H3 MultiClip workflow for ComfyUI.

Ensures:
1. 100% consistent link IDs, input slots, and output slots.
2. Complete and aligned widget value arrays matching current node definitions.
3. 2.0MP 8-step SelfLift avatar 30s (3 clips) default test configuration.
4. Clean visual grouping and spatial layout for ComfyUI web UI.
"""

import json
import os
import uuid

WORKFLOW_GUID = str(uuid.uuid5(uuid.NAMESPACE_DNS, "feihou-h3-multiclip-7nodes"))

multi_clip_data_obj = {
    "activeTab": "global",
    "enable_global": True,
    "global_prompt": "Masterpiece, cinematic lighting, photorealistic, 4k resolution, high quality, professional color grading, sharp details.",
    "global_media": {"images": [], "videos": [], "audios": []},
    "clips": [
        {
            "index": 1,
            "name": "分镜 1",
            "prompt": "A character walking slowly through a modern minimalist space, cinematic side angle, natural sunlight streaming through high windows.",
            "override_steps": False,
            "override_seed": False,
            "seconds": 10.0,
            "steps": 8,
            "transition_step": 6,
            "seed": 0,
            "media": {"images": [], "videos": [], "audios": []}
        },
        {
            "index": 2,
            "name": "分镜 2",
            "prompt": "Continue smoothly: the camera tracks alongside the character as they pause gracefully, turning toward the window with a thoughtful expression.",
            "override_steps": False,
            "override_seed": False,
            "seconds": 10.0,
            "steps": 8,
            "transition_step": 6,
            "seed": 0,
            "media": {"images": [], "videos": [], "audios": []}
        },
        {
            "index": 3,
            "name": "分镜 3",
            "prompt": "Continue smoothly: the camera slowly pulls back into a wide cinematic view, capturing the expansive architectural space and soft ambient light.",
            "override_steps": False,
            "override_seed": False,
            "seconds": 10.0,
            "steps": 8,
            "transition_step": 6,
            "seed": 0,
            "media": {"images": [], "videos": [], "audios": []}
        }
    ]
}

multi_clip_data_str = json.dumps(multi_clip_data_obj, ensure_ascii=False)

workflow = {
    "id": WORKFLOW_GUID,
    "revision": 1,
    "version": 0.4,
    "last_node_id": 7,
    "last_link_id": 15,
    "nodes": [
        {
            "id": 1,
            "type": "FeiHouEasyH3RemixLoader",
            "pos": [100, 240],
            "size": [400, 240],
            "flags": {},
            "order": 1,
            "mode": 0,
            "inputs": [
                {"name": "first_pass_lora_stack", "type": "LORA_STACK", "link": None},
                {"name": "second_pass_lora_stack", "type": "LORA_STACK", "link": None}
            ],
            "outputs": [
                {
                    "name": "h3_bundle",
                    "type": "MINIMAX_H3_BUNDLE",
                    "links": [1],
                    "label": "h3_bundle"
                }
            ],
            "title": "1. H3 模型加载器",
            "properties": {
                "Node name for S&R": "FeiHouEasyH3RemixLoader"
            },
            "widgets_values": [
                "Minimax/minimax_h3_hybrid_fl2va_ref2va_b25-49-bf16-pruned.safetensors",
                "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
                "minimax_h3_video_vae_fp16.safetensors",
                "minimax_h3_audio_vae_fp32.safetensors",
                "无"
            ]
        },
        {
            "id": 2,
            "type": "FeiHouEasyH3MultiClip",
            "pos": [540, 200],
            "size": [680, 940],
            "flags": {},
            "order": 2,
            "mode": 0,
            "inputs": [
                {"name": "h3_bundle", "type": "MINIMAX_H3_BUNDLE", "link": 1},
                {"name": "refmods", "type": "H3_REF_MODS", "link": None},
                {"name": "lora_stack", "type": "LORA_STACK", "link": None},
                {"name": "second_lora_stack", "type": "LORA_STACK", "link": None}
            ],
            "outputs": [
                {
                    "name": "model",
                    "type": "MODEL",
                    "links": [2, 3],
                    "label": "model"
                },
                {
                    "name": "second_sampling_model",
                    "type": "MODEL",
                    "links": [4],
                    "label": "second_sampling_model"
                },
                {
                    "name": "multi_clip_context",
                    "type": "FEIHOU_MULTI_CLIP_CONTEXT",
                    "links": [5],
                    "label": "multi_clip_context"
                },
                {
                    "name": "vae",
                    "type": "VAE",
                    "links": [6, 11],
                    "label": "vae"
                },
                {
                    "name": "audio_vae",
                    "type": "VAE",
                    "links": [7, 12],
                    "label": "audio_vae"
                },
                {
                    "name": "prompt_preview",
                    "type": "STRING",
                    "links": None,
                    "label": "prompt_preview"
                },
                {
                    "name": "steps",
                    "type": "INT",
                    "links": [15],
                    "label": "steps"
                },
                {
                    "name": "positive",
                    "type": "CONDITIONING",
                    "links": None,
                    "label": "positive"
                }
            ],
            "title": "2. 多分镜素材配置",
            "properties": {
                "Node name for S&R": "FeiHouEasyH3MultiClip",
                "feihou_multi_clip_data": multi_clip_data_str
            },
            "widgets_values": [
                "reference",
                "2.0",
                "16:9",
                1920,
                1080,
                10.0,
                8,
                6,
                multi_clip_data_obj["global_prompt"],
                multi_clip_data_str,
                False,
                False
            ]
        },
        {
            "id": 3,
            "type": "KSamplerSelect",
            "pos": [1160, 80],
            "size": [280, 60],
            "flags": {},
            "order": 3,
            "mode": 0,
            "inputs": [],
            "outputs": [
                {
                    "name": "SAMPLER",
                    "type": "SAMPLER",
                    "links": [8],
                    "label": "SAMPLER"
                }
            ],
            "title": "3. 采样器选择",
            "properties": {
                "Node name for S&R": "KSamplerSelect"
            },
            "widgets_values": [
                "euler"
            ]
        },
        {
            "id": 4,
            "type": "BasicScheduler",
            "pos": [1160, 180],
            "size": [280, 110],
            "flags": {},
            "order": 4,
            "mode": 0,
            "inputs": [
                {"name": "model", "type": "MODEL", "link": 2},
                {"name": "steps", "type": "INT", "widget": {"name": "steps"}, "link": 15}
            ],
            "outputs": [
                {
                    "name": "SIGMAS",
                    "type": "SIGMAS",
                    "links": [9],
                    "label": "SIGMAS"
                }
            ],
            "title": "4. 调度步数",
            "properties": {
                "Node name for S&R": "BasicScheduler"
            },
            "widgets_values": [
                "simple",
                8,
                1.0
            ]
        },
        {
            "id": 5,
            "type": "FeiHouEasyH3ChainSampler",
            "pos": [1480, 160],
            "size": [420, 640],
            "flags": {},
            "order": 5,
            "mode": 0,
            "inputs": [
                {"name": "model", "type": "MODEL", "link": 3},
                {"name": "multi_clip_context", "type": "FEIHOU_MULTI_CLIP_CONTEXT", "link": 5},
                {"name": "vae", "type": "VAE", "link": 6},
                {"name": "sampler", "type": "SAMPLER", "link": 8},
                {"name": "sigmas", "type": "SIGMAS", "link": 9},
                {"name": "second_sampling_model", "type": "MODEL", "link": 4},
                {"name": "audio_vae", "type": "VAE", "link": 7},
                {"name": "negative", "type": "CONDITIONING", "link": None},
                {"name": "positive", "type": "CONDITIONING", "link": None}
            ],
            "outputs": [
                {
                    "name": "latent",
                    "type": "LATENT",
                    "links": [10],
                    "label": "latent"
                },
                {
                    "name": "clip_count",
                    "type": "INT",
                    "links": None,
                    "label": "clip_count"
                }
            ],
            "title": "5. 链式采样器",
            "properties": {
                "Node name for S&R": "FeiHouEasyH3ChainSampler"
            },
            "widgets_values": [
                0,                                       # seed
                "fixed",                                 # control_after_generate (LiteGraph injected combo)
                1.0,                                     # cfg (LOCKED to 1.0)
                "selflift_avatar",                       # sampling_engine
                "increment",                             # seed_behavior
                "hybrid",                                # continuation_mode
                0.0,                                     # context_noise
                12.0,                                    # shift_video (H3双时钟视频)
                3.0,                                     # shift_audio (H3双时钟音频)
                True,                                    # auto_shift_sigmas (自动纠偏简单调度)
                0.5,                                     # lowres_scale (transition_step已移出UI，由Node 2上下文自动传递)
                0.0,                                     # rho
                0.5,                                     # w_min
                1.0,                                     # w_max
                "h3_upscaler_lms_v0.1_fp32.safetensors",  # upscaler_model
                False,                                   # highres_tiling
                "auto",                                  # tiling_mode
                2,                                       # tiling_tiles
                "auto",                                  # tiling_axis
                "global_stream",                         # highres_tiling_mode
                4096,                                    # highres_token_chunk
                4.0,                                     # highres_weight_cache_gb
                "22",                                    # overlap_frames ("22" 或 "39")
                False                                    # unload_between_segments (段间全卸载保底开关)
            ]
        },
        {
            "id": 6,
            "type": "FeiHouEasyH3VAEDecode",
            "pos": [1940, 200],
            "size": [320, 220],
            "flags": {},
            "order": 6,
            "mode": 0,
            "inputs": [
                {"name": "samples", "type": "LATENT", "link": 10},
                {"name": "vae", "type": "VAE", "link": 11},
                {"name": "audio_vae", "type": "VAE", "link": 12}
            ],
            "outputs": [
                {
                    "name": "image",
                    "type": "IMAGE",
                    "links": [13],
                    "label": "image"
                },
                {
                    "name": "audio",
                    "type": "AUDIO",
                    "links": [14],
                    "label": "audio"
                }
            ],
            "title": "6. 视频解码器",
            "properties": {
                "Node name for S&R": "FeiHouEasyH3VAEDecode"
            },
            "widgets_values": [
                True,  # tile_temporal
                27,    # tile_size
                5      # overlap
            ]
        },
        {
            "id": 7,
            "type": "VideoCombineV2",
            "pos": [2300, 200],
            "size": [420, 360],
            "flags": {},
            "order": 7,
            "mode": 0,
            "inputs": [
                {"name": "images", "type": "IMAGE", "link": 13},
                {"name": "audio", "type": "AUDIO", "link": 14}
            ],
            "outputs": [
                {
                    "name": "Filenames",
                    "type": "VHS_FILENAMES",
                    "links": None,
                    "label": "Filenames"
                }
            ],
            "title": "7. 视频输出保存",
            "properties": {
                "Node name for S&R": "VideoCombineV2"
            },
            "widgets_values": {
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "video/feihou_h3_multiclip_2.0mp",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True
            }
        }
    ],
    "links": [
        [1, 1, 0, 2, 0, "MINIMAX_H3_BUNDLE"],
        [2, 2, 0, 4, 0, "MODEL"],
        [3, 2, 0, 5, 0, "MODEL"],
        [4, 2, 1, 5, 5, "MODEL"],
        [5, 2, 2, 5, 1, "FEIHOU_MULTI_CLIP_CONTEXT"],
        [6, 2, 3, 5, 2, "VAE"],
        [7, 2, 4, 5, 6, "VAE"],
        [8, 3, 0, 5, 3, "SAMPLER"],
        [9, 4, 0, 5, 4, "SIGMAS"],
        [10, 5, 0, 6, 0, "LATENT"],
        [11, 2, 3, 6, 1, "VAE"],
        [12, 2, 4, 6, 2, "VAE"],
        [13, 6, 0, 7, 0, "IMAGE"],
        [14, 6, 1, 7, 1, "AUDIO"],
        [15, 2, 6, 4, 1, "INT"]
    ],
    "groups": [
        {
            "id": 1,
            "title": "【第 1 阶段】基础模型与多镜头编排容器",
            "bounding": [50, 120, 1140, 950],
            "color": "#3f2f5f",
            "font_size": 24,
            "locked": False
        },
        {
            "id": 2,
            "title": "【第 2 阶段】H3双时钟调度与链式极速二采缝合",
            "bounding": [1160, 20, 780, 850],
            "color": "#1f3b5f",
            "font_size": 24,
            "locked": False
        },
        {
            "id": 3,
            "title": "【第 3 阶段】对标蓝夕像素级时序因果解码与音视频封装",
            "bounding": [1930, 120, 810, 750],
            "color": "#1f4f3f",
            "font_size": 24,
            "locked": False
        }
    ],
    "config": {},
    "extra": {
        "ds": {
            "scale": 0.85,
            "offset": [-20, -50]
        }
    }
}

# 1. Self-consistency check
nodes_by_id = {n["id"]: n for n in workflow["nodes"]}
links_by_id = {l[0]: l for l in workflow["links"]}

for lid, link in links_by_id.items():
    _, src_id, src_slot, dst_id, dst_slot, ltype = link
    src_node = nodes_by_id[src_id]
    dst_node = nodes_by_id[dst_id]
    src_out = src_node["outputs"][src_slot]
    assert lid in src_out["links"], f"Link {lid} not in src {src_id} out {src_slot}"
    dst_in = dst_node["inputs"][dst_slot]
    assert dst_in["link"] == lid, f"Link {lid} != dst {dst_id} in {dst_slot}"

print(f"Self-consistency check PASSED: {len(links_by_id)} links valid.")

# 2. Output paths
out_paths = [
    "workflows/feihou_h3_multiclip_7nodes.json",
    "workflows/01_h3_multi_clip_long_video_pipeline.json",
    "X:/ComfyUI-aki-v2/ComfyUI/user/default/workflows/FeiHou_H3_MultiClip_LongVideo_7Nodes.json",
    "X:/ComfyUI-aki-v2/ComfyUI/user/default/workflows/01_FeiHou_H3多分镜长视频_7节点工作流.json",
    "X:/ComfyUI-aki-v2/ComfyUI/user/default/workflows/01_h3_multi_clip_long_video_pipeline.json",
]

for p in out_paths:
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(workflow, f, indent=2, ensure_ascii=False)
    print(f"Successfully wrote {p}")

# 3. Generate matching API JSON
api_workflow = {
    "1": {
        "class_type": "FeiHouEasyH3RemixLoader",
        "_meta": {"title": "1. H3 模型加载器"},
        "inputs": {
            "remix_model": "Minimax/minimax_h3_hybrid_fl2va_ref2va_b25-49-bf16-pruned.safetensors",
            "text_encoder": "qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "video_vae": "minimax_h3_video_vae_fp16.safetensors",
            "audio_vae": "minimax_h3_audio_vae_fp32.safetensors",
            "second_sampling_model": "无"
        }
    },
    "2": {
        "class_type": "FeiHouEasyH3MultiClip",
        "_meta": {"title": "2. 多分镜素材配置"},
        "inputs": {
            "h3_bundle": ["1", 0],
            "mode": "reference",
            "resolution": "2.0",
            "aspect_ratio": "16:9",
            "width": 1920,
            "height": 1080,
            "seconds": 10.0,
            "steps": 8,
            "transition_step": 6,
            "global_prompt": multi_clip_data_obj["global_prompt"],
            "feihou_multi_clip_data": multi_clip_data_str,
            "force_offload": False,
            "low_vram_streamed_attention": False
        }
    },
    "3": {
        "class_type": "KSamplerSelect",
        "_meta": {"title": "3. 采样器选择"},
        "inputs": {
            "sampler_name": "euler"
        }
    },
    "4": {
        "class_type": "BasicScheduler",
        "_meta": {"title": "4. 调度步数"},
        "inputs": {
            "model": ["2", 0],
            "scheduler": "simple",
            "steps": ["2", 6],
            "denoise": 1.0
        }
    },
    "5": {
        "class_type": "FeiHouEasyH3ChainSampler",
        "_meta": {"title": "5. 链式采样器"},
        "inputs": {
            "model": ["2", 0],
            "multi_clip_context": ["2", 2],
            "vae": ["2", 3],
            "sampler": ["3", 0],
            "sigmas": ["4", 0],
            "second_sampling_model": ["2", 1],
            "audio_vae": ["2", 4],
            "seed": 0,
            "cfg": 1.0,
            "sampling_engine": "selflift_avatar",
            "seed_behavior": "increment",
            "continuation_mode": "hybrid",
            "overlap_frames": "22",
            "unload_between_segments": False,
            "context_noise": 0.0,
            "shift_video": 12.0,
            "shift_audio": 3.0,
            "auto_shift_sigmas": True,
            "lowres_scale": 0.5,
            "rho": 0.0,
            "w_min": 0.5,
            "w_max": 1.0,
            "upscaler_model": "h3_upscaler_lms_v0.1_fp32.safetensors",
            "highres_tiling": False,
            "tiling_mode": "auto",
            "tiling_tiles": 2,
            "tiling_axis": "auto",
            "highres_tiling_mode": "global_stream",
            "highres_token_chunk": 4096,
            "highres_weight_cache_gb": 4.0
        }
    },
    "6": {
        "class_type": "FeiHouEasyH3VAEDecode",
        "_meta": {"title": "6. 视频解码器"},
        "inputs": {
            "samples": ["5", 0],
            "vae": ["2", 3],
            "audio_vae": ["2", 4],
            "tile_temporal": True,
            "tile_size": 27,
            "overlap": 5
        }
    },
    "7": {
        "class_type": "VideoCombineV2",
        "_meta": {"title": "7. 视频输出保存"},
        "inputs": {
            "images": ["6", 0],
            "audio": ["6", 1],
            "frame_rate": 24,
            "loop_count": 0,
            "filename_prefix": "video/feihou_h3_multiclip_2.0mp",
            "format": "video/h264-mp4",
            "pix_fmt": "yuv420p",
            "crf": 19,
            "save_metadata": True,
            "trim_to_audio": False,
            "pingpong": False,
            "save_output": True
        }
    }
}

api_out_path = "workflows/feihou_h3_multiclip_7nodes.api.json"
with open(api_out_path, "w", encoding="utf-8") as f:
    json.dump(api_workflow, f, indent=2, ensure_ascii=False)
print(f"Successfully wrote {api_out_path}")
