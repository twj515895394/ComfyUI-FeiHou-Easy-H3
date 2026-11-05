# 交接快照：22/39 帧重叠衔接动态切换与段间全卸载保底与显存留存优化 (2026-11-05 20:45:00)

## 1. 任务背景与核心目标
1. **分镜衔接重叠帧动态可选（22 帧与 39 帧）**：
   - 彻底解除 22 帧硬编码限制，在采样器提供 `["22", "39"]` 选项；
   - 采样端（潜变量续接、引导上下文）与解码端（像素空间切除、音频波形裁剪）全链路联动动态切除，通过元数据零配置对齐。
2. **显存/内存留存与全卸载保底开关（“有用的留存，无用的卸载”）**：
   - 解决多段连续采样期间重复从内存向 GPU 搬运 38.4GB 权重造成的严重停顿；
   - 默认高速模式（`unload_between_segments=False`）：分镜采样期间保持模型权重常驻 VRAM/RAM，下个分镜零搬运直接起跑；
   - 新增保底模式（`unload_between_segments=True`）：分镜采样后强制全卸载所有模型，以牺牲速度为代价确保极端分辨率或极长镜头 100% 跑通不爆显存；
   - 全部分镜采样结束后统一卸载 DiT 模型，为 2.0MP 3D VAE 解码让渡 18GB+ 完整显存。

## 2. 关键代码改动
1. **`latent_stitcher.py`**：
   - 扩展支持 22 帧（7 video steps, 30 audio steps）与 39 帧（12 video steps, 65 audio steps）；
   - 提供 `get_h3_trim_steps(overlap_frames)` 辅助函数。
2. **`chain_sampler.py`**：
   - 增加 `overlap_frames` 控件（`["22", "39"]`，默认 `"22"`）；
   - 增加 `unload_between_segments` 控件（`BOOLEAN`，默认 `False`）；
   - 动态计算 22 帧与 39 帧潜变量步长、音频步长和上下文帧数；
   - 采样循环中依据 `unload_between_segments` 开关执行段间策略，将 `carry_frames` 存入 `final_latent["feihou_multiclip_meta"]`。
3. **`vae_decoder.py`**：
   - 移除写死常量，动态读取 `samples["feihou_multiclip_meta"]["carry_frames"]`；
   - 像素视频切除、音频波形切除（22 帧对应 29333 采样点，39 帧对应 52000 采样点）与 CPU 原地预分配全面动态化。
4. **`tools/generate_multiclip_workflow.py`** 与 工作流 JSON：
   - 规范对齐 `widgets_values` 与 API 格式；
   - 保持 15 根连线与 7 节点拓扑一致性，输出至 `user/default/workflows/` 与 `workflows/`。

## 3. 测试验证
- 秋叶 Python 环境下 57 项单元测试 100% 通过（新增 5 项涵盖 39 帧缝合、39 帧像素解码、39 帧潜变量掩码、39 帧链式采样与显存留存/卸载开关断言）。
