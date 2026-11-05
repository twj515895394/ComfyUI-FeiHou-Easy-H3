# Issue 0002: 内聚 Motion Context 算法并实现多引擎链式采样器 (FeiHouEasyH3ChainSampler)

## 父问题
docs/prd/0001-multi-clip-long-video.md

## 要构建什么
构建链式采样的中枢执行节点 `FeiHouEasyH3ChainSampler`：
1. 内聚 Motion Context 算法：从前序片段的采样 Latent 尾部自动抽取 22 帧图像 token 与 18 帧音频 token，生成时序重叠锚点并注入当前分镜 conditioning，完全摆脱对外部 Motion Context 节点的依赖；
2. 采样策略引擎：支持 `standard_euler`（标准 Euler 扩散）与 `selflift_avatar`（SelfLift Avatar 极速二采），并支持分镜独立的步数覆盖与种子递增（`increment`）；
3. 循环调度与缝合流转：按序执行分镜采样，将各段结果调用 `H3LatentStitcher` 进行拼接，最终仅输出单一完整长视频 `LATENT`。

## 验收标准
- [x] 注册 ComfyUI 节点 `FeiHouEasyH3ChainSampler`
- [x] 节点提供 `sampling_engine` 下拉选项（`standard_euler` 与 `selflift_avatar`）
- [x] 分镜 2..N 能够自动从前序 Latent 提取 tail 锚点并注入 conditioning
- [x] 针对 `selflift_avatar` 模式，成功将大组件输出的 model 映射为 low_res_model，second_sampling_model 映射为 high_res_model
- [x] 支持种子步进（片段 1 为 seed，片段 2 为 seed+1，以此类推）
- [x] 循环执行结束后，输出拼接完成的单一完整 AV Latent
- [x] 编写测试并通过 `tests/test_chain_sampler.py`

## 被阻塞于
- docs/issues/0001-core-data-model-and-latent-stitcher.md
