# 0001 多分镜容器与 Latent 链式采样缝合架构

为了解决 MiniMax H3 多分镜工作流中 78 节点冗余连线、素材跨镜头重复录入以及像素层多次编解码的显存性能损耗，我们决定将长视频管线解耦为【多分镜素材容器组件 (`FeiHouEasyH3MultiClip`)】与【多模式链式采样执行器 (`FeiHouEasyH3ChainSampler`)】。前者提供全局与分镜 Tab 的配额联动及提示词级联，后者内聚 Motion Context 时序约束，在 Latent 空间直接按周期切除重叠区（视频 7 步、音频 30 步）并无缝拼接，最终仅输出完整时序 AV Latent 供外部单次解码。
