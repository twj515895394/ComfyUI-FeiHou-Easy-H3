# PRD 0002：可续接链式采样器

状态：设计稿，未实现。写代码前以本文为准。

## 1. 要解决的事

现有「FeiHou Easy H3 链式采样器」一次把全部分镜采完，输出一条拼好的 latent。6 段 × 10 秒大约要 70 分钟以上。某一段效果不好时，只能整条重跑。

新节点让用户：

1. 跑一段，看这一段，不满意就重跑这一段。
2. 满意后从下一段接着跑，接缝沿用上一段的潜空间尾巴。
3. 全部满意后，不重新采样，把已经落盘的各段拼成一条完整视频。

## 2. 不做什么

- 不改现有链式采样器的输入、输出、默认行为和端口顺序。一次跑完的工作流保持原样。
- 不新做素材分镜组件。继续吃「FeiHou Easy H3 多分镜素材配置」输出的 `FEIHOU_MULTI_CLIP_CONTEXT`。每段的提示词、素材、时长、种子、步数、conditioning、初始 latent 都已经在里面，且带 `index`。
- 不在分镜面板上加「从这一段继续」按钮。起始段放在新采样节点上。
- 不改 CFG。控件保留是为了和现有采样器同形，值锁定 1.0，改了就按 1.0 用并在报告里写明。
- 不改官方 ComfyUI。不自动重启，改完提示用户用秋叶启动器 GUI 手动重启。
- 第一版不做成片反推续接（用已解码视频的首尾帧重跑）。没有尾巴缓存时直接报错，不偷偷走有损路径。

## 3. 节点

| 项 | 值 |
| --- | --- |
| 类名 | `FeiHouEasyH3ResumableChainSampler` |
| 注册名 | 同上 |
| 显示名 | FeiHou Easy H3 可续接链式采样器 |
| 分类 | FeiHou Easy H3 |
| 实现 | 新文件 `resumable_chain_sampler.py`。采样、latent carry、motion context、SelfLift 步数规则复用 `chain_sampler.py`，不复制一套 |

下游仍接现有「FeiHou Easy H3 视频解码器」。

## 4. 三种跑法

段号按分镜组件里的 `clip.index`，从 1 开始。`start_segment` 到 `end_segment` 是闭区间。

### 4.1 逐段预览（`step_mode = true`）

只采样 `start_segment` 这一个分镜，忽略 `end_segment`。

- 输出只有这一段（若接了上一段尾巴，开头重叠帧已裁掉）。
- 这一段的解码结果写入缓存：`seg_XX.pt`（裁切后的帧和音频）和 `tail_XX.pt`（潜空间尾巴）。
- 同段号再跑一次会覆盖这两个文件。
- 报告末尾写明：满意后把「起始段」改成 N+1。

### 4.2 范围续跑（`step_mode = false`）

采样 `start_segment` 到 `end_segment`。

- `start_segment > 1` 时，从缓存读取上一段的尾巴做续接。
- 范围内每一段都落盘。
- 本次输出是范围内各段拼好的视频，不是全片。全片用 4.3。

### 4.3 只拼接（`assemble_only = true`）

不采样。按缓存键读取 `start_segment` 到 `end_segment` 已落盘的各段，拼成一条视频。

- 缺任何一段就报错，并指出缺的段号。不补采样。
- `step_mode` 在此模式下无效。
- 这是「全部跑完后看完整视频」的入口。逐段跑完 N 次不会自动得到整片。

## 5. 续接

续接算法与现有链式采样器相同，不另写。

- `continuation_mode = hybrid`（默认）：上一段尾巴嵌入下一段开头，再用 motion context 注入引导锚点。
- `latent_carry`：只嵌入尾巴并用 `noise_mask` 冻住。
- `motion_context`：只注入引导锚点。
- 重叠 22 帧 = 7 个视频潜步 + 36 个音频步；39 帧 = 12 个视频潜步 + 65 个音频步。
- 视频 carry 区的 mask 值等于 `context_noise`（0 表示原样保留）。音频 carry 区始终为 0。
- 解码后裁掉重叠帧和对应音频，再落盘、再拼接。

重跑第 N 段后，第 N 段及之后的缓存全部作废：删除 `seg_N` 及以后、`tail_N` 及以后。原因是后段的尾巴是按旧的前段生成的。报告里列出被清除的段号。

## 6. 缓存

目录：ComfyUI 临时目录下的 `feihou_h3_resume/<cache_key>/`。

`cache_key` 只允许字母、数字、下划线、短横线，最长 64。空值用 `default`。含路径分隔符或其他字符直接报错，不替换。

| 文件 | 内容 |
| --- | --- |
| `manifest.json` | 画布宽高、重叠帧数、续接模式、各段种子、各段文件是否齐全、写入时间 |
| `tail_XX.pt` | 第 XX 段采样结果的尾部：视频潜步、音频步、宽、高。只供下一段续接，不供播放 |
| `seg_XX.pt` | 第 XX 段裁切后的帧和音频，供预览和最终拼接 |

`XX` 是两位段号，对应 `clip.index`。

读取规则：

- 只读这个目录里由本节点写过的文件，且 `manifest.json` 能对上。
- `tail` 的宽高与当前画布不一致时拒绝续接，不缩放硬接。
- manifest 里的重叠帧数、续接模式和本次不一致时拒绝续接。换重叠或换续接模式必须换 `cache_key`，或先清空缓存。
- 缓存是本机运行产物。不把别的来源的 `.pt` 丢进来读。

种子：

- 落盘时记录这一段实际使用的种子。
- 再次跑到同一段且种子与记录不同时，报告里写一条警告，不阻止运行。逐段模式下每段都用它自己的种子，不按「本次起点」重新做 +1，避免和全量跑的段种子错位。

## 7. 每次输出的是什么

| 跑法 | 视频输出 | 能看到前面各段吗 | 能看到完整视频吗 |
| --- | --- | --- | --- |
| 逐段预览 | 当前段，加上一段结尾 `preview_tail_seconds` 秒 | 只能看到上一段结尾那几秒，用来检查接缝 | 否 |
| 范围续跑 | 本次范围内拼好的视频 | 范围内可以，范围外不行 | 仅当范围是全部分镜 |
| 只拼接 | 缓存里该范围的全部段 | 是 | 范围覆盖全部分镜时是 |

第一段没有上一段，预览就是本段全长。

节点输出：

| 名称 | 类型 | 含义 |
| --- | --- | --- |
| `frames` | IMAGE | 按上表裁切、拼接后的帧 |
| `audio` | AUDIO | 与帧对齐的音频 |
| `latent` | LATENT | 本次采样的 latent。只拼接时为空 latent，不建议拿去再解码 |
| `report` | STRING | 本次做了什么：段号、种子、是否载入尾巴、裁了多少帧、清除了哪些段、下一步该改哪个参数 |
| `segment_info` | STRING | JSON：范围、缓存键、各段帧数、各段是否来自缓存 |

## 8. 参数

控件顺序就是接线顺序。续接相关的放在前面，采样参数与现有链式采样器保持同名同默认值，方便对照。

### 8.1 必填

| 控件 | 类型 | 默认 | 悬停 |
| --- | --- | --- | --- |
| `model` | MODEL | — | 一采模型。接 Remix 加载器的一采输出 |
| `multi_clip_context` | FEIHOU_MULTI_CLIP_CONTEXT | — | 多分镜素材配置的输出。本节点不改分镜内容，只决定从哪一段跑到哪一段 |
| `vae` | VAE | — | 视频 VAE。逐段预览和最终拼接都要解码，所以这里就解码，不再只出 latent |
| `sampler` | SAMPLER | — | 与链式采样器相同的采样器输入 |
| `sigmas` | SIGMAS | — | 时间步调度。连线值优先；只有该分镜勾选了覆盖步数才重算 |
| `seed` | INT | 0 | 种子基数。某一段在分镜组件里写了自己的种子时，用那一个，不用这里的递增结果 |
| `cfg` | FLOAT | 1.0 | MiniMax H3 的 CFG 必须是 1.0。其他值会被忽略并在报告中说明 |
| `sampling_engine` | COMBO | `selflift_avatar` | `selflift_avatar`：一采低清、二采高清。`standard_euler`：单阶段 Euler |
| `seed_behavior` | COMBO | `increment` | `increment`：未单独指定种子的分镜按段号递增。`fixed_all`：都用同一个种子。`random_all`：每段随机。递增按段号，不按本次起点，保证单独重跑某一段时种子不变 |

`sampling_engine` 选项：`selflift_avatar`、`standard_euler`。

`seed_behavior` 选项：`increment`、`fixed_all`、`random_all`。

### 8.2 续接（可选，放在可选区最前）

| 控件 | 类型 | 默认 | 悬停 |
| --- | --- | --- | --- |
| `start_segment` | INT，最小 1，最大 8 | 1 | 从第几段开始，含本段。逐段预览时只跑这一段 |
| `end_segment` | INT，最小 1，最大 8 | 8 | 跑到第几段，含本段。大于实际分镜数时截到最后一段。逐段预览时忽略 |
| `step_mode` | BOOLEAN | false | 只跑起始段并保存，方便看完再决定重跑还是继续。输出是这一段，另带上一段结尾数秒用于看接缝 |
| `assemble_only` | BOOLEAN | false | 不采样。把缓存里起始段到结束段已经跑好的片段拼成一条视频。缺段会报错 |
| `cache_key` | STRING | `default` | 这组成片的缓存名。同一条视频的逐段、重跑、拼接必须用同一个名字。换重叠帧数或换续接方式时换一个名字 |
| `reload_tail` | BOOLEAN | true | 起始段大于 1 时，读取上一段的潜空间尾巴来衔接。关掉则这一段当开头，和上一段对不上 |
| `reset_cache` | BOOLEAN | false | 本次运行前清空这个缓存名下的全部片段和尾巴。只在确定整条重来时打开，用完关掉 |
| `preview_tail_seconds` | FLOAT，0 到 5，步进 0.1 | 2.0 | 逐段预览时，在当前段前面附上一段结尾多少秒。0 表示只看当前段。只影响预览，不写入缓存 |
| `continuation_mode` | COMBO | `hybrid` | `hybrid`：尾巴嵌入加引导锚点，和现有链式采样器一致。`latent_carry`：只嵌入尾巴。`motion_context`：只注入引导锚点 |
| `context_noise` | FLOAT，0 到 1，步进 0.01 | 0.0 | 嵌入的视频尾巴允许多少重采样。0 原样保留。0.1 到 0.2 可轻微修复接缝处的脸，过大动作会断 |
| `overlap_frames` | COMBO | `22` | `22`：约 0.92 秒，7 个视频潜步，更快。`39`：约 1.63 秒，12 个视频潜步，动作和声音更稳。中途不能改，改了要换缓存名 |

`continuation_mode` 选项：`hybrid`、`latent_carry`、`motion_context`。

`overlap_frames` 选项：`22`、`39`。

### 8.3 采样（可选，与现有链式采样器一致）

这些控件的名字、默认值、悬停与「FeiHou Easy H3 链式采样器」相同，实现时从那边抄，不重新措辞：

`shift_video`、`shift_audio`、`auto_shift_sigmas`、`second_sampling_model`、`audio_vae`、`negative`、`positive`、`lowres_scale`、`rho`、`w_min`、`w_max`、`upscaler_model`、`highres_tiling`、`tiling_mode`、`tiling_tiles`、`tiling_axis`、`highres_tiling_mode`、`highres_token_chunk`、`highres_weight_cache_gb`、`unload_between_segments`。

两点差别写进对应悬停的末尾：

- `audio_vae`：本节点在采样后立刻解码，音频 VAE 不接时只出画面、音频为空。
- `unload_between_segments`：逐段预览只跑一段，这个开关没有段间可卸，仅范围续跑时生效。

## 9. 接线

```
Remix 加载器 ── model / second_sampling_model / vae / audio_vae
多分镜素材配置 ── multi_clip_context
调度器 ── sampler / sigmas
        │
        ▼
可续接链式采样器 ── frames / audio ── 保存视频
                 └─ report（先看这个，确认段号和是否载入了尾巴）
```

一次跑完的旧工作流不要换这个节点。

## 10. 推荐操作

1. `step_mode` 开，`start_segment = 1`，`cache_key` 取一个名字。跑完看输出。
2. 不满意：不改段号，改种子或提示词再跑。该段缓存被覆盖。
3. 满意：`start_segment` 加 1，再跑。报告里应出现「已载入上一段尾巴」。
4. 全部分镜都满意后：`assemble_only` 开，`start_segment = 1`，`end_segment` 设为最后一段。这次不采样，输出整条视频。
5. 只想重跑第 4 段：`assemble_only` 关，`step_mode` 开，`start_segment = 4`。跑完后第 5 段及之后需要按同样方式重跑。

## 11. 失败时怎么说

报告用中文，直接说原因和下一步，不抛英文栈给用户看。

| 情况 | 报告 |
| --- | --- |
| 起始段大于 1，但没有上一段尾巴 | 缓存 `<key>` 里没有第 N-1 段的尾巴。先跑那一段，或把起始段改成 1 |
| 只拼接时缺段 | 缓存 `<key>` 缺第 N 段，不能拼接。先把这一段跑完 |
| 宽高或重叠帧数或续接模式和缓存不一致 | 缓存 `<key>` 是按另一种画布或重叠跑的。换一个缓存名，或打开「清空缓存」后从头跑 |
| 缓存名含非法字符 | 缓存名只能用字母、数字、下划线和短横线 |
| `end_segment < start_segment` | 结束段小于起始段。已对调并在报告里写明实际范围 |

## 12. 验收

- 现有链式采样器的测试全部保持通过，且该节点的端口和默认值没有变化。
- 两段逐段跑完再只拼接，帧数等于两段裁切后之和，接缝处与同一次范围跑的重叠裁切一致。
- 重跑第 1 段后，第 2 段的 `seg` 和 `tail` 被删除，再拼接会因缺段失败。
- 同一段逐段跑两次，第二次种子与第一次记录不同时，报告里有警告。
- `cache_key` 为 `../x` 或空路径时拒绝运行。
- CFG 传入 7 时实际按 1.0 采样，报告里有说明。
