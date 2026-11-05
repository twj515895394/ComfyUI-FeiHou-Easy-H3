# 交接快照：H3多分镜素材大组件重构、全局开关、分段日志与RefMod待办

- **交接时间**：2026-11-05 17:00:00
- **当前分支**：`main`
- **对应 Commit**：`8de6503` (当前工作区存在未提交优化修改)
- **主要涉及模块**：
  - `web/feihou_easy_h3_multi_clip.js`（轻量级 ComfyUI 扩展注册入口）
  - `web/modules/*`（单一职责前端 ES 模块：`styles.js`、`data_model.js`、`ui_builder.js`、`widget_sync.js`、`mention_menu.js`、`gallery.js`）
  - `multi_clip_core.py`（多分镜核心模型、配额引擎、Prompt 级联规则）
  - `multi_clip_node.py`（Node 2 多分镜素材配置节点实现，Stage 1/3 条件解析日志）
  - `chain_sampler.py`（Node 5 链式采样器，单分镜/多分镜判定，Stage 2/3 采样日志）
  - `vae_decoder.py`（Node 6 视频解码器，像素 22 帧裁切，Stage 3/3 解码拼合日志）
  - `tools/generate_multiclip_workflow.py`（工作流生成器，同步更新 UI JSON 与 API JSON）
  - `tests/*`（全量 49 项单元与端到端测试）

---

## 1. 用户主要意图与核心技术决策

### 1.1 用户核心诉求
1. **全局共享素材与提示词开关**：
   - 增加交互式切换开关。开启时全局提示词拼接到各分镜，全局素材扣减分镜配额；关闭时各分镜完全独立运行，不继承全局提示词，各分镜享有独立的满额配额（9图、3视频、3音频），从 `@图1`、`@视频1`、`@音频1` 开始独立编号。
2. **分镜 1 默认强制常驻与单分镜普通视频模式**：
   - “分镜 1”必须始终存在且不可删除（保证至少 1 个分镜）。
   - 若用户仅保留 1 个分镜，整条工作流自动退化为标准单视频模式（普通单次采样与解码），不触发任何分段续接、运动上下文注入或边界裁切。
3. **前端 JS 模块化拆分（SRP 治理）**：
   - 原单个 `web/feihou_easy_h3_multi_clip.js` 文件曾膨胀至 1874 行，按照单一职责原则拆解至 `web/modules/` 子模块，降低维护难度。
4. **组件外观与排版优化**：
   - 适度增加分镜素材组件默认尺寸（680×940），提升容器滚动可视高度。
   - 增加全局与分镜独立提示词输入框的高度与行数（`rows=5`, `min-height: 110px`），改善编辑视野。
   - 彻底去除 Tab 名称中“走秀入场/T台转身/折返退场”等特定业务名称，回归简洁干净的 `分镜 1`、`分镜 2`、`分镜 3`。
   - 全面精简工作流节点大串长标题，去除冗余的括号说明。
5. **排查问题的各环节阶段日志**：
   - 为后续人工测试提供全链路清晰的 `[Stage 1/3]`（条件解析）、`[Stage 2/3]`（链式采样）、`[Stage 3/3]`（视频解码）控制台输出。
6. **下个会话核心待办（RefMod 识别问题）**：
   - 用户反馈：当上游接入 `refmods`（H3_REF_MODS）时，当前多分镜大组件的 `@` 菜单未能像旧版 FeiHou 素材节点那样识别并补全为视频素材。

---

## 2. 核心交付与代码改动一览

### 2.1 前端 ES 模块拆分与重构
- **`web/modules/styles.js`**：独立 CSS 样式层，包含 `.fh-mc-container`、`.fh-mc-switch`（紫色滑动开关）、`.fh-mc-disabled-notice`（黄色停用提醒）、`fh-mc-prompt-input`（增高至 110px，行高 1.5）、`.fh-mc-mention-menu`、`.fh-mc-gallery` 等。
- **`web/modules/data_model.js`**：数据结构模型、默认值生成（`getDefaultData` 保留分镜 1 必填项）、数据规范化（`normalizeData` 增加 `enable_global: boolean`）以及后端同步机制。
- **`web/modules/ui_builder.js`**：组件 DOM 装配中心。分镜 1 屏蔽删除按钮；全局 Tab 增加“🌐 启用全局共享素材与提示词”滑动开关；提示词输入框设置为 `rows=5`；联动全局禁用提示与素材槽禁用遮罩。
- **`web/modules/mention_menu.js`**：`@` 提及弹出框。根据当前 Tab 与 `enable_global` 状态动态生成 `@图1~9`、`@视频1~3`、`@音频1~3` 选项；支持键盘导航与光标处无缝文本插入。
- **`web/modules/gallery.js`**：卡片式素材槽渲染器。支持图片 3/9 折叠展开、拖拽上传、文件删除；支持全局关闭时的禁用置灰展示。
- **`web/modules/widget_sync.js`**：原生 ComfyUI Widget 联动。隐藏原生全局提示词 widget，动态控制分辨率与宽高切换；在模式切换时自适应调整节点高度；针对 Node 5 ChainSampler 参数提供防 `NaN` 运行时清洗。
- **`web/feihou_easy_h3_multi_clip.js`**：精简为约 140 行的扩展入口，调度子模块安装与生命周期注册。

### 2.2 后端逻辑与日志交付
- **`multi_clip_core.py`**：
  - `MultiClipContext` 增加 `enable_global: bool = True` 字段；
  - `MultiClipQuota` 支持在 `enable_global == False` 时将各分镜容量完全释放为满额独立配额（图 9、视 3、音 3，起始编号为 1）；
  - `cascade_prompts` 在全局开关关闭时直接返回分镜原始提示词。
- **`multi_clip_node.py`**：
  - 支持解析前端传来的 `enable_global` 状态；
  - 空分镜自动回退到常驻的单个“分镜 1”；
  - 增加 `[FeiHou MultiClip] [Stage 1/3]` 结构化日志，打印生成模式、分辨率、全局共享状态、素材配额以及各分镜独立步数、种子与引用详情。
- **`chain_sampler.py`**：
  - 判定 `len(clips) == 1` 时进入标准单视频模式（无片段续接，`trim_frames = 0`）；
  - 增加 `[FeiHou ChainSampler] [Stage 2/3]` 结构化日志，详细打印双时钟频移（Shift 12/3）、时序上下文注入、Step Schedule（一采转折点）、分块 Latent 缝合过程。
- **`vae_decoder.py`**：
  - 区分单分镜直接解码模式与多分镜逐段解码裁切模式；
  - 增加 `[FeiHou VAEDecode] [Stage 3/3]` 结构化日志，追踪每段解码分辨率、像素空间 22 帧裁切进度、音频波形裁切采样点数、CPU 预分配流式拼接写入进度以及合成总帧数。
- **`__init__.py`**：
  - 精简 `NODE_DISPLAY_NAME_MAPPINGS` 为 `FeiHou Easy H3 链式采样器`、`FeiHou Easy H3 多分镜素材配置`、`FeiHou Easy H3 视频解码器`。
- **`tools/generate_multiclip_workflow.py`**：
  - 重新编译生成 `workflows/feihou_h3_multiclip_7nodes.json`、`workflows/feihou_h3_multiclip_7nodes.api.json` 以及秋叶启动器工作流目录 `X:/ComfyUI-aki-v2/ComfyUI/user/default/workflows/FeiHou_H3_MultiClip_LongVideo_7Nodes.json`；
  - 彻底去除所有“走秀”字眼，采用通用的现代光影建筑提示词；
  - 将所有节点标题统一精简为干净编号（如 `1. H3 模型加载器`、`2. 多分镜素材配置` 等）。

---

## 3. 踩坑与经验总结（Gotchas）

1. **`_frame_length` 缺少 `fps` 参数报错**：
   - `_frame_length` 定义为 `_frame_length(seconds, fps=24.0)`。在 Stage 1/3 打印日志时直接调用了 `_frame_length(c.seconds)` 导致类型错误。必须显式传入 `_frame_length(c.seconds, fps=24.0)`。
2. **`canvas_w` 与 `canvas_h` 提前引用问题**：
   - 日志打印前如果提前输出分辨率尺寸，必须将 `_canvas_dimensions(...)` 移至日志语句前执行，避免 `UnboundLocalError`。
3. **ComfyUI 浏览器端 ES 模块路径规范**：
   - ComfyUI Web 扩展在子模块相对引入时必须带完整扩展名（如 `import { ... } from "./modules/ui_builder.js"`），且模块间不能互相循环依赖。
4. **秋叶启动器手动重启约束**：
   - 根据用户约束，切勿执行脚本自动化重启 ComfyUI，必须明确提示用户在秋叶启动器 GUI 界面中点击重启。

---

## 4. 验证闭环结果

1. **JS 语法验证**：
   - 运行 `node -c` 对 `web/modules/styles.js`、`web/modules/data_model.js`、`web/modules/ui_builder.js`、`web/modules/widget_sync.js`、`web/modules/mention_menu.js`、`web/modules/gallery.js`、`web/feihou_easy_h3_multi_clip.js` 逐一测试，全部语法校验通过（Exit code 0）。
2. **自动化单元测试全通**：
   - 使用 ComfyUI 专用环境运行：`X:/ComfyUI-aki-v2/python/python.exe -m pytest --import-mode=importlib tests/`
   - **49 passed in 30.01s**（覆盖链式采样、端到端四镜头流水线、潜变量缝合、多分镜节点、配额验证、二采增强、分段 VAE 解码）。
3. **工作流完整性与链路自检**：
   - `tools/generate_multiclip_workflow.py` 内部校验 15 条连线拓扑完整无断连，顺利写入秋叶工作流库。

---

## 5. 未竟任务与下一步计划（接手者必读）

### 5.1 核心攻坚任务：RefMod 引用在 `@` 菜单中识别为视频素材
- **问题现状**：
  在主节点 `FeiHouEasyH3MultiClip`（Node 2）上，虽然定义了可选输入 `refmods`（`H3_REF_MODS`），且后端 `multi_clip_core.py` 与 `multi_clip_node.py` 已经支持了 `refmod_count` 的配额与索引偏移计算（将 RefMod 视为全局视频占位，普通视频顺延到 `@视频2`），但**前端 `web/modules/mention_menu.js` 尚未对接 RefMod**。
  目前 `@` 菜单只从 `data.global_media` 和 `curClip.media` 读取本地上传的文件，当上游连接了 `Load H3 RefMods` 时，输入 `@` 弹窗中没有 RefMod 选项，用户无法像在旧版 FeiHou 节点（`FeiHouEasyH3Media`）那样直接通过 `@` 插入引用。

### 5.2 遗留参考实现（旧版实现位置）
- 在 `web/feihou_easy_h3_ui.js` 中已有完备参考逻辑：
  - `refmodsInputIsConnected(node)`：检测 `node.inputs` 是否有名为 `refmods` 且已连线的槽位；
  - `refreshRefmodCatalog()`：向后端 `/feihou_easy_h3/refmods` 发送 GET 请求，获取已安装加载的 RefMod 元数据（含 `members`，其中包含 `kind === "video"` 或 `kind === "image"`）；
  - `refmodReferences(node)`：递归向上追溯至 `MiniMaxH3RefModsLoader` 或 `MiniMaxH3RefModsAxis`，根据槽位强度提取当前激活的 RefMod 条目；
  - `mentionOptions(node)`：将 RefMod 视频条目排在最前列（占据 `@视频1`），使普通上传视频自动变为 `@视频2`。

### 5.3 下个会话具体执行步骤
1. **对接 RefMod 目录元数据与连线探测**：
   - 在 `web/modules/` 中新建或在 `mention_menu.js` 中扩展 RefMod 检测函数，检查当前节点的 `refmods` 输入槽位是否有连线。
   - 调用 ComfyUI 后台已有的 `/feihou_easy_h3/refmods` API 接口获取可用 RefMod 列表。
2. **扩展 `getMentionOptions` 菜单生成**：
   - 在生成 `@` 弹出菜单时，若检测到 RefMod 接入且包含视频成员，在视频素材最前面生成 `@视频1 (xxx · RefMod)` 选项，打上紫色 `RefMod` 徽标。
   - 后续分镜/全局普通视频的 tag 和显示名称依次顺延为 `@视频2`、`@视频3`。
3. **UI 配额栏联动**：
   - 在 `ui_builder.js` 的配额提示中，如果接入了 RefMod，显示 `视已占用: 1 (RefMod)`，让用户一目了然。
4. **测试验证**：
   - 编写针对 RefMod 前端接入与后端 Stage 1/3 条件映射的自动化用例并验证。

---

## 6. 建议技能（Suggested Skills）
- `handoff`：本会话交接使用的标准技能。
- `diagnose`：排查 RefMod 连线与路由状态时建议调用的技能。
- `codebase-design`：评估前后端 RefMod 配额契约一致性。
