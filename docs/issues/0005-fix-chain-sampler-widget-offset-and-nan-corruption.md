# Issue 0005: 修复 ChainSampler 节点 ComfyUI 控件序列化偏移与 NaN/错误参数破坏

## 父问题
docs/issues/0002-motion-context-and-chain-sampler.md

## 要构建什么
修复 `FeiHouEasyH3ChainSampler` 在 ComfyUI 浏览器画布上加载时的控件值整体偏移与 `NaN` 错误：
1. 识别并对齐 `seed` 控件的 `control_after_generate: True` 特性：ComfyUI 前端会在 `seed` 后隐式注入 `生成后控制` 下拉控件；
2. 在工作流生成器 `tools/generate_multiclip_workflow.py` 中，在 `seed` (0) 与 `cfg` (1.0) 之间正确插入注入控件槽位（`"fixed"` / `"increment"`）；
3. 严格校正后续 21 个控件的映射关系，消除 `cfg`、`w_max`、`tiling_tiles` 等浮点/整数输入框因读取到字符串变成 `NaN` 的破坏性异常；
4. 纠正 `context_noise` 误读 12.00 的严重安全隐患（恢复为 0.0），确保 `shift_video=12.0`、`shift_audio=3.0`、`transition_step=6` 等关键 H3 双时钟与二采调度参数准确映射；
5. 精简过长节点标题，防止在画布缩放下右侧文本与输入端子重叠。

## 验收标准
- [x] 工作流导出的 Node 5 `widgets_values` 严格包含注入的 `生成后控制` 槽位，总长度由 22 扩为 23 项
- [x] 浏览器加载 Node 5 时无任何 `NaN` 出现，`cfg` 正确显示 `1.0`，`w_max` 正确显示 `1.0`，`tiling_tiles` 正确显示 `2`
- [x] `context_noise` 正确显示为 `0.00`，`shift_video` 正确显示为 `12.00`，`shift_audio` 正确显示为 `3.00`
- [x] `transition_step` 正确显示为 `6`，`sampling_engine` 正确选中 `selflift_avatar`
- [x] 自动化测试验证 API Prompt 编译不受影响且保持 100% 连通

## 被阻塞于
无 - 可以立即开始
