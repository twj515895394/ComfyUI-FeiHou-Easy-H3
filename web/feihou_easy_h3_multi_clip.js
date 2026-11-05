/**
 * FeiHou Easy H3 Multi-Clip Web Extension Entry Point.
 * Modularized according to the Single Responsibility Principle (SRP).
 */

import { app } from "../../scripts/app.js";
import { installStyles } from "./modules/styles.js";
import { buildUI } from "./modules/ui_builder.js";
import { closeMentionMenu } from "./modules/mention_menu.js";
import { refreshRefmodCatalog, refmodsInputIsConnected } from "./modules/refmod_helper.js";
import {
    hideNativeGlobalPrompt,
    syncResolutionWidgets,
    syncModeWidgets,
    updateContainerHeight,
    sanitizeChainSamplerWidgets,
    getGenerationMode
} from "./modules/widget_sync.js";

const NODE_CLASS = "FeiHouEasyH3MultiClip";

app.registerExtension({
    name: "FeiHouEasyH3.MultiClip",
    setup() {
        installStyles();
    },
    beforeRegisterNodeDef(nodeType, nodeData) {
        // Node 5: ChainSampler widget guard and runtime sanitization
        if (nodeData?.name === "FeiHouEasyH3ChainSampler") {
            const origCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const res = origCreated?.apply(this, arguments);
                sanitizeChainSamplerWidgets(this);
                return res;
            };

            const origConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                const res = origConfigure?.apply(this, arguments);
                sanitizeChainSamplerWidgets(this);
                return res;
            };

            const origDrawForeground = nodeType.prototype.onDrawForeground;
            nodeType.prototype.onDrawForeground = function () {
                if (this.widgets) {
                    for (const w of this.widgets) {
                        if (w && Number.isNaN(w.value)) {
                            sanitizeChainSamplerWidgets(this);
                            break;
                        }
                    }
                }
                return origDrawForeground?.apply(this, arguments);
            };
            return;
        }

        // Node 2: MultiClip interactive tabbed UI and asset management
        if (nodeData?.name !== NODE_CLASS) return;
        installStyles();

        const originalCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            installStyles();
            const result = originalCreated?.apply(this, arguments);

            const container = document.createElement("div");
            container.className = "fh-mc-container";

            this.addDOMWidget("multi_clip_ui", "multi_clip_ui", container, {
                serialize: false,
                getMinHeight: () => {
                    const m = getGenerationMode(this);
                    return m === "text" ? 380 : m === "image" ? 520 : 640;
                },
            });

            this.__fhMcContainer = container;

            hideNativeGlobalPrompt(this);
            syncResolutionWidgets(this);
            syncModeWidgets(this, () => {
                if (this.__fhMcContainer) {
                    buildUI(this, this.__fhMcContainer);
                    updateContainerHeight(this, this.__fhMcContainer);
                }
            });

            try {
                buildUI(this, container);
            } catch (err) {
                console.error("[FeiHouEasyH3.MultiClip] Error in onNodeCreated buildUI:", err);
            }

            if (Array.isArray(this.size)) {
                const genMode = getGenerationMode(this);
                const targetH = genMode === "text" ? 640 : genMode === "image" ? 820 : 1000;
                this.setSize?.([Math.max(700, this.size[0]), Math.max(targetH, this.size[1])]);
                updateContainerHeight(this, container);
            }
            return result;
        };

        const originalConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const result = originalConfigure?.apply(this, arguments);
            if (refmodsInputIsConnected(this)) {
                void refreshRefmodCatalog(true);
            }
            hideNativeGlobalPrompt(this);
            syncResolutionWidgets(this);
            syncModeWidgets(this, () => {
                if (this.__fhMcContainer) {
                    buildUI(this, this.__fhMcContainer);
                    updateContainerHeight(this, this.__fhMcContainer);
                }
            });
            if (this.__fhMcContainer) {
                try {
                    buildUI(this, this.__fhMcContainer);
                    updateContainerHeight(this, this.__fhMcContainer);
                } catch (err) {
                    console.error("[FeiHouEasyH3.MultiClip] Error in onConfigure buildUI:", err);
                }
            }
            return result;
        };

        const originalConnectionsChange = nodeType.prototype.onConnectionsChange;
        nodeType.prototype.onConnectionsChange = function (type, index, isConnected, linkInfo, input) {
            const result = originalConnectionsChange?.apply(this, arguments);
            const slot = (this.inputs || [])[index];
            if (slot && String(slot.name || "") === "refmods") {
                setTimeout(async () => {
                    await refreshRefmodCatalog(true);
                    if (this.__fhMcContainer) {
                        try {
                            buildUI(this, this.__fhMcContainer);
                            updateContainerHeight(this, this.__fhMcContainer);
                        } catch (err) {
                            console.error("[FeiHouEasyH3.MultiClip] Error in onConnectionsChange buildUI:", err);
                        }
                    }
                }, 50);
            }
            return result;
        };

        const originalResize = nodeType.prototype.onResize;
        nodeType.prototype.onResize = function (size) {
            const result = originalResize?.apply(this, arguments);
            if (this.__fhMcContainer) {
                updateContainerHeight(this, this.__fhMcContainer);
            }
            return result;
        };

        const originalDrawForeground = nodeType.prototype.onDrawForeground;
        nodeType.prototype.onDrawForeground = function () {
            hideNativeGlobalPrompt(this);
            syncResolutionWidgets(this);
            syncModeWidgets(this);
            return originalDrawForeground?.apply(this, arguments);
        };

        const originalRemoved = nodeType.prototype.onRemoved;
        nodeType.prototype.onRemoved = function () {
            closeMentionMenu();
            return originalRemoved?.apply(this, arguments);
        };
    },
});
