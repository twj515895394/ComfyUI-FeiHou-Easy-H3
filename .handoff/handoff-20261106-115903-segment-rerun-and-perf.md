# 交接快照：长视频性能分析、二采复用与单段重跑方案预研

## 基本元数据

- **交接时间**：2026-11-06 11:59
- **当前分支**：`feat/multiclip-h3`
- **HEAD**：`3ff4b06` perf(h3): reuse first-pass model for the second pass and stop restaging VAEs per segment
- **工作区状态**：干净（本次两处改动已提交）
- **主要模块**：`chain_sampler.py`、`nodes.py`（`MiniMaxH3Bundle.second_sampling_model_for`）、`vae_decoder.py`
- **运行环境**：秋叶 ComfyUI，Python `X:\ComfyUI-aki-v2\python\python.exe`；**禁止自动化重启**，改动需用户在秋叶启动器 GUI 手动重启后生效
- **验证**：`python -m unittest discover tests` → 61 项全部通过

## 主要意图与决策

用户用 `长视频test (Copy).json` 跑完 6 段 × 10 秒、1088×1920 的长视频，总耗时约 76.6 分钟（采样 4223s + 解码 375s），要求从完整日志里判断速度还有没有优化空间，并纠正了我对一采/二采模型关系的误判。

**关键纠正（必须记住）**：这套工作流**不是**两套模型、两套 LoRA。Remix 加载器的“二采模型”选的是“无”，LoRA 全部加在加载器之前的一采口（旁路模式），二采 LoRA 口为空。我最初说“两套 38.4GB 装不下所以必须交接卸载”是错的——两份 patcher 底层是同一份权重，卸载一采等于把共享权重清掉，二采只好重新 stage。

## 核心交付与改动

### 1. 二采复用一采模型（`nodes.py`，`second_sampling_model_for`）

Remix 加载器且二采模型为“无”时，不再 `UNETLoader().load_unet()` 重新加载 38.4GB：

- **二采 LoRA 为空**：直接返回一采 patcher，不挂 `feihou_h3_handoff`，交接时零卸载。日志标志：`二采无独立模型且无二采 LoRA，复用一采模型，跳过一采/二采交接卸载`。
- **二采 LoRA 有值**：`_second_pass_from_first()` 克隆一采 patcher，清空 `patches` 与 `lora`/`bypass_lora` 注入后只打二采 LoRA。克隆共享已加载权重，sol-attn、sage attention、KJNodes chunk 等打在模型对象上的加速补丁跟着走。
- **二采是另一个模型文件**：权重必须重载（两份不同 38GB，47GB 显存装不下，交接卸载保留），但 `_carry_acceleration()` 把一采的 `transformer_options` 和 `object_patches` 复制过去，二采不再是裸模型。

### 2. 解码不再每段清缓存（`vae_decoder.py`）

删掉分段循环里的 `soft_empty_cache()`。smart memory 关闭时它会让 ComfyUI 把两个 VAE 卸掉，导致每段都重新 stage 视频 VAE（4965MB）+ 音频 VAE（576MB），6 段 12 次。现在只 `gc.collect()`，VAE 常驻。预计解码从 375s 降到约 340s。

### 3. 此前已提交、本会话确认生效的修复

- `84bb596`：`chain_sampler.py` 补 `import os` 并缓存 BUNNY 桥运行时模块。本轮日志已验证分镜 2~6 语义桥广播成功，`name 'os' is not defined` 不再出现。
- `0104cce`：连线 `sigmas` 为步数权威源，仅 `override_steps=True` 才重算。

## 踩坑与经验（Gotchas）

1. **`released first-pass transformer` 不等于有两个模型。** 判断依据是交接前后的 `CUDA reserved`：本轮从约 10112 MiB 掉到 1536 MiB，说明权重真被清掉了。`0 models unloaded` 只代表段间全卸载开关没触发，不代表交接没卸载。
2. **一采 `208 patches attached`、二采 `0 patches attached`。** 这 208 个是用户接在一采输出后的加速节点（模型稀疏注意力、注意力后端、Sage Attention、KJNodes chunk）。新加载的二采模型对象看不到它们，所以加速补丁必须显式搬运或通过克隆继承。
3. **“旁路”是 LoRA 计算方式，不是启用开关。** 旁路（`load_bypass_lora_for_models`）保持原权重、前向时额外加 `强度 × LoRA 输出`；常规（`load_lora_for_models`）加载时合并进权重。默认即旁路。挂在一采口的 LoRA 只作用于一采；二采口留空且复用一采模型时，这份 LoRA 会被二采继承。
4. **分镜 4 低模两步异常慢（174s、343s，正常 42~52s）是外部干扰，不是代码问题。** latent 尺寸全程没变，之后两步立刻恢复。重跑前确认机器空闲。
5. **注意力机制**：`_ensure_sol_attn` 在 `selflift_avatar` + `global_stream`/`global_ram` 下把 ComfyUI 原生 sol-attn 打到每个 double block（tau 1.3、topk 0、start_percent 0.2、min_tokens 12288、sink_conditioning exact_kv_and_rows、extra_tokens 256）。已有 `double_block` 补丁则跳过，所以用户手动接的稀疏注意力节点优先。一采二采各挂一次。低 token 步和前 20% 步走密集注意力。

## 验证闭环

- 单测 61 项通过（含真实 BUNNY 桥功能测试 `TestBunnyBridgeRealApply`，断言桥接后张量真的被变换且运行时模块被缓存）。
- **未经真机验证**：二采复用与 VAE 常驻两处改动都在 `3ff4b06`，需要用户重启 ComfyUI 后跑一次才能确认。期望日志：二采前出现“复用一采模型”且不再有 `released first-pass transformer` 紧跟 `38444MB Staged`；解码阶段两个 VAE 只在第一段 stage 一次。

## 未竟任务与下一步计划

**下一个会话的核心议题：单段重跑，避免整条 6 段全量重跑。**

用户原话要点：分段里某段效果不好时不想全部重跑，想讨论是**保存每段 latent 的首尾上下文再单独重跑**，还是**直接用成片的分段视频首尾帧重跑**。

接手者第一步：先把两个方案的机理和代价讲清楚再让用户选，不要直接写代码。分析时需要的事实：

- **衔接机制**：段间靠 latent carry-over（22 帧 = 7 视频潜步 + 36 音频步）加 Motion Context 关键帧锚点（`motion_context_kernel.py` 的 `inject_h3_motion_context`，视频走 `minimax_keyframes`，音频走 `minimax_refs` 以避免 PainterNodes 的 `KeyError: 'latent'`）。重跑第 N 段必须复现第 N-1 段尾部的这 7 潜步 / 36 音步，否则接缝对不上。
- **方案 A（保存 latent 上下文）**：采样时把每段的尾部 latent（视频 7 步 + 音频 36 步）和当时的 conditioning 落盘。重跑时直接作为 carry-over 注入，衔接在潜空间，数学上和原始拼接一致，接缝最干净。代价是要存的不只是尾部——下一段的头部也要能对齐，且 conditioning 含参考图 latent，体积不小。改动落在 `chain_sampler.py` 的段循环末尾。
- **方案 B（视频首尾帧重跑）**：用已解码成片的相邻帧反推。问题是 VAE 解码再编码是有损的，而且音频上下文无法从视频帧恢复，接缝和声画对齐都会比方案 A 差。优势是不需要改采样器、用户手头已有成片就能做。
- **建议倾向**：方案 A 作主路径（接缝无损），方案 B 作为没有保留 latent 时的补救手段。两者不互斥，但要讲清 B 的音轨短板。
- 另外注意重跑必须复用原段的 seed、sigmas、参考素材和语义桥参数，否则即使上下文对齐，画面风格也会漂。

**明确不做**：不改官方 ComfyUI；不自动化重启；CFG 保持 1.0。

## 建议技能（Suggested Skills）

- `minimax-h3-skill-router`：讨论前先确认 H3 latent 网格、帧到潜步的换算是否和 22/39 帧衔接一致。
- `diagnose`：若用户重启后跑出的日志和期望不符，用它定位是复用路径没走到还是 handoff 仍在卸载。
- `grill-me`：单段重跑方案有多个真实取舍（存多少上下文、音频怎么办、重跑入口做成节点还是工作流），适合在动手前把需求问透。
