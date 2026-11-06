# 当前交接索引 (Current Handoff)

> **最新会话交接：** [handoff-20261106-115903-segment-rerun-and-perf.md](./handoff-20261106-115903-segment-rerun-and-perf.md)（接手者必读）

- **最近核实**：2026-11-06 11:59
- **分支 / HEAD**：`feat/multiclip-h3` @ `3ff4b06`，工作区干净
- **当前大阶段**：长视频性能优化已落地（待真机验证）；下一会话转入「单段重跑」方案设计，**先讨论清楚再写代码**
- **运行约束**：秋叶 Python `X:\ComfyUI-aki-v2\python\python.exe`；禁止自动化重启 ComfyUI，改动后须提示用户在秋叶启动器 GUI 手动重启；不改官方 ComfyUI；CFG 恒为 1.0
- **当前状态**：
  1. **连线 sigmas 绝对权威性与 SelfLift 二采步数对齐**：
     - 修复 `chain_sampler.py` 中误用节点 2 默认步数（8 步）强行覆盖外部连线传入的自定义 sigmas（如 10 步）的问题；
     - 确立清晰权威原则：连入 Node 5 `sigmas` 端口的时间步调度具备最高优先级，仅在分镜显式勾选 `override_steps=True` 时才触发动态重算；
     - SelfLift 架构在 10 步 sigmas 下精准分配：一采（低模）6 步，二采（高模）$10 - 6 = 4$ 步。
  2. **BUNNY H3 Conditioning Bridge（语义桥）双模协同接入**：
     - `multi_clip_node.py` 末尾挂载 `positive` (CONDITIONING) 输出端口；
     - `chain_sampler.py` 末尾挂载 `positive` (CONDITIONING) 输入端口，内置 `bunny_h3_bridge` 元数据探测器与多分镜自动广播机制；
     - 单分镜模式直通语义桥，多分镜模式各分镜独立提示词与素材引用 100% 保全的同时自动应用同款语义桥转换。
  3. **正负向 Condition 链路闭环**：
     - 用户可在画布上直接连接 `Node 2 (positive)` -> `ZeroOutConditioning` -> `Node 5 (negative)`，或依赖 Node 5 底层内置的自动条件零化兜底。
  4. **节点 2 UI 自适应与提示词视野扩容**：
     - 彻底消除底部 400px 大片灰色留白：容器自适应高度与 `node.size[1]` 联动，并在 `onConfigure` 与 `onResize` 实时同步；
     - 提示词文本框高度从 110px 提升至 150px，行数扩展至 6 行；
     - 强化消除原生 `global_prompt` 幽灵输入框，标签栏上方干净平整。
  5. **测试验证**：60 项单元测试 100% 全部通过。
- **下阶段核心待办**：用户在秋叶启动器中重启 ComfyUI，体验扩容后的 UI 界面，并在画布上连接 BUNNY H3 语义桥或零化条件进行长视频生成质检。

---

## 核心进展归档（倒序）

### 迭代 8（2026-11-06 11:59）：6 段全量跑性能分析、二采复用一采、解码 VAE 常驻

1. **二采不再重复加载 38.4GB**（`nodes.py`，`3ff4b06`）：确认用户工作流是单模型单 LoRA 堆（二采模型=“无”，LoRA 加在加载器前）。`second_sampling_model_for` 在二采模型为空时改为复用一采 patcher——二采 LoRA 为空直接返回，有值则克隆并只换 LoRA 补丁，sol-attn / sage attention / KJNodes 等加速补丁随克隆继承；二采为独立模型文件时仍重载，但用 `_carry_acceleration` 复制一采的非 LoRA 补丁。
2. **解码不再每段清缓存**（`vae_decoder.py`）：移除分段循环内 `soft_empty_cache()`，避免视频+音频 VAE 每段重新 stage（6 段 12 次）。
3. **真机日志确认**：语义桥 `os` NameError 修复生效，分镜 2~6 广播成功；段间留存开关生效（`0 models unloaded`），但交接卸载是另一条路径，已由本次修复处理。
4. **注意力接法已向用户说明**：`_ensure_sol_attn` 打 ComfyUI 原生 sol-attn 到每个 double block，已有补丁则跳过，一采二采各挂一次。
5. **61 项单测通过**。二采复用与 VAE 常驻两处改动**尚未真机验证**，需重启后看日志确认。

### 迭代 7（2026-11-05 23:25:00）：sigmas 连线权威性修复与 SelfLift 步数精准分配
1. **根因定位与修复**：
   - 原逻辑无条件比对 `clip.steps`（节点 2 默认 8 步）与连线 `sigmas` 步数（10 步），由于 $8 \neq 10$，误判为“分镜步数与输入不符”，进而调用 `calculate_sigmas` 重新生成了 8 步 simple 调度，导致二采被锁死在 $8 - 6 = 2$ 步；
   - 现增加 `clip_has_override = getattr(clip, "override_steps", False)` 守卫，只有分镜显式勾选覆盖步数时才重算，默认连线 `sigmas` 100% 直通。
2. **测试验证**：
   - 新增 `test_incoming_sigmas_authority` 单元测试，全套 60 项单测 100% 通过。

### 迭代 6（2026-11-05 21:40:00）：BUNNY H3 语义桥协同广播、Condition 端口暴露与 UI 留白高度优化
1. **Condition 端口向后兼容暴露**：
   - 在 `multi_clip_node.py` 的 `RETURN_TYPES` 末尾追加 `positive`（第 8 个端口，Slot 7），输出当前激活/第 1 分镜的完整 Conditioning；
   - 在 `chain_sampler.py` 的 `INPUT_TYPES["optional"]` 末尾追加 `positive` 输入端口（Slot 8），确保已有工作流（如 `长视频test.json`）端口连线零漂移。
2. **BUNNY H3 语义桥元数据探测与多镜头动态广播**：
   - 探测传入 `positive` 中的 `bunny_h3_bridge` 元数据标记；
   - 分镜 1 直通增强结果，分镜 2..N 自动对各自独立的 `clip.base_conditioning` 应用同款语义桥转换（提取 adapter、alpha、magnitude_match 配置）；
   - 兼顾画布直观连线调节与多分镜各自独立提示词与素材引用的完美保全。
3. **节点 2 前端高度自适应与提示词扩容**：
   - `.fh-mc-container` 默认 `max-height` 提升至 720px，并在 `onConfigure` 与 `onResize` 动态计算 `node.size[1] - 225px`，消除底部留白；
   - `.fh-mc-prompt-input` 最小高度提升至 140px，默认高度 150px，行数设为 6 行；
   - 彻底隐藏原生 `global_prompt` textarea，避免露头残存。
4. **59 项单测全部通过**。

### 迭代 5（2026-11-05 20:45:00）：22/39 帧重叠衔接动态切换与段间全卸载保底开关
1. **22/39 帧重叠衔接全链路动态化**：
   - 采样端在 `chain_sampler.py` 增加 `overlap_frames` 控件（`["22", "39"]`，默认 `"22"`），动态计算 7/12 潜步与 36/65 音步；
   - 解码端在 `vae_decoder.py` 动态读取 `samples["feihou_multiclip_meta"]["carry_frames"]`，视频像素与音频波形（32kHz 下 29,333 vs 52,000 采样点）精准裁切。
2. **段间全卸载保底开关与智能显存留存**：
   - 增加 `unload_between_segments` 控件（默认 `False`）；
   - 默认模式下分镜间保留 DiT 权重于显存中，避免每个分镜重复耗费数十秒从内存加载 38.4GB 模型；
   - 保底模式开启时每段采样后彻底卸载所有模型清空显存，牺牲速度保证超长片段跑通不爆显存；
   - 全部分镜采样完毕后统一卸载 DiT 模型，为 2.0MP 3D VAE 解码让渡 18GB+ 完整显存。
3. **57 项单元测试全部通过**。

### 迭代 4（2026-11-05 19:15:00）：第三方 PainterNodes 猴子补丁冲突规避与潜变量续接修复
1. **KeyError: 'latent' 根因定位与本插件单边兼容治理**：
   - 报错源自 `ComfyUI-PainterNodes` 的 `PainterMiniMaxFL2VA.py` 对 `MiniMaxH3.extra_conds` 进行了全局猴子补丁。其代码在合并条件时假定所有 keyframe 均带视频潜变量（直接执行 `[kf["latent"] for kf in keyframes]`）；当分镜间注入纯音频上下文锚点（仅含 `audio_latent`）且分镜同时携带参考素材（`refs`）时，直接触发 `KeyError: 'latent'`。
   - 在 `motion_context_kernel.py` 中重构音频上下文注入：严格保持 `minimax_keyframes` 仅存放具备 `"latent"` 的视频关键帧，音频上下文按照 MiniMax H3 底层标准封装为 `minimax_refs`（`{"kind": "audio", "ref_audio_t": ..., "audio_latent": ...}`），完美避开 PainterNodes 的未加判断遍历，同时兼顾原生 H3 音频对齐与特征提取。
   - 新增 `sanitize_h3_conditioning` 条件防卫净化器并在 `chain_sampler.py` 采样前对正负条件进行统一清洗拦截，自动将任何无 `"latent"` 键的音频帧合规迁移至 `minimax_refs`。
2. **Latent Carry-over 潜空间续接覆写 Bug 修复**：
   - 修复 `chain_sampler.py` 在执行完 `_carry_latent` 后多余的重复读取代码，确保各分镜间的 7 tokens 潜变量续接与单通道 `noise_mask` 准确注入采样器。
3. **测试套件全面验证**：
   - 更新并新增 PainterNodes 兼容仿真测试，52 项单元测试 100% 通过。

### 迭代 3（2026-11-05 18:00:00）：RefMod 连线识别、@ 菜单注入、素材编号顺延与 Prompt 规范化
1. **RefMod 探测与目录缓存**：
   - 创建 `web/modules/refmod_helper.js`，实现 `refmodsInputIsConnected` 连线检查，递归穿透 `Reroute`、`SetNode` / `GetNode` 虚拟连线定位源节点；
   - 异步防抖拉取 `/feihou_easy_h3/refmods` 接口获取 RefMod 成员的视频/图片/音频类型与名称。
2. **@ 菜单注入与序号顺延**：
   - 在 `web/modules/mention_menu.js` 中将 RefMod 资产置顶，分配 `@视频1` 并展示紫色 RefMod 徽章；
   - 本地全局视频与分镜私有视频自动向后顺延起始编号（如 `@视频2`、`@视频3`）；
   - 画廊区视频配额标签动态显示 `视 (已占 X/3, 含RefMod)`。
3. **主入口生命周期联动**：
   - 在 `web/feihou_easy_h3_multi_clip.js` 中增加 `onConnectionsChange` 监听 `refmods` 端口变动，动态刷新目录并重新构建 UI。
4. **后端 Prompt 标签转换**：
   - 在 `multi_clip_node.py` 中引入 `normalize_prompt_mentions`，将 `@视频1: [name]` 或 `@视频1` 透明替换为 MiniMax H3 底层标准 `<Video 1>`，确保通过 `refmod_compat.validate_reference_tags` 校验及 CLIP Tokenizer 编码。

### 迭代 2（2026-11-05 17:00:00）：多分镜大组件模块化、全局开关、外观优化与排查日志
1. **全局共享素材与提示词开关**：
   - 增加交互式切换开关。关闭时各分镜完全独立运行，不继承全局提示词，各分镜享有独立的满额配额（9图、3视频、3音频），从 `@图1`、`@视频1`、`@音频1` 开始独立编号。
2. **分镜 1 默认强制常驻与单分镜普通视频模式**：
   - “分镜 1”必须始终存在且不可删除；若用户仅保留 1 个分镜，整条工作流自动按标准单视频流水线执行，无拼接裁切开销。
3. **前端 JS 模块化拆分（SRP 治理）**：
   - 将原单个 1874 行庞大文件拆分至 `web/modules/`（`styles.js`、`data_model.js`、`ui_builder.js`、`widget_sync.js`、`mention_menu.js`、`gallery.js`），主入口精简至 ~140 行。
4. **组件外观与输入框排版优化**：
   - 分镜素材组件默认尺寸调整为宽 680px、高 940px，滚动容器最小高度提升至 580px；
   - 全局与分镜提示词输入框设置为 `rows=5`、`min-height: 110px`、行高 `1.5`，可视视野显著提升；
   - Tab 标签全面去除“走秀”等特定字眼，回归干净规范的 `分镜 1`、`分镜 2`、`分镜 3`；
   - 工作流 7 个节点标题全面精简，去除大串长括号。
5. **Stage 1/2/3 全链路排查排错日志**：
   - 覆盖 Stage 1/3 条件解析、Stage 2/3 链式采样、Stage 3/3 视频解码，为用户人工测试提供清晰跟踪。

### 迭代 1（2026-11-05 01:30:00）：H3 多分段架构对标蓝夕重构与全链路显存/内存优化
1. **画质根因修复（对标 lanxi）**：
   - 将原潜空间强行截断拼接重构为各分段独立 VAE 解码后，在像素空间（Pixel Space）无损裁切 22 帧，音频在波形空间对齐裁剪，彻底消除横向黑花条纹与重影。
2. **H3 双时钟调度保护**：
   - 注入 `minimax_h3_sigma_shift_video = 12.0` 与 `shift_audio = 3.0`，采样器内置自动纠偏识别，防止跳过细节成型期。
3. **8 分段显存与内存治理**：
   - 采样端 GPU->CPU 即时转存与显存回收，采样后卸载 DiT 让渡 18GB VRAM 给 2.0MP 3D VAE；
   - 解码端基于 CPU 原地流式预分配写入（`assembled_frames`），消除 8 段拼接时的 85GB 内存翻倍峰值。

---

## 待办任务池（Pending Backlog）

- [ ] **下一会话核心议题：单段重跑方案设计（先讨论，不写代码）**：
  - 某段效果不好时避免 6 段全量重跑。候选：A. 采样时保存每段 latent 首尾上下文（7 视频潜步 + 36 音频步）用于重跑，接缝无损；B. 用成片分段视频首尾帧重跑，无需改采样器但 VAE 往返有损且音频上下文无法恢复。
  - 倾向 A 为主路径、B 为无 latent 时的补救。重跑必须复用原段 seed、sigmas、参考素材和语义桥参数。详见最新快照“下一步计划”。
- [ ] **真机验证 `3ff4b06`**：
  - 重启后确认日志出现“复用一采模型，跳过一采/二采交接卸载”，且不再有 `released first-pass transformer` 紧跟 `38444MB Staged`；解码阶段两个 VAE 仅第一段 stage 一次。
- [ ] **人工质检跟踪**：重启后加载长视频工作流，结合 Stage 1/2/3 日志做生成质检。

**明确不做**：不改官方 ComfyUI 代码；不自动化重启（一律提示用户用秋叶启动器 GUI）；CFG 保持 1.0。
