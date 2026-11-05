# Issue 0001: 核心领域模型与 Latent 双通道周期裁切拼接内核

## 父问题
docs/prd/0001-multi-clip-long-video.md

## 要构建什么
构建长视频长效资产管理与潜变量缝合的底层核心模块，包含：
1. `MultiClipContext` 规范定义与配额计算引擎：管理全局与各分镜配置，精确计算 9 图/3 视/3 音配额消耗，根据全局素材占用量计算各分镜卡槽起始标号，并处理前缀级联提示词；
2. `H3LatentStitcher` 潜变量缝合内核：对连续片段的 AV Latent 进行数学对齐。针对后续片段，在视频通道精确裁切首部 7 个 latent steps，在音频通道裁切首部 30 个 40Hz steps，并在时间轴拼接，重新封装为标准的 H3 NestedTensor。
3. 全面单元测试：验证配额越界、RefMod 占用顺延、时序相位相干性与张量结构。

## 验收标准
- [x] 配额计算引擎能根据全局图片数 $N_{img}$ 计算分镜剩余图片数 $9 - N_{img}$ 并标注起始索引为 $N_{img} + 1$
- [x] RefMod 视频正确计入全局视频配额，占据 Video 1，后续视频自动顺延至 Video 2 及以上
- [x] 提示词级联引擎在全局提示词存在时自动以换行作为前缀拼接分镜提示词
- [x] `H3LatentStitcher` 成功切除视频首部 7 步、音频首部 30 步，并正确输出拼接张量 `[1, 16, T1 + T2 - 7, H, W]`
- [x] 编写测试并通过 `tests/test_multi_clip_quota.py` 与 `tests/test_latent_stitcher.py`

## 被阻塞于
无 - 可以立即开始
