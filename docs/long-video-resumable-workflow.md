# H3 长视频可续接工作流：参数、逐段制作与审核手册

> 面向后续 Agent 的操作指南：根据用户提供的创意、提示词和素材，先规划多分镜，再像人工操作者一样逐段设置、执行、审核；当前段确认合格后才继续下一段。不要一次性把整条长视频盲跑完。
>
> 示例图：[`workflows/02_h3_long_video_resumable_example.json`](../workflows/02_h3_long_video_resumable_example.json)
> 来源图：`X:\ComfyUI-aki-v2\ComfyUI\user\default\workflows\长视频test-可续接.json`

## 1. 工作流用途与重要原则

这个工作流把“分镜与素材定义”和“逐段采样、缓存、续接、拼接”分开：

- **`FeiHouEasyH3MultiClip`（多分镜素材配置）** 保存整条视频的全局设定、每段提示词、时长、采样覆盖项和素材清单，并为每段准备 conditioning 与初始 latent。
- **`FeiHouEasyH3ResumableChainSampler`（可续接链式采样器）** 每次只运行指定片段，使用上段 latent 尾部衔接，缓存已完成片段；用户审核后，再手动改起始段参数运行下一段。也可切换为只拼接已缓存片段。

**逐段人工审核是默认制作方法。** 不要把 `start_segment=1, end_segment=6, step_mode=false` 当作默认的一键生产设置；这会在一次执行中连续跑多段，失去每段审核关口。每段审核不通过时，修改该段提示词/素材或种子，保持起始段不变重跑；通过后才把起始段改成下一段。

其他硬约束：

1. MiniMax H3 的 CFG 必须是 `1.0`，节点运行时也会强制使用 `1.0`。
2. 续接缓存必须保持相同 `cache_key`、画布、重叠帧数和续接模式；切换画布/重叠/续接策略时使用新缓存名，或明确清空旧缓存后从头跑。
3. 不要把逐段预览文件直接拼在一起：续接段预览可额外带上前一段末尾若干秒供接缝检查，这段预览前缀不在片段缓存内；应使用 `assemble_only` 输出缓存成片。
4. 除非用户明确提出 RefMod，否则移除 RefMods Loader 节点并断开 MultiClip 的 `refmods` 输入口。
5. 节点 JSON 只保存媒体引用/文件名和工作流数据，不打包本机素材、模型、LoRA 或 RefMod 文件；Agent 必须确认当前运行环境能找到它们。

## 2. 示例工作流现状（不是通用提示词模板）

该示例文件原样复制了用户的工作流 JSON。包含 17 个节点、24 条连线，节点均为启用状态。示例是一条 6 分镜、参考生视频的工作流；提示词和素材为示例作者的内容，后续任务应按用户的新需求重写，不要照搬人物身份、剧情或素材。

### 2.1 节点与主要连线

| 节点 ID | 节点 | 在图中的作用 |
|---|---|---|
| 1 | `FeiHouEasyH3RemixLoader` | 提供 H3 模型包、VAE 和相关模型接口。 |
| 2 | `FeiHouEasyH3MultiClip` | 六段故事、提示词和素材的配置容器；输出 model、second model、context、VAE、audio VAE、prompt preview、steps、positive。 |
| 3 | `KSamplerSelect` | 选择 `euler` sampler。 |
| 4 | `BasicScheduler` | 生成基础 sigma 调度；steps 来自 MultiClip，模型由节点 18 提供。 |
| 5 | `FeiHouEasyH3ResumableChainSampler` | 当前唯一的采样器实例；执行选定分镜并输出画面、音频、latent、运行报告和结构化段信息。 |
| 7 | `VideoCombineV2` | 保存本次采样器输出。当前名称为“当前段预览保存”，不是最终拼接专用节点。 |
| 8 | `MiniMaxH3RefModsLoader` | 示例中接入 RefMod。只有任务明确需要时才保留。 |
| 9、11 | `FeiHouEasyH3LoraStack` | 一采/二采 LoRA 堆叠，并分别接回 H3 Loader。是否启用以节点内开关和 bypass 状态为准。 |
| 10 | `H3SigmaRefiner` | 处理 sigma 调度后接入采样器。 |
| 12、14、15、17 | Chunk Feed Forward、Sage Attention、Block Sparse Attention、Model Attention Backend | 模型注意力/显存处理链。 |
| 18 | `ModelPreviewOverrideKJ` | 模型预览/调度链路中的模型处理节点。 |
| 19 | `BunnyH3ConditioningBridge` | 对 MultiClip 的 positive conditioning 应用语义桥后送进采样器。 |
| 21 | `easy showAnything` | 显示采样器 report；不负责视频合并。 |

关键数据链：

```text
1 Remix Loader -> 2 MultiClip
2.model -> 18 -> 5.model
2.second_sampling_model -> 5.second_sampling_model
2.multi_clip_context -> 5.multi_clip_context
2.vae -> 5.vae                 2.audio_vae -> 5.audio_vae
3.KSamplerSelect -> 5.sampler
2.steps -> 4.BasicScheduler -> 10.H3SigmaRefiner -> 5.sigmas
2.positive -> 19.Bunny Bridge -> 5.positive
8.RefMods -> 2.refmods          （仅任务需要 RefMod 时保留）
5.frames -> 7.images            5.audio -> 7.audio
5.report -> 21
```

### 2.2 当前保存值

- MultiClip：`mode=reference`，分辨率预设 `1.0`，画幅 `16:9`，手动宽高 `1920×1080`（仅 custom 分辨率模式才使用），全局秒数 `10`、全局 steps `7`、全局 transition step `5`、global prompt 为空；全局共享开启。
- 六个 clip 的 `override_steps=false`、`override_seed=false`；因此各段真正使用上游全局 `seconds=10`、`steps=7`、`transition_step=5`、由采样器生成的种子策略。JSON 中 clip 自己也保存 seconds / steps / transition 字段，但 override 关闭时它们不作为该段覆盖值。
- 当前采样器 widgets：seed `666`，seed control `fixed`，CFG `1`，`selflift_avatar`，`increment`；`start_segment=2`、`end_segment=2`、`step_mode=false`、`assemble_only=false`；cache key `default`、`reload_tail=true`、`reset_cache=false`、预览尾巴 `2s`；续接模式 `hybrid`、噪声 `0`；视频/音频 shift `12/3`、自动 shift `true`；lowres scale `0.65`、rho `0`、w_min/w_max `0.5/1`；upscaler `h3_upscaler_lms_v0.1_fp32.safetensors`；high-res tiling 开启，`auto`、2 tiles、axis auto、`global_stream`、token chunk 4096、weight cache 4GB；重叠 `22`；段间卸载关闭。
- 图只有一个可续接采样器。`start_segment=2` 表示当前配置意图是续跑第 2 段；但“上次成功运行”信息仅在节点下方的 report widget/历史记录中，不要将旧 report 当作当前运行结果。第 2 段执行要求缓存中存在第 1 段 tail。
- VideoCombine：24 fps、H.264 MP4、`video/feihou_h3_segment`、CRF 19、`save_output=true`。此节点会保存采样器当前输出；当 `step_mode` 下游接到它时输出包含预览前缀，不能拿该文件直接当 assemble-only 成片。
- RefMods Loader 在示例中选中的条目显示为 `刘亦菲小龙女`，但是否保留该选项必须以用户当前任务为准；示例里的某个 Mod 不能被视为新视频的默认授权或默认需求。

## 3. 规划用户的视频：从创意到多分镜素材

Agent 应先把用户要求整理成可执行的分镜清单，再改工作流，而不是直接开始生成：

1. **提取约束**：主题/剧情、人物与外观连续性、场景、动作、时长、画幅/分辨率、风格、声音/对白限制、不可出现项，以及哪些素材对应人物/服装/道具/环境。
2. **先建立素材映射**：列出每个素材文件、类型和用途。区分全局素材（每段都要引用）与局部分镜素材（仅某些段使用）。确认文件确实在 ComfyUI 可读的输入/素材目录中；不要只因为 JSON 有文件名就认为文件已随工作流存在。
3. **拆成有因果的镜头段**：每段写清起始状态、动作节拍、结束状态、镜头/构图、环境、运动方向、转场承接和声音。段末状态应为下一段提供可见的动作或画面钩子；避免前后段人物、衣着、道具位置或运动轴线无理由改变。
4. **写每段 prompt**：需要重复的身份/连续性规则可放 global prompt；每段 prompt 写该段独有的动作和镜头。若全局引用素材编号，请保证各段使用的素材配额与顺序一致；局部素材引用应依对应分镜实际素材映射核对。
5. **配置秒数和覆盖**：全局 seconds/steps/transition 是默认值；按需设置 clip 的 `override_steps` 和对应字段。不要误以为 clip JSON 的字段总会生效。每段 override seed 需同时打开 `override_seed` 并填 seed。
6. **审查素材容量和引用**：reference mode 每个分镜最多图 9、视频 3、音频 3；全局引用会从每段可用容量扣除。把素材添加后检查生成的 reference map/log 与提示词 `@图N`、`@视频N`、`@音频N` 一致。
7. **确认再执行**：在第一段运行前让用户确认分镜、素材与关键设定，尤其是身份来源、敏感素材、RefMod、画面规格和输出用途。用户确认后开始逐段生成。

### 3.1 多分镜节点字段

| 设置 | 功能与 Agent 操作建议 |
|---|---|
| `mode` | `reference` 参考生视频（多模态素材与 @ 引用）；`image` 首尾帧/图生视频（最多使用两张有效图作为首尾帧）；`text` 纯提示词，不使用多分镜图/视频/音频素材。RefMod 只支持 reference mode。 |
| `resolution`, `aspect_ratio`, `width`, `height` | 选择像素量级与画幅；width/height 仅 custom 预设下使用，且应为 32 的倍数。按目标平台和资源预算决定。 |
| `seconds`, `steps`, `transition_step` | 全局分镜默认时长、总采样步数、一采转折步。每段 `override_steps=true` 时才应用该段对应 seconds/steps/transition 值。SelfLift 下若转折设置导致二采不足 2 步，运行时会将转折点往前收，以至少留 2 步。 |
| `global_prompt` | 开启全局共享时作为前缀，以换行与每段 prompt 拼接。适合共通身份、风格和禁则；不要放只适用于某一场的动作。 |
| global media | 开启全局共享时所有分镜都可用，会占用每段素材容量；适合跨段一致的人物参考。 |
| `clips[]` / 每个分镜 | `index/name` 是顺序与名称；`prompt` 是该段内容；`seconds/steps/transition_step` 与 `override_steps` 配合；`seed` 与 `override_seed` 配合；`media.images/videos/audios` 是局部素材文件名列表。局部素材只作用于该分镜。 |
| `refmods` | 可选 H3_REF_MODS 输入，仅用户明确指定 RefMod 时连接。每个启用的成员按对应模态计入容量。 |
| `lora_stack`, `second_lora_stack` | 分别应用于一采和二采模型的 LoRA 组合。逐段审核时如果改 LoRA 使角色外观发生变化，需慎重评估旧段与新段衔接。 |
| `force_offload` | 采样完成后主动释放显存/模型缓存；内存吃紧可评估开启，代价是重载时间。 |
| `low_vram_streamed_attention` | 启用 H3 深度分块流式注意力以降低峰值显存；有注意力节点/硬件兼容性问题时不要盲目启用。 |

### 3.2 素材配额与引用编号

reference mode 素材容量上限：全局图片最多 9、视频最多 3、音频最多 3；全局素材会对所有分镜占位并扣除局部容量。每个有效视频 RefMod 也占一个全局视频配额。局部素材数量超出剩余容量时会报错，而不是悄悄丢弃。image mode 仅取最多两张图片作为首/尾帧；text mode 忽略多模态素材。

提示词前端写法使用 `@图1`、`@视频1`、`@音频1` 等引用；前端/节点会规范成 H3 token，如 `<Video 1>`。编号由对应模态的全局素材、局部素材和 RefMod 顺序共同决定，不能仅按文件名或视觉顺序推测。生成后查看 MultiClip 的 prompt preview / `reference_map` / 日志，确认每个标签映射到预期素材。

## 4. RefMods：必须按需使用

### 不需要 RefMod

如果用户的提示词、素材和要求均未明确说要 RefMod：

- 删除 `MiniMaxH3RefModsLoader` 节点，或至少断开其输出；推荐删除节点和悬空连线，避免后续 Agent 误以为它是必需输入。
- 确认 MultiClip `refmods` 插槽不再有连接。
- 不要因为示例工作流已有 Loader、或下拉框当前有选项，就擅自注入 Mod。

### 需要 RefMod

- 必须由用户明确指定要用哪个 Mod（或确认 Agent 提出的具体候选）。一个 Mod 相当于一个参考素材；不能把“想要某种人物/风格”自行推断成使用某个 Mod。
- 可选 Mod 数据源为 `X:\ComfyUI-aki-v2\ComfyUI\models\refmods`。在 `MiniMaxH3RefModsLoader` 上实时选择该目录扫描出的 Mod 下拉项；若新文件未出现在下拉列表，先确认上游 RefMods 扩展的扫描/刷新状态，不要手写一个不存在的名称。
- 将 Loader 的 `mods` 输出连到 MultiClip 的 `refmods` 输入口。只有 loader 里的活动、非零 strength 条目才参与；检查类型兼容性、强度范围及引用素材容量。
- 在相应分镜 prompt 使用用户要求的 `@视频1` 这种显式引用形式（也可按 Mod 实际模态使用 `@图N` / `@音频N`）。一个 Mod 的成员/副本对应一个活动参考素材；bundle 中每个活动成员也可能分别占配额。先核实 Mod 的模态与实际条目数量。
- RefMod 排在相应模态普通素材前，因而会改变普通素材编号。以运行时 `reference_map`/日志为准；必须验证 `<Video 1>` 真正对应指定 Mod，再开始生成。
- 不要同一 Mod 同时通过 RefMods Loader 和另一条 Apply/Text Encode 注入路径重复添加。

## 5. 可续接采样器：端口、参数与语义

### 5.1 输入和输出

**必需输入：** `model`（模型）、`multi_clip_context`（MultiClip 上下文）、`vae`（视频 VAE）、`sampler`、`sigmas`、`seed`、`cfg`、`sampling_engine`、`seed_behavior`。

**可选输入：**

- 运行范围/缓存：`start_segment`、`end_segment`、`step_mode`、`assemble_only`、`cache_key`、`reload_tail`、`reset_cache`、`preview_tail_seconds`。
- 续接/时钟：`continuation_mode`、`context_noise`、`shift_video`、`shift_audio`、`auto_shift_sigmas`。
- 模型/conditioning：`second_sampling_model`、`audio_vae`、`negative`、`positive`。
- SelfLift：`lowres_scale`、`rho`、`w_min`、`w_max`、`upscaler_model`。
- 高分辨率切块：`highres_tiling`、`tiling_mode`、`tiling_tiles`、`tiling_axis`、`highres_tiling_mode`、`highres_token_chunk`、`highres_weight_cache_gb`。
- 其他：`overlap_frames`、`unload_between_segments`。

**输出：**

| 输出 | 内容 | 推荐用途 |
|---|---|---|
| `frames` (`IMAGE`) | 输出视频帧序列；step preview 可能在当前段前附加上段尾部。 | 接 VideoCombine 预览/保存。 |
| `audio` (`AUDIO`) | 解码音频波形与采样率（若有）。 | 接 VideoCombine 音频输入。 |
| `latent` (`LATENT`) | 本次运行最后一段的 latent，或 assemble-only 的占位 latent。 | 一般不用于下一次续跑；节点从磁盘 tail cache 续接。 |
| `report` (`STRING`) | 可读运行状态、缓存、续接和审核提示。 | 显示到文本节点，检查成功与错误。 |
| `segment_info` (`STRING`) | JSON 格式的运行模式、cache key、段号/帧数/seed、失效缓存、重叠数等。 | 给 Agent 或自动化记录核对；不是可供用户直接观看的视频。 |

### 5.2 参数表

| 参数 | 用途 / 调整规则 |
|---|---|
| `seed` | 全局基 seed。increment 根据分镜 index 加位移，重跑同段保持起始段不变可复现；random_all 例外。 |
| `cfg` | H3 固定为 `1.0`；不得改。传入其他值也会被强制改为 1。 |
| `sampling_engine` | `selflift_avatar` 两阶段低清/高分辨率采样；`standard_euler` 标准 Euler 单阶段。示例用 SelfLift。 |
| `seed_behavior` | `increment`（按段号递增，推荐）、`fixed_all`（每段同 seed）、`random_all`（每次随机）。若 clip 开启 seed override，则用该段 seed。 |
| `start_segment`, `end_segment` | 运行起止分镜，含首尾；超出实际末段会截到最后，倒置会调换。`step_mode=true` 时 end 被忽略，只运行 start。 |
| `step_mode` | 只运行起始段并保存；审核型逐段流程应开启。若 start>1，可在输出预览前附加上一段缓存尾部 `preview_tail_seconds`；附加内容不入缓存。 |
| `assemble_only` | 不采样，只读取 start 到 end 已存在的成片缓存并拼起来；任一段缺失就报错。与 step_mode 不同，是输出成片的方式。 |
| `cache_key` | 一条视频/一套一致参数共用的安全缓存名（字母、数字、`_`、`-`，最多 64 字符）。不同视频务必不同。 |
| `reload_tail` | start>1 时读取上一段 latent tail。关闭后该段不继承前段，可能不连续；正常续接保持开启。 |
| `reset_cache` | 本次运行前删除该 cache key 下全部段与尾巴。只在确认整条重来时开启一次，执行后立即关闭；会丢失缓存结果。 |
| `preview_tail_seconds` | step preview 前附加上一段结尾用于接缝检查，范围 0–5 秒。只影响预览输出，不写缓存；不要把该预览 MP4 当单段净片。 |
| `continuation_mode` | `hybrid`（latent carry + motion context，推荐）；`latent_carry`（潜变量尾部续接）；`motion_context`（仅条件引导特征）。段间缓存要求该设置一致。 |
| `context_noise` | latent carry 的扰动强度。0 完全保留携带尾部，轻微非零可允许细微重去噪；优先保持示例 0。 |
| `shift_video`, `shift_audio` | H3 双时钟 sigma shift，示例 `12`、`3`。除非有明确调度依据，不要逐段改。 |
| `auto_shift_sigmas` | 自动修正未做 H3 shift 的简单线性 sigma 调度；通常开启。 |
| `second_sampling_model` / `audio_vae` | 可连二采模型及独立音频 VAE；无二采模型时 SelfLift 自动复用一采模型。 |
| `negative` / `positive` | 可选负/正 conditioning。未连负向会自动置零；该图的 positive 经过 Bunny bridge。 |
| `lowres_scale` | SelfLift 一采缩放比例；目标≤1MP至少0.7，目标>1MP按目标面积自动保障一采约≥0.5MP；高于自动下限的用户设置保持。图中保存值 0.65，但运行时会按画布自动提高到要求的下限。 |
| `rho`, `w_min`, `w_max` | SelfLift 噪声调度平滑与一、二采融合权重；示例 `0 / 0.5 / 1.0`。 |
| `upscaler_model` | 一采到二采之间的 latent 放大器；确认模型文件已安装。 |
| `highres_tiling` | 是否启用高分辨率切块/流式处理，显存受限时使用。 |
| `tiling_mode`, `tiling_tiles`, `tiling_axis` | auto/manual、手动块数、切分轴；manual 时 tiles 生效。 |
| `highres_tiling_mode` | `global_stream` / `spatial`。global_stream 配合稀疏注意力降低显存；需完整模型链支持。 |
| `highres_token_chunk` | 每次 attention 的最大 token 块；越低通常越省显存但越慢。 |
| `highres_weight_cache_gb` | 高分辨率阶段 GPU 模型权重缓存额度。 |
| `overlap_frames` | `22` 或 `39`；决定续接 latent/音频携带范围和解码后裁切量。整条缓存中不能中途变更。 |
| `unload_between_segments` | 多段范围采样时每段后全卸载模型，节省显存但牺牲速度；逐段 step mode 每次只有一段，通常无段间效果。 |

### 5.3 重叠与裁剪

重叠既用于上一段 latent 尾部续接，也用于下一段采样开头的重复区去重。解码后，续接段会裁掉开头重叠画面和对应时长音频，再把净片写入缓存；输出净片拼接因此不会重复重叠区。

- `22` 帧 ≈ 0.92 秒：7 个视频 latent token；音频携带 36 步；解码后移除 22 帧及等时长音频。
- `39` 帧 ≈ 1.63 秒：12 个视频 latent token；音频携带 65 步；解码后移除 39 帧及等时长音频。

两者走同一套携带与裁剪流程，只是对应长度不同。39 帧更长，通常提供更充分的动作/声音接续但生成成本更高。

## 6. Agent 模拟人工操作：逐段生成与审核 SOP

每一步都按“设置一个段号 → 执行一次 → 查 report 和视频 → 判断是否通过”的节奏完成。Agent 不应只检查节点执行成功，还要查看实际视频画面和声音。

### 阶段 A：创建/准备工作流

1. 从用户素材与剧情建立分镜表，按第 3 节分配全局与局部素材。
2. 打开示例副本，保留必要的模型/注意力/输出节点；按本次需求重写 MultiClip 全局 prompt、六段（或实际段数）提示词和 media 列表。删掉无关示例素材引用，确认文件能被当前 ComfyUI 加载。
3. 用户未明确要 RefMod：移除 Loader 与连接。用户明确指定：再按第 4 节选择并连接。
4. 设定全局时长、steps、transition 和画布；选择一个新的 `cache_key`，例如 `campaignA_20261112`。确定 overlap/续接 mode 后整条视频固定不变。
5. 采样器设 `step_mode=true`、`assemble_only=false`、`reload_tail=true`、`reset_cache=false`；先将 start/end 设置为 `1/1`。CFG 保持 1.0。确认 VideoCombine 连接 sampler 的 frames 与 audio，report 已连接到文本查看节点。
6. 在执行第 1 段前检查 MultiClip prompt preview / reference map，确认分镜数量、素材编号、提示词映射正确。必要时先让用户确认剧情拆分与第一段计划。

### 阶段 B：每段的人工审核循环

对段 `N` 重复以下流程：

1. **设置范围**：`start_segment=N`；`step_mode=true`、`assemble_only=false`；end 可保持 N（step mode 会忽略它）。N=1 不需要前段 tail；N>1 保持 `reload_tail=true`，并确认 N-1 已成功生成且使用同 cache key、画布、overlap、continuation mode。
2. **执行该段**：运行一次 ComfyUI。不要并行启动下一段，不要将 N+1 先排队。等待运行结束。
3. **核验结构状态**：检查 sampler `report` 中有“第 N 段采样完成”，N>1 时应有“已载入第 N-1 段的尾巴”；确认无缺缓存、尺寸不兼容、模型缺失或异常。检查 `segment_info` 指向正确的段号与 cache key。
4. **观看当前输出**：打开 VideoCombine 输出的 MP4（逐段预览）检查动作、身份、衣着/道具、场景、镜头方向、画面质量、段首接缝与音频。N>1 的预览可能先显示 N-1 尾部 `preview_tail_seconds`，审片时区分这段重复预览前缀与当前段净内容。
5. **作出人工式判定**：
   - **通过**：段内内容和接缝满足用户目标，记录段号、实际 seed、输出文件、关键问题=无；然后才把 `start_segment` 改成 N+1 并运行下一段。
   - **不通过**：先定位问题属于提示词、素材映射、随机种子还是续接/画面设定。修改第 N 段对应字段，起始段仍为 N，保持 cache key 不变并重新运行。重跑 N 会使 N 及后续段缓存失效；若后续段曾生成，必须按顺序重新审核/重跑，不可沿用基于旧 N 的后续结果。
   - **要求新方向/大改**：如果改了画布、overlap、续接模式、全局身份素材/角色基线等会破坏既有接续关系的参数，使用新的 cache key 从第 1 段重新制作，必要时经用户确认后才清理旧缓存。
6. **记制作日志**：每段至少记录通过/不通过、seed、素材/提示词变更、cache key、输出文件名、审核意见。ComfyUI report/segment_info 可作为机器事实，用户是否接受画面仍需人工/视觉审核，不能由“执行 completed”替代。

建议跟踪表：

| 段号 | 素材/提示词版本 | Seed | 执行状态 | 画面审核 | 接缝/音频 | 决策 | 输出/备注 |
|---:|---|---:|---|---|---|---|---|
| 1 |  |  |  |  |  | 待审核 |  |
| 2 |  |  |  |  |  | 待审核 |  |
| … |  |  |  |  |  |  |  |

### 阶段 C：最终拼接成片

1. 所有段都审核通过，且每段净片缓存属于同一个 cache key、画布、overlap、续接 mode 后，再拼接。
2. 采样器切换 `assemble_only=true`，`step_mode=false`，设 `start_segment=1`、`end_segment=最后一段`；不要启用 `reset_cache`。此模式不采样，缺任一段会报错。
3. 将 frames/audio 接入 VideoCombine；按最终交付需求设文件名前缀、格式/帧率、音视频选项后运行一次。检查最终成片时长、片段顺序、画面接缝与音频连续。
4. VideoCombine 的这一份输出才是缓存净片的完整拼接版本。若用户只想预览部分已完成片段，可将 start/end 设为该范围；不完整范围不是最终全片。

## 7. 缓存机制与故障处理

默认缓存位置在 ComfyUI temp 目录：`feihou_h3_resume/<cache_key>/`。其中：

- `seg_XX.pt`：VAE 解码后的、已经裁掉续接重叠的画面/音频净片，供预览、只拼接及最终输出使用。
- `tail_XX.pt`：该段 latent，供下一段读取并在 latent carry/hybrid 模式续接。
- `manifest.json`：记录画布、overlap、续接模式以及段号和 seed 等元信息。

常见情况：

| 情况 | 处理 |
|---|---|
| 第 N 段提示缺少 N-1 tail | 先生成 N-1，或把 start 改 1；不要关闭 `reload_tail` 来掩盖缺失。 |
| assemble-only 提示缺段 | 查 report 的缺失段号，按顺序补跑并审核后再 assemble。 |
| 缓存画布/重叠/续接模式不一致 | 用新 cache key 从头跑，或确认需废弃旧结果后 reset；不能混合不同配置的 tail/segments。 |
| 重跑中间段后发现后段旧文件仍在输出目录 | 输出目录里的旧 MP4 不等于有效缓存；运行时会失效该段及后续缓存，重新跑并审核后再 assemble。 |
| preview 视频开头有重复画面 | 这是 `preview_tail_seconds` 的接缝检查前缀；净段保存在 segment cache，最终走 assemble-only。 |
| seed 改了但 report 提示与上次不同 | 这是提示信息；审片确认新结果，任何依赖旧段的后续内容都必须重跑。 |
| 对全片重做 | 用新 cache key 最安全；若复用旧 key，开启 `reset_cache` 运行一次后立即关闭，并从段 1 重新审核。 |

## 8. 维护者/Agent 参考实现

说明应与实际实现保持一致，参数变更后重新核对：

- `multi_clip_node.py`：MultiClip UI/执行、模型选择、素材载入和引用映射。
- `multi_clip_core.py`：全局/局部素材配额、提示词级联和 context 数据模型。
- `chain_sampler.py`：基础采样器、自适应 SelfLift 比例、latent/motion context 与 overlap 常量。
- `resumable_chain_sampler.py`：范围/step/assemble 模式、续接、裁剪、预览与输出。
- `resume_cache.py`：磁盘缓存键、segment/tail、配置兼容与失效。
- `refmod_compat.py`：上游 RefMods 数据规范化、参考顺序与 tag 校验。

本文件是使用手册，不改变运行逻辑。若节点输入、缓存行为或工作流连线发生变化，需同步更新本说明与示例。
