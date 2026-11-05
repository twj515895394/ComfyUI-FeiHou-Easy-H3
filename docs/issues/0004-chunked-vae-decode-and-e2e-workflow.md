# Issue 0004: 实现长视频分块 VAE 解码器与工作流端到端验证

## 父问题
docs/prd/0001-multi-clip-long-video.md

## 要构建什么
构建超长视频时序无缝分块 VAE 解码器及端到端工作流范例：
1. `FeiHouEasyH3VAEDecode` 节点：接收超长视频 Latent 与 VAE，在时间轴上按照安全批次（如 128 帧）进行时序重叠窗口解码与平滑融合，彻底杜绝 30 秒长视频在 16GB/24GB 显卡上的 VRAM OOM；
2. 搭建极简 7 节点端到端长视频工作流示例，替换原 78 节点工作流，验证四段直连生成完整效果。

## 验收标准
- [x] 注册 ComfyUI 节点 `FeiHouEasyH3VAEDecode`
- [x] 针对 4 段长视频拼接后的 Latent 执行分块解码，显存峰值低于直接解码且接缝处无闪烁伪影
- [x] 导出包含 7 个核心节点的新版极简长视频工作流范例 JSON
- [x] 验证端到端无报错通过

## 被阻塞于
- docs/issues/0002-motion-context-and-chain-sampler.md
- docs/issues/0003-multi-clip-tab-ui-component.md
