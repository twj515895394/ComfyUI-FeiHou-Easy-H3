/**
 * Gallery slots, card rendering, and upload handling for FeiHou Easy H3 Multi-Clip.
 * Supports file drag-and-drop from OS, multiple-file sequential fill, and slot reordering.
 */

import { api } from "../../../scripts/api.js";
import { uploadFile } from "./data_model.js";

const REORDER_MIME = "application/x-feihou-slot-reorder";

function isFileMatchingType(file, type) {
    if (!file) return false;
    const mime = (file.type || "").toLowerCase();
    const name = (file.name || "").toLowerCase();
    if (type === "image") {
        if (mime.startsWith("image/")) return true;
        return /\.(png|jpe?g|webp|bmp|gif|avif|tiff?)$/i.test(name);
    }
    if (type === "video") {
        if (mime.startsWith("video/")) return true;
        return /\.(mp4|webm|mov|mkv|avi|flv|wmv|m4v)$/i.test(name);
    }
    if (type === "audio") {
        if (mime.startsWith("audio/")) return true;
        return /\.(mp3|wav|flac|ogg|m4a|aac|wma|opus)$/i.test(name);
    }
    return false;
}

export function renderGallerySection(
    node,
    container,
    parent,
    title,
    type,
    capacity,
    startOrdinal,
    fileList,
    onUpdate,
    customLabels = null,
    disabled = false,
    buildUIFn = null
) {
    const wrap = document.createElement("div");
    wrap.className = "fh-mc-section";
    if (disabled) {
        wrap.style.opacity = "0.5";
        wrap.style.pointerEvents = "none";
    }

    const head = document.createElement("div");
    head.className = "fh-mc-label-row";

    const titleSpan = document.createElement("span");
    titleSpan.textContent = title;
    head.appendChild(titleSpan);

    const isImage = type === "image";
    const canCollapse = isImage && capacity > 3;
    const isExpanded = canCollapse ? Boolean(node.properties?.imageGalleryExpanded) : true;

    if (canCollapse && !disabled) {
        wrap.classList.toggle("is-images-collapsed", !isExpanded);
        wrap.classList.toggle("is-images-expanded", isExpanded);

        const toggleBtn = document.createElement("button");
        toggleBtn.type = "button";
        toggleBtn.className = "fh-mc-gallery-toggle";
        const hasExtraFiles = (fileList || []).slice(3).some(Boolean);
        if (isExpanded) {
            toggleBtn.textContent = "收起图片 ▲";
        } else if (hasExtraFiles) {
            const filledCount = (fileList || []).filter(Boolean).length;
            toggleBtn.textContent = `展开图片 (${filledCount}/${capacity}) ▼`;
        } else {
            toggleBtn.textContent = `展开图片 (${capacity}) ▼`;
        }
        toggleBtn.onclick = (e) => {
            e.stopPropagation();
            e.preventDefault();
            node.properties = node.properties || {};
            node.properties.imageGalleryExpanded = !isExpanded;
            if (buildUIFn) {
                buildUIFn(node, container);
            }
        };
        head.appendChild(toggleBtn);
    }

    wrap.appendChild(head);

    if (capacity <= 0) {
        const fullNotice = document.createElement("div");
        fullNotice.style.fontSize = "10px";
        fullNotice.style.color = "rgba(255,255,255,0.4)";
        fullNotice.style.fontStyle = "italic";
        fullNotice.textContent = "（该类型配额已由全局占满，无需在此上传）";
        wrap.appendChild(fullNotice);
        parent.appendChild(wrap);
        return;
    }

    const grid = document.createElement("div");
    grid.className = "fh-mc-gallery-grid";

    // Allow dropping multiple files anywhere on the grid area
    if (!disabled) {
        grid.addEventListener("dragover", (event) => {
            event.preventDefault();
            event.stopPropagation();
            grid.classList.add("is-dragover");
        });
        grid.addEventListener("dragleave", (event) => {
            if (!grid.contains(event.relatedTarget)) {
                grid.classList.remove("is-dragover");
            }
        });
        grid.addEventListener("drop", async (event) => {
            event.preventDefault();
            event.stopPropagation();
            grid.classList.remove("is-dragover");
            // If drop hit a specific slot, the slot's drop handler will take care of it
            if (event.target.closest(".fh-mc-slot")) return;

            const files = Array.from(event.dataTransfer?.files || []);
            const validFiles = files.filter(f => isFileMatchingType(f, type));
            if (validFiles.length === 0) return;

            const next = [...fileList];
            let fileIdx = 0;
            // 1st pass: fill available empty slots
            for (let idx = 0; idx < capacity && fileIdx < validFiles.length; idx++) {
                if (!next[idx]) {
                    try {
                        const up = await uploadFile(validFiles[fileIdx++], type);
                        next[idx] = up;
                    } catch (err) {
                        console.error("[FeiHouMultiClip] Upload error:", err);
                    }
                }
            }
            // 2nd pass: if more files remain, fill from beginning
            for (let idx = 0; idx < capacity && fileIdx < validFiles.length; idx++) {
                try {
                    const up = await uploadFile(validFiles[fileIdx++], type);
                    next[idx] = up;
                } catch (err) {
                    console.error("[FeiHouMultiClip] Upload error:", err);
                }
            }
            onUpdate(next);
        });
    }

    const tagPrefix = type === "image" ? "图" : type === "video" ? "视频" : "音频";

    for (let i = 0; i < capacity; i++) {
        const ordinal = startOrdinal + i;
        const filePath = fileList[i] || "";
        const slot = document.createElement("div");
        slot.className = `fh-mc-slot ${filePath ? "has-file" : ""}`;
        slot.dataset.slotIndex = String(i);
        slot.dataset.mediaType = type;

        const badge = document.createElement("div");
        badge.className = "fh-mc-slot-badge";
        badge.textContent = customLabels?.[i]?.badge || `@${tagPrefix}${ordinal}`;
        slot.appendChild(badge);

        if (filePath) {
            slot.title = `拖拽可与其它槽位调换顺序或替换，点击可更换${tagPrefix}`;
            if (type === "image") {
                const img = document.createElement("img");
                img.className = "fh-mc-slot-thumb";
                img.draggable = false;
                img.src = api.apiURL(`/view?filename=${encodeURIComponent(filePath)}&type=input`);
                slot.appendChild(img);
            } else {
                const icon = document.createElement("span");
                icon.textContent = type === "video" ? "🎬 视频" : "🎵 音频";
                slot.appendChild(icon);
            }

            if (!disabled) {
                // Delete button
                const del = document.createElement("div");
                del.className = "fh-mc-slot-del";
                del.textContent = "✕";
                del.title = "删除此素材";
                del.onclick = (e) => {
                    e.stopPropagation();
                    const next = [...fileList];
                    next.splice(i, 1);
                    onUpdate(next);
                };
                slot.appendChild(del);

                // Slot draggable for reordering
                slot.draggable = true;
                slot.addEventListener("dragstart", (event) => {
                    slot.__suppressClickUntil = Date.now() + 350;
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData(REORDER_MIME, JSON.stringify({
                        type,
                        index: i,
                        nodeId: String(node.id ?? "")
                    }));
                    slot.classList.add("is-reordering");
                });
                slot.addEventListener("dragend", () => {
                    slot.classList.remove("is-reordering");
                    container.querySelectorAll(".is-dragover, .is-reorder-target, .is-reordering")
                        .forEach(el => el.classList.remove("is-dragover", "is-reorder-target", "is-reordering"));
                });

                // Click filled slot to replace file
                slot.onclick = (e) => {
                    if (Date.now() < (slot.__suppressClickUntil || 0)) return;
                    if (e.target.closest(".fh-mc-slot-del")) return;
                    e.stopPropagation();
                    const input = document.createElement("input");
                    input.type = "file";
                    input.accept = type === "image" ? "image/*" : type === "video" ? "video/*" : "audio/*";
                    input.onchange = async () => {
                        if (input.files && input.files[0]) {
                            try {
                                slot.classList.add("is-uploading");
                                const uploaded = await uploadFile(input.files[0], type);
                                const next = [...fileList];
                                next[i] = uploaded;
                                onUpdate(next);
                            } catch (err) {
                                alert("更换失败: " + err.message);
                            } finally {
                                slot.classList.remove("is-uploading");
                            }
                        }
                    };
                    input.click();
                };
            }
        } else if (!disabled) {
            slot.title = `点击或拖拽文件到此处上传${tagPrefix}`;
            const hint = document.createElement("span");
            hint.textContent = customLabels?.[i]?.hint || `+ 上传${tagPrefix}`;
            slot.appendChild(hint);

            slot.onclick = () => {
                if (Date.now() < (slot.__suppressClickUntil || 0)) return;
                const input = document.createElement("input");
                input.type = "file";
                input.accept = type === "image" ? "image/*" : type === "video" ? "video/*" : "audio/*";
                input.onchange = async () => {
                    if (input.files && input.files[0]) {
                        try {
                            slot.classList.add("is-uploading");
                            const uploaded = await uploadFile(input.files[0], type);
                            const next = [...fileList];
                            next[i] = uploaded;
                            onUpdate(next);
                        } catch (err) {
                            alert("上传失败: " + err.message);
                        } finally {
                            slot.classList.remove("is-uploading");
                        }
                    }
                };
                input.click();
            };
        } else {
            const hint = document.createElement("span");
            hint.textContent = `（已禁用）`;
            slot.appendChild(hint);
        }

        // Drag & Drop handlers for each slot (works for both empty and filled slots)
        if (!disabled) {
            slot.addEventListener("dragenter", (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (event.dataTransfer?.types?.includes(REORDER_MIME.toLowerCase())) {
                    slot.classList.add("is-reorder-target");
                } else {
                    slot.classList.add("is-dragover");
                }
            });

            slot.addEventListener("dragover", (event) => {
                event.preventDefault();
                event.stopPropagation();
                if (event.dataTransfer?.types?.includes(REORDER_MIME.toLowerCase())) {
                    slot.classList.add("is-reorder-target");
                } else {
                    slot.classList.add("is-dragover");
                }
            });

            slot.addEventListener("dragleave", (event) => {
                if (!slot.contains(event.relatedTarget)) {
                    slot.classList.remove("is-dragover", "is-reorder-target");
                }
            });

            slot.addEventListener("drop", async (event) => {
                event.preventDefault();
                event.stopPropagation();
                slot.classList.remove("is-dragover", "is-reorder-target");

                // Check for slot-to-slot reorder first
                const reorderRaw = event.dataTransfer?.getData(REORDER_MIME);
                if (reorderRaw) {
                    try {
                        const reorder = JSON.parse(reorderRaw);
                        if (reorder.type === type && reorder.nodeId === String(node.id ?? "") && reorder.index !== i) {
                            const next = [...fileList];
                            const temp = next[reorder.index];
                            next[reorder.index] = next[i];
                            next[i] = temp;
                            onUpdate(next);
                            return;
                        }
                    } catch {}
                }

                // Check for OS file drop
                const files = Array.from(event.dataTransfer?.files || []);
                const validFiles = files.filter(f => isFileMatchingType(f, type));
                if (validFiles.length === 0) {
                    if (files.length > 0) {
                        const expected = type === "image" ? "图片" : type === "video" ? "视频" : "音频";
                        alert(`格式不匹配：请拖入${expected}文件`);
                    }
                    return;
                }

                slot.classList.add("is-uploading");
                try {
                    const next = [...fileList];
                    for (let k = 0; k < validFiles.length; k++) {
                        const targetIdx = i + k;
                        if (targetIdx >= capacity) break;
                        const uploaded = await uploadFile(validFiles[k], type);
                        next[targetIdx] = uploaded;
                    }
                    onUpdate(next);
                } catch (err) {
                    alert("拖入上传失败: " + err.message);
                } finally {
                    slot.classList.remove("is-uploading");
                }
            });
        }

        grid.appendChild(slot);
    }
    wrap.appendChild(grid);
    parent.appendChild(wrap);
}

