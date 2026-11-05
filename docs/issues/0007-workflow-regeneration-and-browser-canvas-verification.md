# Issue 0007: 重新编译生成 7 节点工作流并同步到 ComfyUI 用户目录进行视觉与测试验证

## 父问题
docs/issues/0004-chunked-vae-decode-and-e2e-workflow.md

## 要构建什么
基于 Issue 0005 与 Issue 0006 的修复成果，重新生成并部署 7 节点多分镜长视频工作流：
1. 更新 `tools/generate_multiclip_workflow.py`：
   - 更新 Node 5 的 `widgets_values` 数组，嵌入 `control_after_generate` 槽位，确保 23 项控件与 LiteGraph 严格 1:1 对齐；
   - 更新 Node 2 的建议外框大小（`[600, 760]`），确保 DOM 组件天然完全展开；
   - 优化 Node 5 标题长度为 `5. FeiHou Easy H3 链式采样缝合执行器 (SelfLift二采)`；
2. 同步生成以下两处目标文件：
   - 仓库工作流：`workflows/feihou_h3_multiclip_7nodes.json`
   - ComfyUI 默认用户工作流：`X:\ComfyUI-aki-v2\ComfyUI\user\default\workflows\FeiHou_H3_MultiClip_LongVideo_7Nodes.json`
3. 适配 `tools/run_multiclip_test.py` 中的 `build_api_prompt`，使其兼容 23 项新格式与历史 22 项旧格式；
4. 运行全量单元测试与 API 编译验证，确保 0 报错。

## 验收标准
- [x] `generate_multiclip_workflow.py` 运行无报错，两处目标 JSON 文件完成同步写入
- [x] 导出的 JSON 符合 ComfyUI RFC4122 GUID 与 `version: 0.4` 标准
- [x] `run_multiclip_test.py --check-only` 验证 API 图正确编译，无任何浮点解析或类型异常
- [x] 用户在浏览器 ComfyUI 中重新加载工作流时，界面美观、参数对齐、0 个 NaN

## 被阻塞于
- docs/issues/0005-fix-chain-sampler-widget-offset-and-nan-corruption.md
- docs/issues/0006-multi-clip-ui-refinement-and-tab-layout.md
