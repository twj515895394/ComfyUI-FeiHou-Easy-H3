# FeiHou Easy H3 工作流说明

## 中文说明

使用本文件夹中的工作流前，请先安装所需插件，并下载对应模型。

### 可能需要安装的插件

- `ComfyUI-FeiHou-Easy-H3`（本目录对应的节点包）
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)
- [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)

也可以在 ComfyUI Manager 中搜索插件名称安装。安装或更新后请重启 ComfyUI。

### 模型与资源

工作流需要的插件、模型和相关资源：

小肥猴的网盘：<https://pan.quark.cn/s/27fe4727197b>

不同工作流需要的模型可能不同，请按照工作流中的加载器选择对应文件。如果列表中找不到模型，请检查模型是否放入了正确的 `ComfyUI/models` 子目录，然后刷新或重启 ComfyUI。

部分工作流还需要额外的 LoRA 或其他自定义节点，具体以工作流中的节点为准。

### 长视频逐段续接示例

- 示例工作流：[02_h3_long_video_resumable_example.json](../workflows/02_h3_long_video_resumable_example.json)
- 参数、素材分镜和 Agent 逐段生成/审核操作手册：[H3 长视频可续接工作流手册](../docs/long-video-resumable-workflow.md)

The resumable long-video example and the agent's segment-by-segment production/review procedure are documented here: [H3 Resumable Long-Video Workflow Manual](../docs/long-video-resumable-workflow.md).

---

# FeiHou Easy H3 Workflow Guide

## English

Before using any workflow in this folder, install the required custom nodes and download the models used by that workflow.

### Required custom nodes

- `ComfyUI-FeiHou-Easy-H3` (this custom-node package)
- [ComfyUI-KJNodes](https://github.com/kijai/ComfyUI-KJNodes)
- [ComfyUI-VideoHelperSuite](https://github.com/Kosinkadink/ComfyUI-VideoHelperSuite)

You can also install them by searching for their names in ComfyUI Manager. Restart ComfyUI after installing or updating custom nodes.

### Models and assets

The plugins, models, and related assets used by the workflows are available here:

Xiao Fei Hou's cloud drive: <https://pan.quark.cn/s/27fe4727197b>

Model requirements may differ between workflows. Select the matching files in each workflow's loader node. If a model is not listed, place it in the correct `ComfyUI/models` subdirectory, then refresh or restart ComfyUI.

Some workflows may also require additional LoRAs or custom nodes. Please check the nodes included in the workflow.
