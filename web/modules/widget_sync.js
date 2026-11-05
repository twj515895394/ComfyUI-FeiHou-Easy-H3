/**
 * Node widget synchronization, sizing, and ChainSampler sanitization for FeiHou Easy H3.
 */

export function hideNativeGlobalPrompt(node) {
    if (!node || !node.widgets) return;
    const w = node.widgets.find(x => x.name === "global_prompt");
    if (!w) return;
    w.computeSize = () => [0, -4];
    w.draw = () => {};
    w.hidden = true;
    if (w.inputEl) {
        w.inputEl.style.display = "none";
        w.inputEl.style.visibility = "hidden";
        w.inputEl.style.opacity = "0";
        w.inputEl.style.pointerEvents = "none";
        w.inputEl.style.height = "0px";
        w.inputEl.style.position = "absolute";
        w.inputEl.style.top = "-9999px";
    }
}

export function setWidgetVisible(widget, visible) {
    if (!widget) return;
    const isHidden = Boolean(widget.hidden);
    const shouldHide = !visible;
    if (isHidden === shouldHide) return;
    widget.hidden = shouldHide;
    if (shouldHide) {
        if (!widget.__fhOrigComputeSize) widget.__fhOrigComputeSize = widget.computeSize;
        if (!widget.__fhOrigDraw) widget.__fhOrigDraw = widget.draw;
        widget.computeSize = () => [0, -4];
        widget.draw = () => {};
        if (widget.inputEl) {
            widget.inputEl.style.display = "none";
            widget.inputEl.style.visibility = "hidden";
        }
    } else {
        if (widget.__fhOrigComputeSize) widget.computeSize = widget.__fhOrigComputeSize;
        if (widget.__fhOrigDraw) widget.draw = widget.__fhOrigDraw;
        if (widget.inputEl) {
            widget.inputEl.style.display = "";
            widget.inputEl.style.visibility = "";
        }
    }
}

export function getGenerationMode(node) {
    if (!node || !node.widgets) return "reference";
    const modeWidget = node.widgets.find(w => w.name === "mode");
    const raw = String(modeWidget?.value || "reference").toLowerCase().trim();
    if (raw === "text" || raw.includes("文生")) return "text";
    if (raw === "image" || raw.includes("首尾") || raw.includes("图生")) return "image";
    return "reference";
}

export function syncModeWidgets(node, onModeChanged = null) {
    if (!node || !node.widgets) return;
    const modeWidget = node.widgets.find(w => w.name === "mode");
    if (modeWidget && !modeWidget.__fhBound) {
        modeWidget.__fhBound = true;
        const origCallback = modeWidget.callback;
        modeWidget.callback = function (val) {
            const res = origCallback?.apply(this, arguments);
            const genMode = getGenerationMode(node);
            if (Array.isArray(node.size)) {
                if (genMode === "text") {
                    node.setSize?.([Math.max(620, node.size[0]), 560]);
                } else if (genMode === "image") {
                    node.setSize?.([Math.max(620, node.size[0]), 700]);
                } else {
                    node.setSize?.([Math.max(620, node.size[0]), 840]);
                }
            }
            if (onModeChanged) {
                onModeChanged(genMode);
            }
            node.setDirtyCanvas?.(true, true);
            return res;
        };
    }
}

export function syncResolutionWidgets(node) {
    if (!node || !node.widgets) return;
    const resWidget = node.widgets.find(w => w.name === "resolution");
    const val = String(resWidget?.value || "").toLowerCase();
    const isCustom = val === "custom" || val === "自定义";

    for (const w of node.widgets) {
        if (w.name === "aspect_ratio") {
            setWidgetVisible(w, !isCustom);
        } else if (w.name === "width" || w.name === "height") {
            setWidgetVisible(w, isCustom);
        }
    }

    if (resWidget && !resWidget.__fhBound) {
        resWidget.__fhBound = true;
        const origCallback = resWidget.callback;
        resWidget.callback = function () {
            const res = origCallback?.apply(this, arguments);
            syncResolutionWidgets(node);
            node.setDirtyCanvas?.(true, true);
            return res;
        };
    }
}

export function updateContainerHeight(node, container) {
    if (!node) return;
    const cont = container || node.__fhMcContainer;
    if (!cont || !Array.isArray(node.size)) return;
    const genMode = getGenerationMode(node);
    const minHeight = genMode === "text" ? 380 : genMode === "image" ? 520 : 640;
    // Top widgets occupy ~220px. Ensure container fills smoothly down to lower edge of node.
    const avail = Math.max(minHeight, Math.floor(node.size[1] - 225));
    cont.style.maxHeight = `${avail}px`;
}

const DEFAULT_CHAIN_SAMPLER_VALUES = {
    seed: 0,
    cfg: 1.0,
    sampling_engine: "selflift_avatar",
    seed_behavior: "increment",
    continuation_mode: "hybrid",
    context_noise: 0.0,
    shift_video: 12.0,
    shift_audio: 3.0,
    auto_shift_sigmas: true,
    transition_step: 6,
    lowres_scale: 0.5,
    rho: 0.0,
    w_min: 0.5,
    w_max: 1.0,
    upscaler_model: "h3_upscaler_lms_v0.1_fp32.safetensors",
    highres_tiling: false,
    tiling_mode: "auto",
    tiling_tiles: 2,
    tiling_axis: "auto",
    highres_tiling_mode: "global_stream",
    highres_token_chunk: 4096,
    highres_weight_cache_gb: 4.0
};

export function sanitizeChainSamplerWidgets(node) {
    if (!node || !node.widgets) return;
    for (const w of node.widgets) {
        if (!w || !w.name || w.name === "control_after_generate") continue;
        const def = DEFAULT_CHAIN_SAMPLER_VALUES[w.name];
        if (def === undefined) continue;

        if (typeof def === "number") {
            if (typeof w.value !== "number" || Number.isNaN(w.value)) {
                const parsed = parseFloat(w.value);
                w.value = Number.isNaN(parsed) ? def : parsed;
            }
        } else if (typeof def === "boolean") {
            if (typeof w.value !== "boolean") {
                w.value = Boolean(def);
            }
        } else if (typeof def === "string") {
            if (typeof w.value !== "string" || !w.value) {
                w.value = def;
            } else if (w.options && Array.isArray(w.options.values) && !w.options.values.includes(w.value)) {
                w.value = def;
            }
        }
    }
}
