"""Test runner for FeiHou Easy H3 MultiClip 7-node workflow.

Usage:
    # 1. Health & node check (does NOT queue or run):
    X:/ComfyUI-aki-v2/python/python.exe tools/run_multiclip_test.py --check-only

    # 2. Trigger real inference execution (after ComfyUI restarted):
    X:/ComfyUI-aki-v2/python/python.exe tools/run_multiclip_test.py --run
"""

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

COMFY_HOST = "http://127.0.0.1:8188"
WORKFLOW_PATH = "workflows/feihou_h3_multiclip_7nodes.json"
USER_WORKFLOW_PATH = "X:/ComfyUI-aki-v2/ComfyUI/user/default/workflows/FeiHou_H3_MultiClip_LongVideo_7Nodes.json"


def http_get(endpoint: str, timeout: float = 5.0):
    url = f"{COMFY_HOST}{endpoint}"
    req = urllib.request.Request(url, headers={"User-Agent": "FeiHouTest/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def http_post(endpoint: str, payload: dict, timeout: float = 10.0):
    url = f"{COMFY_HOST}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "FeiHouTest/1.0"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def check_comfyui_health():
    print(f"\n[1/3] 检查 ComfyUI 服务状态 ({COMFY_HOST})...")
    try:
        stats = http_get("/system_stats")
        devices = stats.get("devices", [])
        gpu_name = devices[0].get("name", "Unknown") if devices else "CPU"
        vram_free = devices[0].get("vram_free", 0) / (1024**3) if devices else 0
        vram_total = devices[0].get("vram_total", 0) / (1024**3) if devices else 0
        print(f"  ✓ ComfyUI 在线运行中")
        print(f"  ✓ 设备: {gpu_name}")
        print(f"  ✓ 显存: 空闲 {vram_free:.1f} GB / 总计 {vram_total:.1f} GB")
        return True
    except Exception as exc:
        print(f"  ✗ 无法连接到 ComfyUI: {exc}")
        return False


def check_node_definitions():
    print(f"\n[2/3] 检查新版节点定义与双时钟/续接特性加载状态...")
    try:
        obj_info = http_get("/object_info/FeiHouEasyH3ChainSampler")
        node_def = obj_info.get("FeiHouEasyH3ChainSampler", {})
        opt_inputs = node_def.get("input", {}).get("optional", {})

        has_continuation = "continuation_mode" in opt_inputs
        has_shift_video = "shift_video" in opt_inputs
        has_auto_shift = "auto_shift_sigmas" in opt_inputs

        print(f"  - continuation_mode 续接策略: {'✓ 已加载' if has_continuation else '✗ 未加载（需重启 ComfyUI）'}")
        print(f"  - shift_video 双时钟支持: {'✓ 已加载' if has_shift_video else '✗ 未加载（需重启 ComfyUI）'}")
        print(f"  - auto_shift_sigmas 自动纠偏: {'✓ 已加载' if has_auto_shift else '✗ 未加载（需重启 ComfyUI）'}")

        if not (has_continuation and has_shift_video and has_auto_shift):
            print("\n  [提示] ComfyUI 正在运行旧版内存定义，请先在绘世启动器 (Aki Launcher GUI) 中重启 ComfyUI！")
            return False
        return True
    except Exception as exc:
        print(f"  ✗ 获取节点定义失败: {exc}")
        return False


def build_api_prompt(ui_workflow: dict) -> dict:
    """Build ComfyUI API prompt graph directly from the 7 nodes."""
    nodes = {n["id"]: n for n in ui_workflow["nodes"]}
    prompt = {}

    # Node 1: RemixLoader
    n1 = nodes[1]
    prompt["1"] = {
        "class_type": n1["type"],
        "_meta": {"title": n1["title"]},
        "inputs": {
            "remix_model": n1["widgets_values"][0],
            "text_encoder": n1["widgets_values"][1],
            "video_vae": n1["widgets_values"][2],
            "audio_vae": n1["widgets_values"][3],
            "second_sampling_model": n1["widgets_values"][4],
        },
    }

    # Node 2: MultiClip
    n2 = nodes[2]
    w2 = n2["widgets_values"]
    prompt["2"] = {
        "class_type": n2["type"],
        "_meta": {"title": n2["title"]},
        "inputs": {
            "h3_bundle": ["1", 0],
            "resolution": w2[0] if isinstance(w2, list) else w2["resolution"],
            "aspect_ratio": w2[1] if isinstance(w2, list) else w2["aspect_ratio"],
            "width": int(w2[2] if isinstance(w2, list) else w2["width"]),
            "height": int(w2[3] if isinstance(w2, list) else w2["height"]),
            "seconds": float(w2[4] if isinstance(w2, list) else w2["seconds"]),
            "steps": int(w2[5] if isinstance(w2, list) else w2["steps"]),
            "transition_step": int(w2[6] if isinstance(w2, list) else w2["transition_step"]),
            "global_prompt": w2[7] if isinstance(w2, list) else w2["global_prompt"],
            "multi_clip_data": w2[8] if isinstance(w2, list) else w2["multi_clip_data"],
            "force_offload": bool(w2[9] if isinstance(w2, list) and len(w2) > 9 else w2.get("force_offload", False)),
            "low_vram_streamed_attention": bool(w2[10] if isinstance(w2, list) and len(w2) > 10 else w2.get("low_vram_streamed_attention", False)),
        },
    }

    # Node 3: KSamplerSelect
    n3 = nodes[3]
    prompt["3"] = {
        "class_type": n3["type"],
        "_meta": {"title": n3["title"]},
        "inputs": {
            "sampler_name": n3["widgets_values"][0] if isinstance(n3["widgets_values"], list) else n3["widgets_values"].get("sampler_name", "euler"),
        },
    }

    # Node 4: BasicScheduler
    n4 = nodes[4]
    w4 = n4["widgets_values"]
    prompt["4"] = {
        "class_type": n4["type"],
        "_meta": {"title": n4["title"]},
        "inputs": {
            "model": ["2", 0],
            "scheduler": w4[0] if isinstance(w4, list) else w4["scheduler"],
            "steps": ["2", 6],
            "denoise": float(w4[2] if isinstance(w4, list) and len(w4) >= 3 else (w4[1] if isinstance(w4, list) else w4["denoise"])),
        },
    }

    # Node 5: ChainSampler
    n5 = nodes[5]
    w5 = n5["widgets_values"]
    if isinstance(w5, list):
        if len(w5) == 22 and isinstance(w5[1], str) and w5[1] in ("fixed", "increment", "decrement", "randomize"):
            # New format: 22 items with control_after_generate, transition_step removed from widgets (passed via context)
            inputs_5 = {
                "model": ["2", 0],
                "multi_clip_context": ["2", 2],
                "vae": ["2", 3],
                "sampler": ["3", 0],
                "sigmas": ["4", 0],
                "second_sampling_model": ["2", 1],
                "audio_vae": ["2", 4],
                "seed": int(w5[0]),
                # w5[1] is control_after_generate ("fixed" / "increment")
                "cfg": float(w5[2]),
                "sampling_engine": str(w5[3]),
                "seed_behavior": str(w5[4]),
                "continuation_mode": str(w5[5]),
                "context_noise": float(w5[6]),
                "shift_video": float(w5[7]),
                "shift_audio": float(w5[8]),
                "auto_shift_sigmas": bool(w5[9]),
                "lowres_scale": float(w5[10]),
                "rho": float(w5[11]),
                "w_min": float(w5[12]),
                "w_max": float(w5[13]),
                "upscaler_model": str(w5[14]),
                "highres_tiling": bool(w5[15]),
                "tiling_mode": str(w5[16]),
                "tiling_tiles": int(w5[17]),
                "tiling_axis": str(w5[18]),
                "highres_tiling_mode": str(w5[19]),
                "highres_token_chunk": int(w5[20]),
                "highres_weight_cache_gb": float(w5[21]),
            }
        elif len(w5) >= 23:
            # Format with ComfyUI LiteGraph auto-injected control_after_generate at index 1
            inputs_5 = {
                "model": ["2", 0],
                "multi_clip_context": ["2", 2],
                "vae": ["2", 3],
                "sampler": ["3", 0],
                "sigmas": ["4", 0],
                "second_sampling_model": ["2", 1],
                "audio_vae": ["2", 4],
                "seed": int(w5[0]),
                # w5[1] is control_after_generate ("fixed" / "increment")
                "cfg": float(w5[2]),
                "sampling_engine": str(w5[3]),
                "seed_behavior": str(w5[4]),
                "continuation_mode": str(w5[5]),
                "context_noise": float(w5[6]),
                "shift_video": float(w5[7]),
                "shift_audio": float(w5[8]),
                "auto_shift_sigmas": bool(w5[9]),
                "transition_step": int(w5[10]),
                "lowres_scale": float(w5[11]),
                "rho": float(w5[12]),
                "w_min": float(w5[13]),
                "w_max": float(w5[14]),
                "upscaler_model": str(w5[15]),
                "highres_tiling": bool(w5[16]),
                "tiling_mode": str(w5[17]),
                "tiling_tiles": int(w5[18]),
                "tiling_axis": str(w5[19]),
                "highres_tiling_mode": str(w5[20]),
                "highres_token_chunk": int(w5[21]),
                "highres_weight_cache_gb": float(w5[22]),
            }
        else:
            inputs_5 = {
                "model": ["2", 0],
                "multi_clip_context": ["2", 2],
                "vae": ["2", 3],
                "sampler": ["3", 0],
                "sigmas": ["4", 0],
                "second_sampling_model": ["2", 1],
                "audio_vae": ["2", 4],
                "seed": int(w5[0]),
                "cfg": float(w5[1]),
                "sampling_engine": str(w5[2]),
                "seed_behavior": str(w5[3]),
                "continuation_mode": str(w5[4]),
                "context_noise": float(w5[5]),
                "shift_video": float(w5[6]),
                "shift_audio": float(w5[7]),
                "auto_shift_sigmas": bool(w5[8]),
                "transition_step": int(w5[9]),
                "lowres_scale": float(w5[10]),
                "rho": float(w5[11]),
                "w_min": float(w5[12]),
                "w_max": float(w5[13]),
                "upscaler_model": str(w5[14]),
                "highres_tiling": bool(w5[15]),
                "tiling_mode": str(w5[16]),
                "tiling_tiles": int(w5[17]),
                "tiling_axis": str(w5[18]),
                "highres_tiling_mode": str(w5[19]),
                "highres_token_chunk": int(w5[20]),
                "highres_weight_cache_gb": float(w5[21]),
            }
    else:
        inputs_5 = {
            "model": ["2", 0],
            "multi_clip_context": ["2", 2],
            "vae": ["2", 3],
            "sampler": ["3", 0],
            "sigmas": ["4", 0],
            "second_sampling_model": ["2", 1],
            "audio_vae": ["2", 4],
            **w5,
        }
    prompt["5"] = {
        "class_type": n5["type"],
        "_meta": {"title": n5["title"]},
        "inputs": inputs_5,
    }

    # Node 6: VAEDecode
    n6 = nodes[6]
    w6 = n6["widgets_values"]
    prompt["6"] = {
        "class_type": n6["type"],
        "_meta": {"title": n6["title"]},
        "inputs": {
            "samples": ["5", 0],
            "vae": ["2", 3],
            "audio_vae": ["2", 4],
            "tile_temporal": bool(w6[0] if isinstance(w6, list) else w6.get("tile_temporal", True)),
            "tile_size": int(w6[1] if isinstance(w6, list) else w6.get("tile_size", 27)),
            "overlap": int(w6[2] if isinstance(w6, list) else w6.get("overlap", 5)),
        },
    }

    # Node 7: VideoCombineV2
    n7 = nodes[7]
    w7 = n7["widgets_values"]
    prompt["7"] = {
        "class_type": n7["type"],
        "_meta": {"title": n7["title"]},
        "inputs": {
            "images": ["6", 0],
            "audio": ["6", 1],
            **(w7 if isinstance(w7, dict) else {
                "frame_rate": 24,
                "loop_count": 0,
                "filename_prefix": "video/feihou_h3_multiclip_2.0mp",
                "format": "video/h264-mp4",
                "pix_fmt": "yuv420p",
                "crf": 19,
                "save_metadata": True,
                "trim_to_audio": False,
                "pingpong": False,
                "save_output": True,
            }),
        },
    }

    return prompt


def run_test():
    print(f"\n[3/3] 准备提交长视频测试生成任务...")
    with open(WORKFLOW_PATH, "r", encoding="utf-8") as f:
        ui_wf = json.load(f)

    api_prompt = build_api_prompt(ui_wf)
    print(f"  ✓ 成功将 7 节点 UI 工作流编译为 API 执行图 (含 {len(api_prompt)} 个任务节点)")

    payload = {"prompt": api_prompt}
    try:
        res = http_post("/prompt", payload)
        prompt_id = res.get("prompt_id")
        print(f"  ✓ 任务提交成功！Prompt ID: {prompt_id}")
        print(f"  - 队列号: {res.get('number', 'N/A')}")
        print(f"\n开始监听推理进度 (Ctrl+C 可中断退出监听，后台继续执行)...")

        start_time = time.time()
        while True:
            time.sleep(3.0)
            elapsed = time.time() - start_time
            history = http_get(f"/history/{prompt_id}")
            if prompt_id in history:
                prompt_hist = history[prompt_id]
                status = prompt_hist.get("status", {})
                completed = status.get("completed", False)
                messages = status.get("messages", [])
                outputs = prompt_hist.get("outputs", {})

                if completed:
                    print(f"\n🎉 视频生成完成！总耗时: {elapsed:.1f} 秒")
                    for nid, out_dict in outputs.items():
                        if "Filenames" in out_dict:
                            print(f"  - 最终合成视频: {out_dict['Filenames']}")
                        if "images" in out_dict:
                            print(f"  - 输出帧信息: {out_dict['images']}")
                    break
                else:
                    print(f"  [运行中] 状态: {status.get('status_str', 'processing')} (已耗时 {elapsed:.1f}s)")
            else:
                queue_info = http_get("/queue")
                running = [j[1] for j in queue_info.get("queue_running", [])]
                pending = [j[1] for j in queue_info.get("queue_pending", [])]
                if prompt_id in running:
                    print(f"  [采样/解码中] GPU 正在全速推理中... (已耗时 {elapsed:.1f}s)")
                elif prompt_id in pending:
                    print(f"  [排队等待中] 等待前序任务... (已耗时 {elapsed:.1f}s)")
                else:
                    print(f"  [检查中] 已提交，正在启动... (已耗时 {elapsed:.1f}s)")

    except Exception as exc:
        print(f"  ✗ 提交或执行任务失败: {exc}")


def main():
    parser = argparse.ArgumentParser(description="FeiHou H3 MultiClip Test Runner")
    parser.add_argument("--check-only", action="store_true", help="Only check server and nodes, do not run")
    parser.add_argument("--run", action="store_true", help="Execute the 7-node multiclip workflow")
    args = parser.parse_args()

    print("=" * 65)
    print("  FeiHou Easy H3 多分镜长视频 7 节点极简工作流执行与健康检查工具")
    print("=" * 65)

    healthy = check_comfyui_health()
    if not healthy:
        sys.exit(1)

    nodes_ready = check_node_definitions()

    if args.check_only or not args.run:
        print("\n[状态] 健康与节点检查完成。如需跑图，请在 ComfyUI 重启后使用 --run 参数触发。")
        return

    if not nodes_ready:
        print("\n[警告] 节点尚未热重载，继续运行可能导致新特性不生效。")
        confirm = input("是否确认立即执行？(y/N): ").strip().lower()
        if confirm != "y":
            print("已取消执行。")
            return

    run_test()


if __name__ == "__main__":
    main()
