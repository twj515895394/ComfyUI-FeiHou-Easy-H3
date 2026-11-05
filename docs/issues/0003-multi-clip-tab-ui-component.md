# Issue 0003: 开发 FeiHouEasyH3MultiClip 节点与前端多 Tab 交互界面

## 父问题
docs/prd/0001-multi-clip-long-video.md

## 要构建什么
构建长视频分镜与素材资产管理组件 `FeiHouEasyH3MultiClip` 及其前端 UI：
1. 后端节点定义：注册 `FeiHouEasyH3MultiClip`，包含 `h3_bundle`、可选 `refmods` 与 `lora_stack` 输入，输出 `model`、`second_sampling_model`、`multi_clip_context` 及 `prompt_preview`；
2. 前端多 Tab 交互：在现有飞猴 UI 风格（紫色卡片、圆形角标）基础上，实现【全局 Tab】与【分镜 Tab（默认 1、2，支持 `+` / `✕` 增减）】；
3. 动态配额与卡槽联动渲染：分镜 Tab 动态仅渲染剩余卡槽（方案 A），序号自动从 $N+1$ 开始顺延标号；
4. 提示词与素材映射预览：实时更新 `prompt_preview`，清晰呈现各分镜合并后的完整提示词及引用映射表；
5. 工作流保存与恢复：保证所有 Tab 的配置、分镜覆盖参数和上传素材在 ComfyUI 工作流保存与刷新后完全保留。

## 验收标准
- [x] 注册 ComfyUI 节点 `FeiHouEasyH3MultiClip`
- [x] 前端呈现 Tab 栏，包含全局 Tab 和分镜 Tab 1、2，支持点击 `[+]` 新增分镜与 `[✕]` 删除分镜
- [x] 分镜 Tab 按照方案 A 仅展示剩余卡槽，且卡槽编号根据全局占用量自动顺延（如 6~9，视频 2~3）
- [x] 分镜 Tab 提供秒数与采样步数独立覆盖开关
- [x] `prompt_preview` 正确输出每个分镜的级联提示词与素材对应关系
- [x] 刷新页面或重新加载工作流时，多 Tab 数据与卡槽媒体完整持久化恢复

## 被阻塞于
- docs/issues/0001-core-data-model-and-latent-stitcher.md
- docs/issues/0002-motion-context-and-chain-sampler.md
