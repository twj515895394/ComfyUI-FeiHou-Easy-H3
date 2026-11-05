# FeiHou Easy H3 多分镜组件 RefMod 连线与 @ 提及自动补全支持交接文档

- **快照标识**：`handoff-20261105-180000-refmod-mention-support`
- **更新时间**：2026-11-05 18:00:00
- **当前状态**：Node 2 (`FeiHouEasyH3MultiClip`) 的 `refmods` 连线探测、目录缓存、@ 菜单优先识别为视频素材、本地素材编号自动顺延、以及后端 prompt 提及标签规范化已全部完成，51 项单元测试全部通过。

---

## 1. 修复背景与问题定位

在多镜头分镜大组件（Node 2: `FeiHouEasyH3MultiClip`）接入 `Load H3 RefMods`（`MiniMaxH3RefModsLoader` / `MiniMaxH3RefModsAxis`）时，存在以下问题：
1. **@ 菜单未感知 RefMod**：在全局提示词或分镜提示词输入框中输入 `@` 或点击 `@` 按钮时，下拉菜单仅扫描当前节点上传的普通媒体文件，未包含上游 `refmods` 输入槽连接的 RefMod 资产。
2. **编号顺延未生效**：RefMod 包含视频资产时，应优先分配 `@视频1`，本地上传的全局视频应从 `@视频2` 开始顺延，分镜私有视频进一步顺延；由于前端未探测上游 RefMod，导致编号错位。
3. **Prompt 规范化对齐**：前端用户在提示词中输入 `@视频1: [name]` 或 `@视频1`，但 MiniMax H3 官方底层 CLIP Tokenizer 与 `refmod_compat.validate_reference_tags` 仅识别 `<Video 1>`、`<Picture 1>`、`<Audio 1>` 格式的特殊 Token，未做转换会导致模型当作普通字符串处理且触发校验异常。

---

## 2. 实施方案与技术实现

### 2.1 前端 RefMod 助手模块 (`web/modules/refmod_helper.js`)
- **连线判断**：`refmodsInputIsConnected(node)` 实时检查 `node.inputs` 中 `name === "refmods"` 且 `link != null`。
- **图链路穿透寻源**：`refmodSourceNode(node, depth)` 递归穿越 `Reroute`、`SetNode` / `GetNode` 原生 LiteGraph 虚拟连接，定位真实的 `MiniMaxH3RefModsLoader` 或 `MiniMaxH3RefModsAxis` 节点。
- **RefMod 目录缓存**：`refreshRefmodCatalog(force)` 异步请求 ComfyUI 后端 `/feihou_easy_h3/refmods` 接口获取 RefMod 成员（member）详细元数据（kind: `video` / `image` / `audio`），5 秒内自带防抖缓存。
- **引用项动态生成**：`refmodReferences(node)` 解析源节点的 active slots（8 个槽位），读取 `strength_*`、`copies_*`、`components_*` 等配置，为每个激活的 RefMod 成员生成统一结构：
  ```javascript
  {
      type: "video" | "image" | "audio",
      name: member.name,
      modName: name,
      fullLabel: `${member.name} · RefMod`,
      source: `RefMod · ${name}`,
      refmodKey: "...",
      previewUrl: ""
  }
  ```

### 2.2 前端 @ 提及菜单集成 (`web/modules/mention_menu.js`)
- 在构建 `@` 菜单选项（`getMentionOptions(node, isGlobal, clipIndex)`）时：
  1. 首先调用 `refmodReferences(node)`，将激活的 RefMod 过滤分类（视频/图片/音频）；
  2. RefMod 视频优先分配 `@视频1`、`@视频2` 等序号，并在下拉菜单中展示专属紫色徽章 `<span class="fh-mc-refmod-tag-badge">RefMod</span>`；
  3. 全局上传视频的序号自动从 `refmodVidCount + 1` 起算；
  4. 当前分镜私有视频的序号自动从 `refmodVidCount + globalVidCount + 1` 起算；
  5. 图片与音频同样支持 RefMod 优先排序与顺延。
- 样式增强（`web/modules/styles.js`）：新增 `.fh-mc-refmod-tag-badge` 样式（深紫高亮、圆角小标签）。

### 2.3 素材栏与配额徽章联动 (`web/modules/ui_builder.js`)
- 在画廊栏目中，若探测到连接的 RefMod：
  - 全局视频配额标签动态显示为 `视 (已占 X/3, 含RefMod)`；
  - 全局视频卡槽序号自动顺延至 `@视频 (N)` 起始；
  - 动态计算并限制剩余可上传的最大视频槽位数。

### 2.4 主入口生命周期钩子 (`web/feihou_easy_h3_multi_clip.js`)
- `onConfigure`：检测到 `refmods` 连线时预取 `refreshRefmodCatalog(true)` 并重新刷新 UI。
- `onConnectionsChange`：监听 `refmods` 槽位的连线与断开事件，自动刷新目录并在 50ms 后触发 `buildUI`，实现连线/断线时配额与 `@` 菜单的实时热响应。

### 2.5 后端 Prompt 标签自动规范化 (`multi_clip_node.py`)
- 新增正则替换函数 `normalize_prompt_mentions(prompt: str) -> str`：
  - 将 `@(?:视频|Video)\s*(\d+)(?:\s*[:：]\s*\[?[^\]\s\n,，。！？]+\]?)?` 替换为 `<Video \1>`；
  - 将 `@(?:图|图片|Picture|Image)\s*(\d+)(?:\s*[:：]\s*\[?[^\]\s\n,，。！？]+\]?)?` 替换为 `<Picture \1>`；
  - 将 `@(?:音频|Audio)\s*(\d+)(?:\s*[:：]\s*\[?[^\]\s\n,，。！？]+\]?)?` 替换为 `<Audio \1>`。
- 在 `MODE_REFERENCE` 模式下，将各分镜级组合提示词 `effective_prompt = normalize_prompt_mentions(merged_prompt)`：
  - 正确传递给 `_reference_conditioning(...)`，无缝通过 `refmod_compat.validate_reference_tags` 校验；
  - 正确触发 `bundle.clip.tokenize` 生成交叉注意力引导；
  - 在素材映射汇总表 `reference_map` 中补充记录 `@视频1(RefMod:name)`。

---

## 3. 验证与测试结果

1. **JavaScript 语法校验**：
   ```bash
   node -c web/feihou_easy_h3_multi_clip.js web/modules/refmod_helper.js web/modules/mention_menu.js web/modules/ui_builder.js web/modules/styles.js web/modules/widget_sync.js
   ```
   - 结果：全部通过，0 警告，0 错误。

2. **单元测试与回归测试**：
   ```bash
   "X:/ComfyUI-aki-v2/python/python.exe" -m pytest --import-mode=importlib tests/
   ```
   - 结果：**51 passed in 25.59s**（原 49 项全部通过，新增 2 项专门覆盖 `normalize_prompt_mentions` 与 `test_generate_with_refmods` 配额顺延及映射表生成）。

---

## 4. 下一步计划 (Next Steps)

1. **用户人工真机验证**：
   - 用户在秋叶启动器中重启 ComfyUI 后，在 Web 界面加载 `workflows/01_h3_multi_clip_long_video_pipeline.json`；
   - 在 Node 2 的 `refmods` 端口接入 `Load H3 RefMods`，在全局或分镜提示词框中键入 `@`，验证下拉菜单第一项是否正确展示 RefMod 视频并标有 RefMod 徽章；
   - 上传全局视频和分镜视频，确认普通视频的编号是否依次顺延为 `@视频2`、`@视频3`；
   - 确认提示词中使用 `@视频1: [name]` 或 `@视频1` 时，终端 Stage 1/3 日志正常输出且无 Tag 报错。
