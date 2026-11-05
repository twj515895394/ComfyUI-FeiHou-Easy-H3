/**
 * CSS stylesheet injection for FeiHou Easy H3 Multi-Clip UI.
 */

export function installStyles() {
    let style = document.getElementById("feihou-h3-multi-clip-style");
    if (!style) {
        style = document.createElement("style");
        style.id = "feihou-h3-multi-clip-style";
        document.head.appendChild(style);
    }
    style.textContent = `
      .fh-mc-container {
        display: flex;
        flex-direction: column;
        gap: 8px;
        width: 100%;
        box-sizing: border-box;
        padding: 6px 10px;
        color: #e2e8f0;
        font-family: system-ui, -apple-system, sans-serif;
        user-select: none;
        overflow-y: auto !important;
        overflow-x: hidden !important;
        max-height: 520px;
        scrollbar-width: thin;
      }
      .fh-mc-container::-webkit-scrollbar {
        width: 6px;
      }
      .fh-mc-container::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.25);
        border-radius: 3px;
      }
      .fh-mc-container::-webkit-scrollbar-thumb {
        background: rgba(168, 85, 247, 0.45);
        border-radius: 3px;
      }
      .fh-mc-container::-webkit-scrollbar-thumb:hover {
        background: rgba(168, 85, 247, 0.75);
      }
      .fh-mc-tab-bar {
        position: sticky !important;
        top: 0 !important;
        z-index: 10 !important;
        background: #181920 !important;
        display: flex !important;
        flex-wrap: wrap !important;
        align-items: center !important;
        gap: 6px !important;
        padding: 4px 0 8px 0 !important;
        margin-bottom: 4px !important;
        border-bottom: 1px solid rgba(255, 255, 255, 0.16) !important;
        flex-shrink: 0 !important;
        min-height: 42px !important;
        overflow: visible !important;
        box-sizing: border-box !important;
      }
      .fh-mc-tab-btn {
        display: inline-flex !important;
        align-items: center !important;
        gap: 6px !important;
        padding: 6px 12px !important;
        border: 1px solid rgba(255, 255, 255, 0.2) !important;
        border-radius: 6px !important;
        background: rgba(255, 255, 255, 0.08) !important;
        color: rgba(255, 255, 255, 0.85) !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        cursor: pointer !important;
        transition: all 0.15s ease !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
        line-height: 1.4 !important;
      }
      .fh-mc-tab-btn-title {
        max-width: 140px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        display: inline-block;
        vertical-align: middle;
      }
      .fh-mc-tab-btn:hover {
        background: rgba(168, 85, 247, 0.25) !important;
        color: #fff !important;
        border-color: rgba(168, 85, 247, 0.6) !important;
      }
      .fh-mc-tab-btn.is-active {
        background: #8b5cf6 !important;
        color: #ffffff !important;
        border-color: #c084fc !important;
        box-shadow: 0 0 10px rgba(139, 92, 246, 0.6) !important;
      }
      .fh-mc-tab-close {
        display: inline-flex !important;
        align-items: center !important;
        justify-content: center !important;
        width: 16px !important;
        height: 16px !important;
        border-radius: 50% !important;
        font-size: 11px !important;
        line-height: 1 !important;
        opacity: 0.6 !important;
        transition: all 0.12s ease !important;
        margin-left: 2px !important;
        flex-shrink: 0 !important;
      }
      .fh-mc-tab-close:hover {
        opacity: 1 !important;
        background: rgba(239, 68, 68, 0.8) !important;
        color: #fff !important;
      }
      .fh-mc-tab-add {
        display: inline-flex !important;
        align-items: center !important;
        gap: 4px !important;
        padding: 6px 12px !important;
        border: 1px dashed rgba(168, 85, 247, 0.6) !important;
        border-radius: 6px !important;
        background: rgba(168, 85, 247, 0.12) !important;
        color: #d8b4fe !important;
        font-size: 12px !important;
        font-weight: 600 !important;
        cursor: pointer !important;
        transition: all 0.15s ease !important;
        white-space: nowrap !important;
        flex-shrink: 0 !important;
        line-height: 1.4 !important;
      }
      .fh-mc-tab-add:hover {
        background: rgba(168, 85, 247, 0.3) !important;
        color: #fff !important;
        border-color: #c084fc !important;
      }
      .fh-mc-section {
        display: flex;
        flex-direction: column;
        gap: 6px;
        background: rgba(0, 0, 0, 0.2);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 6px;
        padding: 8px;
        box-sizing: border-box;
      }
      .fh-mc-switch-row {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 10px;
        background: rgba(139, 92, 246, 0.12);
        border: 1px solid rgba(168, 85, 247, 0.35);
        border-radius: 6px;
        margin-bottom: 4px;
        box-sizing: border-box;
      }
      .fh-mc-switch-label-wrap {
        display: flex;
        flex-direction: column;
        gap: 2px;
      }
      .fh-mc-switch-title {
        font-size: 12px;
        font-weight: 700;
        color: #f1f5f9;
        display: flex;
        align-items: center;
        gap: 6px;
      }
      .fh-mc-switch-desc {
        font-size: 11px;
        color: rgba(255, 255, 255, 0.6);
        line-height: 1.3;
      }
      .fh-mc-switch {
        position: relative;
        display: inline-block;
        width: 38px;
        height: 22px;
        flex-shrink: 0;
      }
      .fh-mc-switch input {
        opacity: 0;
        width: 0;
        height: 0;
      }
      .fh-mc-switch-slider {
        position: absolute;
        cursor: pointer;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background-color: rgba(255, 255, 255, 0.2);
        transition: .2s;
        border-radius: 22px;
        border: 1px solid rgba(255, 255, 255, 0.3);
      }
      .fh-mc-switch-slider:before {
        position: absolute;
        content: "";
        height: 16px;
        width: 16px;
        left: 2px;
        bottom: 2px;
        background-color: white;
        transition: .2s;
        border-radius: 50%;
      }
      .fh-mc-switch input:checked + .fh-mc-switch-slider {
        background-color: #8b5cf6;
        border-color: #a855f7;
      }
      .fh-mc-switch input:checked + .fh-mc-switch-slider:before {
        transform: translateX(16px);
      }
      .fh-mc-disabled-notice {
        padding: 8px 12px;
        background: rgba(234, 179, 8, 0.12);
        border: 1px dashed rgba(234, 179, 8, 0.4);
        border-radius: 6px;
        font-size: 11px;
        color: #fef08a;
        line-height: 1.4;
      }
      .fh-mc-label-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        font-size: 11px;
        font-weight: 600;
        color: rgba(255, 255, 255, 0.7);
        gap: 6px;
      }
      .fh-mc-badge-purple {
        background: rgba(168, 85, 247, 0.2);
        color: #c084fc;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 10px;
        border: 1px solid rgba(168, 85, 247, 0.35);
        white-space: nowrap;
      }
      .fh-mc-prompt-input {
        width: 100%;
        min-height: 110px;
        height: 110px;
        background: #0f1015;
        border: 1px solid rgba(255, 255, 255, 0.15);
        border-radius: 6px;
        color: #f8fafc;
        padding: 8px 10px;
        font-size: 13px;
        line-height: 1.5;
        font-family: inherit;
        box-sizing: border-box;
        resize: vertical;
        outline: none;
        transition: border-color 0.15s ease;
      }
      .fh-mc-prompt-input:focus {
        border-color: #a855f7;
        box-shadow: 0 0 0 1px rgba(168, 85, 247, 0.4);
      }
      .fh-mc-prompt-input:disabled {
        opacity: 0.45;
        background: rgba(0, 0, 0, 0.4);
        cursor: not-allowed;
      }
      .fh-mc-mention-btn {
        background: rgba(168, 85, 247, 0.18);
        border: 1px solid rgba(168, 85, 247, 0.45);
        color: #d8b4fe;
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        transition: all 0.15s ease;
        line-height: 1.3;
      }
      .fh-mc-mention-btn:hover {
        background: rgba(168, 85, 247, 0.35);
        color: #fff;
        border-color: #c084fc;
      }
      .fh-mc-gallery-grid {
        display: grid;
        grid-template-columns: repeat(3, minmax(0, 1fr));
        gap: 6px;
        box-sizing: border-box;
      }
      .fh-mc-gallery-toggle {
        background: rgba(255, 255, 255, 0.08);
        border: 1px solid rgba(255, 255, 255, 0.18);
        color: rgba(255, 255, 255, 0.85);
        border-radius: 4px;
        padding: 2px 8px;
        font-size: 11px;
        font-weight: 600;
        cursor: pointer;
        display: inline-flex;
        align-items: center;
        gap: 4px;
        transition: all 0.15s ease;
        line-height: 1.3;
      }
      .fh-mc-gallery-toggle:hover {
        background: rgba(168, 85, 247, 0.25);
        color: #fff;
        border-color: rgba(168, 85, 247, 0.6);
      }
      .is-images-collapsed .fh-mc-slot:nth-child(n+4) {
        display: none !important;
      }
      .fh-mc-slot {
        position: relative;
        aspect-ratio: 16/9;
        background: #1e1f29;
        border: 1px dashed rgba(255, 255, 255, 0.25);
        border-radius: 6px;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        color: rgba(255, 255, 255, 0.6);
        cursor: pointer;
        overflow: hidden;
        transition: all 0.15s ease;
        box-sizing: border-box;
      }
      .fh-mc-slot:hover {
        border-color: #a855f7;
        background: #252636;
        color: #f1f5f9;
      }
      .fh-mc-slot.has-file {
        border-style: solid;
        border-color: rgba(168, 85, 247, 0.4);
        background: #111218;
      }
      .fh-mc-slot.has-file[draggable="true"] {
        cursor: grab;
      }
      .fh-mc-slot.has-file[draggable="true"]:active {
        cursor: grabbing;
      }
      .fh-mc-slot.is-dragover {
        border-color: #38bdf8 !important;
        background: rgba(56, 189, 248, 0.22) !important;
        box-shadow: 0 0 16px rgba(56, 189, 248, 0.6) !important;
        color: #38bdf8 !important;
        transform: scale(1.03);
        z-index: 5;
      }
      .fh-mc-slot.is-reorder-target {
        border-color: #c084fc !important;
        background: rgba(192, 132, 252, 0.25) !important;
        box-shadow: 0 0 16px rgba(192, 132, 252, 0.6) !important;
        transform: scale(1.03);
        z-index: 5;
      }
      .fh-mc-slot.is-reordering {
        opacity: 0.45;
        border-style: dotted !important;
      }
      .fh-mc-slot.is-uploading {
        opacity: 0.7;
        pointer-events: none;
        border-color: #f59e0b !important;
        background: rgba(245, 158, 11, 0.2) !important;
      }
      .fh-mc-gallery-grid.is-dragover {
        outline: 2px dashed #38bdf8;
        outline-offset: 4px;
        border-radius: 8px;
        background: rgba(56, 189, 248, 0.06);
      }
      .fh-mc-slot-thumb {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .fh-mc-slot-badge {
        position: absolute;
        top: 3px;
        left: 3px;
        background: rgba(0, 0, 0, 0.75);
        color: #c084fc;
        padding: 1px 4px;
        border-radius: 3px;
        font-size: 9px;
        font-weight: 700;
        z-index: 2;
        pointer-events: none;
      }
      .fh-mc-slot-del {
        position: absolute;
        top: 3px;
        right: 3px;
        width: 16px;
        height: 16px;
        border-radius: 50%;
        background: rgba(239, 68, 68, 0.85);
        color: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 10px;
        font-weight: 700;
        cursor: pointer;
        z-index: 3;
        transition: transform 0.12s ease;
      }
      .fh-mc-slot-del:hover {
        transform: scale(1.15);
        background: #dc2626;
      }
      .fh-mc-overrides-box {
        display: flex;
        flex-direction: column;
        gap: 6px;
        padding: 6px 8px;
        background: rgba(0, 0, 0, 0.3);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 6px;
      }
      .fh-mc-overrides-row {
        display: flex;
        align-items: center;
        gap: 8px;
        font-size: 11px;
        color: rgba(255, 255, 255, 0.8);
      }
      .fh-mc-overrides-row input[type="checkbox"] {
        cursor: pointer;
        accent-color: #8b5cf6;
      }
      .fh-mc-input-num {
        width: 55px;
        background: #0f1015;
        border: 1px solid rgba(255, 255, 255, 0.2);
        border-radius: 4px;
        color: #fff;
        padding: 2px 4px;
        font-size: 11px;
        box-sizing: border-box;
      }
      .fh-mc-mention-menu {
        position: fixed;
        z-index: 99999;
        width: 250px;
        max-height: 280px;
        overflow-y: auto;
        padding: 5px;
        border: 1px solid rgba(168, 85, 247, 0.45);
        border-radius: 8px;
        background: #181920;
        box-shadow: 0 12px 32px rgba(0, 0, 0, 0.7), 0 0 12px rgba(168, 85, 247, 0.25);
        color: #f1f5f9;
        font-family: system-ui, -apple-system, sans-serif;
        box-sizing: border-box;
      }
      .fh-mc-mention-title {
        padding: 4px 6px 6px;
        color: rgba(255, 255, 255, 0.55);
        font-size: 11px;
        font-weight: 600;
        border-bottom: 1px solid rgba(255, 255, 255, 0.1);
        margin-bottom: 4px;
        display: flex;
        align-items: center;
        justify-content: space-between;
      }
      .fh-mc-mention-empty {
        padding: 10px;
        color: rgba(255, 255, 255, 0.4);
        font-size: 11px;
        text-align: center;
      }
      .fh-mc-mention-item {
        display: grid;
        grid-template-columns: 32px minmax(0, 1fr);
        gap: 8px;
        align-items: center;
        min-height: 38px;
        padding: 4px 6px;
        border-radius: 6px;
        cursor: pointer;
        transition: all 0.12s ease;
      }
      .fh-mc-mention-item:hover, .fh-mc-mention-item.is-active {
        background: rgba(168, 85, 247, 0.22);
        outline: 1px solid rgba(168, 85, 247, 0.5);
      }
      .fh-mc-mention-thumb {
        width: 32px;
        height: 32px;
        border-radius: 4px;
        background: rgba(255, 255, 255, 0.08);
        display: flex;
        align-items: center;
        justify-content: center;
        font-size: 15px;
        overflow: hidden;
      }
      .fh-mc-mention-thumb img {
        width: 100%;
        height: 100%;
        object-fit: cover;
      }
      .fh-mc-mention-info {
        display: flex;
        flex-direction: column;
        min-width: 0;
      }
      .fh-mc-mention-tag {
        font-size: 12px;
        font-weight: 700;
        color: #c084fc;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        display: flex;
        align-items: center;
      }
      .fh-mc-refmod-tag-badge {
        font-size: 10px;
        background: #9333ea;
        color: #ffffff;
        padding: 1px 5px;
        border-radius: 3px;
        margin-left: 6px;
        font-weight: 500;
        line-height: 1.2;
        display: inline-block;
      }
      .fh-mc-mention-desc {
        font-size: 10px;
        color: rgba(255, 255, 255, 0.5);
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        margin-top: 1px;
      }
    `;
    document.head.append(style);
}
