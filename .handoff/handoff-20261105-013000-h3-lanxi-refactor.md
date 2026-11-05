# 交接快照：H3多分段架构对标蓝夕重构与全链路显存/内存优化

- **交接时间**：2026-11-05 01:30:00
- **当前分支**：`main`
- **对应 Commit**：`8de6503` (当前工作区存在未提交优化修改)
- **主要涉及模块**：
  - `chain_sampler.py`（链式分段采样与潜空间续接）
  - `vae_decoder.py`（时序因果分段无损解码与流式拼合）
  - `multi_clip_node.py`（多分镜素材大组件双时钟注入）
  - `tests/test_vae_decoder.py`、`tests/test_chain_sampler.py`、`tests/test_end_to_end_multiclip.py`

---

## 1. 用户主要意图与核心技术决策

### 1.1 用户核心痛点
用户反馈在使用简化多分镜工作流生成 2.0MP 高清视频时，画质明显劣于其日常使用的 1.0MP 基础工作流（出现模糊、涂抹感、黑色横条纹与相位失真）。
用户明确指令参考 `X:\ComfyUI-aki-v2\ComfyUI\custom_nodes\ComfyUI-MiniMaxH3-lanxi`（蓝夕版）的设计逻辑，针对**分段采样**、**潜空间续接**、**音视频解码与拼接**进行重构优化，并重点强化多达 8 分段高负荷场景下的**显存（VRAM）与内存（RAM）**保护。

### 1.2 关键技术决策与对标 `lanxi`
1. **潜空间拼接 vs. 像素空间裁切（核心画质修复）**：
   - **痛点根因**：MiniMax H3 的 3D 时序因果 VAE 是以每 5 个 token（17 帧，重叠 1 token）进行因果 chunk 卷积解码。旧方案在潜空间强行切掉 7 个 token 进行 `torch.cat` 拼接成单一超长潜变量后再喂给 VAE，直接撕裂了因果卷积感受野和边缘 Padding，造成全片相位重影与模糊。
   - **决策**：严格对标 `lanxi` 的 `decode_av_latent` 与像素空间裁切：每个分镜头潜变量保持原生独立形态，由 VAE 独立解码出完整帧，随后在**像素空间（Pixel Space）**无损裁掉续接重叠的 22 帧（`frames = frames[22:]`），音频在波形空间裁剪采样点。
2. **H3 双时钟 Flow-Matching 调度纠偏（细节形成修复）**：
   - MiniMax H3 是非线性双时钟模型（`shift_video=12.0`, `shift_audio=3.0`）。普通 `BasicScheduler` 若未加偏移，线性采样步长会在 1 步之内跳过构建宏观骨架与超清细节最关键的 $1.0 \to 0.80$ 阶段。
   - **决策**：在模型和 `transformer_options` 挂载 `minimax_h3_sigma_shift_video = 12.0` 与 `minimax_h3_sigma_shift_audio = 3.0`，并在采样器中内置 `_ensure_shifted_sigmas` 自动识别并纠偏未偏移的线性调度。
3. **潜空间直通续接（`_carry_latent`）与单通道遮罩**：
   - 上一分段末尾 7 个视频潜变量 token 与 36 个音频步直接嵌入下一分段初始潜变量头部，并附带单通道 `noise_mask`（前 7 个 token 固定在 $\sigma=0$）。
4. **8 分段多镜头内存与显存全链路治理**：
   - **显存隔离**：每段采样结束立即 `_latent_to_cpu` 转存主机内存，段间强制 `soft_empty_cache()` 与 `gc.collect()`，显存占用恒定在单段水平。
   - **跨阶段显存让渡**：链式采样结束后、进入 VAE 解码前，主动调用 `unload_model_and_clones` 彻底卸载 18GB DiT 权重，为 2.0MP 3D VAE 留出完整显存。
   - **消除 85GB 内存翻倍峰值**：解码阶段采用 CPU 原地流式预分配写入（`assembled_frames`），写完一段立即销毁单段临时缓冲，彻底避免 `torch.cat` 在 8 段 2.0MP 场景下需要 85GB 内存峰值导致系统卡死的隐患。

---

## 2. 核心交付与代码改动

| 文件 | 核心改动 |
|------|----------|
| `chain_sampler.py` | 1. 引入 `_patch_h3_dual_clock`，挂载 `minimax_h3_sigma_shift_video/audio` 与 `ModelSamplingAV`；<br>2. 增加 `_ensure_shifted_sigmas` 自动纠正线性调度步数；<br>3. 增加 `_carry_latent` 与单通道 `noise_mask` 冻结机制；<br>4. 增加 `_latent_to_cpu`，段间强制显存回收；<br>5. 采样结束前主动卸载 DiT 模型让渡显存给 VAE；<br>6. 输出字典附带 `clip_latents` 与完整元数据。 |
| `vae_decoder.py` | 1. 检测 `clip_latents`，进入多分段独立无损解码分支；<br>2. 实施像素空间 22 帧无损去重裁切与波形空间音频精确对齐裁切；<br>3. 增加 CPU 原地流式预分配写入，消除 8 段拼接时的 2x 内存翻倍；<br>4. 解码各段后立即销毁 GPU 潜变量并回收显存；<br>5. 保留对旧版或单段潜变量的完全向下兼容。 |
| `multi_clip_node.py` | 在输出 `model` 与 `second_model` 时预置 `minimax_h3_sigma_shift_video = 12.0` 与 `shift_audio = 3.0`，使下游 BasicScheduler 自动识别 H3 时钟。 |
| `tests/test_vae_decoder.py` | 增加像素空间 22 帧裁切测试以及 8 分段流式预分配内存优化专项测试。 |
| `tests/test_chain_sampler.py` | 增加 `_ensure_shifted_sigmas` 曲线纠偏与 `_carry_latent` 潜变量遮罩赋值专项测试。 |
| `tests/test_end_to_end_multiclip.py` | 更新端到端断言为 4 镜头独立 VAE 解码与 258 帧（81 + 3×59）像素级对齐。 |

---

## 3. 踩坑与经验（Gotchas）

1. **MagicMock 自生属性干扰 `vae_decode_audio`**：
   - 在单元测试中，若 `audio_vae` 为 `MagicMock()`，`comfy_extras.nodes_audio.vae_decode_audio` 会读取 `audio_vae.audio_sample_rate_output`。由于 mock 机制，该访问会返回一个新的 `MagicMock` 实例而非预设的整数采样率。
   - **解法**：在 `vae_decoder.py` 的 `_decode_single_audio` 中优先判断 `audio_sample_rate` 是否为具体 `int`，优先走原生通道避免 mock 属性自生干扰。
2. **纯视频（Video-only）潜变量防御**：
   - 某些工作流或测试用例的 `initial_latent` 可能只提供单一视频 Tensor `[1, 16, T, H, W]` 而无音频流。
   - **解法**：实现 `_safe_unpack_av`，在单一流输入时安全解包为 `(video, None)`，`_carry_latent` 自动生成对应的单流遮罩，避免解包越界。
3. **8 分段下 `torch.cat` 的系统内存暴击**：
   - 8 段 10 秒 2.0MP 视频的总像素体积超 42GB，`torch.cat` 需要两倍常驻内存（原列表 + 新拼张量 = 85GB）。必须在解码完第 1 段拿到尺寸后预分配全尺寸输出张量，后续各段切片直接写入并立即销毁单段缓冲。

---

## 4. 验证闭环

- **运行环境**：专用 ComfyUI Python（`X:\ComfyUI-aki-v2\python\python.exe`）
- **门禁测试**：
  ```bash
  X:/ComfyUI-aki-v2/python/python.exe -m unittest discover -s tests
  ```
- **测试结果**：**43 项测试全部通过**（`Ran 43 tests in 12.007s - OK`），覆盖单段一采/二采、多段像素裁切、双时钟调度、8段流式内存分配与端到端流转。
- **运行边界合规**：未触发任何在线 GPU 推理任务，未自动重启 ComfyUI 服务。

---

## 5. 未竟任务与下一步计划

1. **用户重启 ComfyUI**：
   - 提示用户通过 **绘世启动器 (Aki Launcher GUI)** 手动重启 ComfyUI，使新代码生效。
2. **下一步 GPU 实际生成验证**（待用户重启并明确授权后）：
   - 使用修复后的 7 节点多镜头工作流（`workflows/feihou_h3_multiclip_7nodes.json`）测试 2.0MP 8 步二采（例如 3 段维密走秀，共 30 秒）。
   - 抽帧质检：确认人物面部、衣服高频纹理是否恢复锐利无损，分镜头衔接处是否有黑花条纹或重影。
3. **分镜参考视频（Ref2VA）后续支持**：
   - 用户提到“参考生视频明天再测”，后续可在分镜头大组件中验证带参考视频/参考音频的复杂混合生成。

---

## 6. 建议技能（Suggested Skills）

- `minimax-h3-skill-router`：编写多分镜头影视级剧本、多景别调度与运镜描述词。
- `diagnose`：在用户反馈生成结果有异常时辅助定位显存与执行日志。
