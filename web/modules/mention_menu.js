/**
 * @ Mention menu and autocomplete for FeiHou Easy H3 Multi-Clip.
 */

import { api } from "../../../scripts/api.js";
import { getData } from "./data_model.js";
import { getGenerationMode } from "./widget_sync.js";
import { refmodsInputIsConnected, refreshRefmodCatalog, refmodReferences } from "./refmod_helper.js";

let activeMentionMenu = null;

export function closeMentionMenu() {
    if (activeMentionMenu) {
        if (activeMentionMenu.element && activeMentionMenu.element.parentNode) {
            activeMentionMenu.element.parentNode.removeChild(activeMentionMenu.element);
        }
        if (activeMentionMenu.cleanup) {
            activeMentionMenu.cleanup();
        }
        activeMentionMenu = null;
    }
}

export function getCaretCoordinates(element, position) {
    const div = document.createElement("div");
    const style = window.getComputedStyle(element);

    const properties = [
        "boxSizing", "width", "height", "overflowX", "overflowY",
        "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
        "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
        "fontStyle", "fontVariant", "fontWeight", "fontSize",
        "lineHeight", "fontFamily", "textAlign", "textTransform",
        "textIndent", "letterSpacing", "wordSpacing",
        "whiteSpace", "wordBreak", "wordWrap"
    ];

    div.style.position = "absolute";
    div.style.visibility = "hidden";
    div.style.top = "0px";
    div.style.left = "0px";
    div.style.pointerEvents = "none";

    for (const prop of properties) {
        div.style[prop] = style[prop];
    }

    div.style.whiteSpace = "pre-wrap";
    div.style.wordBreak = "break-word";
    div.style.width = element.clientWidth + "px";

    div.textContent = element.value.substring(0, position);

    const span = document.createElement("span");
    span.textContent = element.value.substring(position, position + 1) || "@";
    div.appendChild(span);

    document.body.appendChild(div);
    const spanOffset = {
        top: span.offsetTop + parseInt(style.borderTopWidth || "0", 10),
        left: span.offsetLeft + parseInt(style.borderLeftWidth || "0", 10),
        height: parseInt(style.lineHeight || "18", 10)
    };
    document.body.removeChild(div);

    const rect = element.getBoundingClientRect();
    return {
        top: rect.top + spanOffset.top - element.scrollTop,
        left: rect.left + spanOffset.left - element.scrollLeft,
        height: spanOffset.height
    };
}

export function getMentionOptions(node, isGlobal, clipIndex) {
    const genMode = getGenerationMode(node);
    if (genMode === "text") return [];

    const data = getData(node);
    const enableGlobal = Boolean(data.enable_global);
    if (isGlobal && !enableGlobal) return [];

    const options = [];

    const gMedia = (enableGlobal && data.global_media) ? data.global_media : { images: [], videos: [], audios: [] };
    const gImages = gMedia.images || [];
    const gVideos = gMedia.videos || [];
    const gAudios = gMedia.audios || [];

    if (genMode === "image") {
        const curClip = !isGlobal && Array.isArray(data.clips) ? data.clips.find(c => c.index === clipIndex) : null;
        const targetImgs = (!isGlobal && curClip?.media?.images?.length)
            ? curClip.media.images
            : (enableGlobal ? gImages : (curClip?.media?.images || []));
        const customDefs = [
            { tag: "@图1", label: "@图1 (首帧)", source: "首帧 (起幅起始画面)" },
            { tag: "@图2", label: "@图2 (尾帧)", source: "尾帧 (止幅结束画面，可选)" },
        ];
        for (let i = 0; i < 2; i++) {
            const file = targetImgs[i];
            options.push({
                tag: customDefs[i].tag,
                label: customDefs[i].label,
                hasFile: Boolean(file),
                type: "image",
                fileName: file ? file.split(/[/\\]/).pop() : "",
                source: file ? `${customDefs[i].source}: ${file.split(/[/\\]/).pop()}` : customDefs[i].source,
                previewUrl: file ? api.apiURL(`/view?filename=${encodeURIComponent(file)}&type=input`) : "",
            });
        }
        return options;
    }

    // 1. Reference mode: check if RefMods input is connected
    const isRefConnected = refmodsInputIsConnected(node);
    if (isRefConnected) {
        void refreshRefmodCatalog();
    }
    const rawRefs = isRefConnected ? refmodReferences(node) : [];
    const refmodVideos = rawRefs.filter(r => r.type === "video");
    const refmodImages = rawRefs.filter(r => r.type === "image");
    const refmodAudios = rawRefs.filter(r => r.type === "audio");

    const modVidCount = refmodVideos.length;
    const modImgCount = refmodImages.length;
    const modAudCount = refmodAudios.length;

    // Inject RefMod options (always available to global and all clips)
    refmodVideos.forEach((ref, idx) => {
        const ordinal = idx + 1;
        options.push({
            tag: `@视频${ordinal}`,
            label: `@视频${ordinal}: [${ref.name || ref.modName}]`,
            hasFile: true,
            isRefMod: true,
            type: "video",
            fileName: ref.name || ref.modName,
            source: `RefMod · ${ref.modName}`,
            previewUrl: "",
        });
    });

    refmodImages.forEach((ref, idx) => {
        const ordinal = idx + 1;
        options.push({
            tag: `@图${ordinal}`,
            label: `@图${ordinal}: [${ref.name || ref.modName}]`,
            hasFile: true,
            isRefMod: true,
            type: "image",
            fileName: ref.name || ref.modName,
            source: `RefMod · ${ref.modName}`,
            previewUrl: "",
        });
    });

    refmodAudios.forEach((ref, idx) => {
        const ordinal = idx + 1;
        options.push({
            tag: `@音频${ordinal}`,
            label: `@音频${ordinal}: [${ref.name || ref.modName}]`,
            hasFile: true,
            isRefMod: true,
            type: "audio",
            fileName: ref.name || ref.modName,
            source: `RefMod · ${ref.modName}`,
            previewUrl: "",
        });
    });

    const gImgCount = gImages.length;
    const gVidCount = gVideos.length;
    const gAudCount = gAudios.length;

    // 2. Global media slots
    if (isGlobal && enableGlobal) {
        const maxGlobalImg = Math.max(0, 9 - modImgCount);
        for (let i = 0; i < maxGlobalImg; i++) {
            const ordinal = modImgCount + 1 + i;
            const file = gImages[i];
            options.push({
                tag: `@图${ordinal}`,
                label: `@图${ordinal}`,
                hasFile: Boolean(file),
                type: "image",
                fileName: file ? file.split(/[/\\]/).pop() : "",
                source: file ? `全局素材: ${file.split(/[/\\]/).pop()}` : "全局图片 (未上传)",
                previewUrl: file ? api.apiURL(`/view?filename=${encodeURIComponent(file)}&type=input`) : "",
            });
        }

        const maxGlobalVid = Math.max(0, 3 - modVidCount);
        for (let i = 0; i < maxGlobalVid; i++) {
            const ordinal = modVidCount + 1 + i;
            const file = gVideos[i];
            options.push({
                tag: `@视频${ordinal}`,
                label: `@视频${ordinal}`,
                hasFile: Boolean(file),
                type: "video",
                fileName: file ? file.split(/[/\\]/).pop() : "",
                source: file ? `全局素材: ${file.split(/[/\\]/).pop()}` : "全局视频 (未上传)",
                previewUrl: "",
            });
        }

        const maxGlobalAud = Math.max(0, 3 - modAudCount);
        for (let i = 0; i < maxGlobalAud; i++) {
            const ordinal = modAudCount + 1 + i;
            const file = gAudios[i];
            options.push({
                tag: `@音频${ordinal}`,
                label: `@音频${ordinal}`,
                hasFile: Boolean(file),
                type: "audio",
                fileName: file ? file.split(/[/\\]/).pop() : "",
                source: file ? `全局素材: ${file.split(/[/\\]/).pop()}` : "全局音频 (未上传)",
                previewUrl: "",
            });
        }
    } else {
        // Clip Tab
        if (enableGlobal) {
            // 已上传或首个占位全局素材
            const maxGlobalImg = Math.max(0, 9 - modImgCount);
            const showGImgCount = Math.max(gImgCount, Math.min(1, maxGlobalImg));
            for (let i = 0; i < showGImgCount; i++) {
                const ordinal = modImgCount + 1 + i;
                const file = gImages[i];
                options.push({
                    tag: `@图${ordinal}`,
                    label: `@图${ordinal}`,
                    hasFile: Boolean(file),
                    type: "image",
                    fileName: file ? file.split(/[/\\]/).pop() : "",
                    source: file ? `全局素材: ${file.split(/[/\\]/).pop()}` : "全局图片 (未上传)",
                    previewUrl: file ? api.apiURL(`/view?filename=${encodeURIComponent(file)}&type=input`) : "",
                });
            }

            const maxGlobalVid = Math.max(0, 3 - modVidCount);
            const showGVidCount = Math.max(gVidCount, Math.min(1, maxGlobalVid));
            for (let i = 0; i < showGVidCount; i++) {
                const ordinal = modVidCount + 1 + i;
                const file = gVideos[i];
                options.push({
                    tag: `@视频${ordinal}`,
                    label: `@视频${ordinal}`,
                    hasFile: Boolean(file),
                    type: "video",
                    fileName: file ? file.split(/[/\\]/).pop() : "",
                    source: file ? `全局素材: ${file.split(/[/\\]/).pop()}` : "全局视频 (未上传)",
                    previewUrl: "",
                });
            }

            const maxGlobalAud = Math.max(0, 3 - modAudCount);
            const showGAudCount = Math.max(gAudCount, Math.min(1, maxGlobalAud));
            for (let i = 0; i < showGAudCount; i++) {
                const ordinal = modAudCount + 1 + i;
                const file = gAudios[i];
                options.push({
                    tag: `@音频${ordinal}`,
                    label: `@音频${ordinal}`,
                    hasFile: Boolean(file),
                    type: "audio",
                    fileName: file ? file.split(/[/\\]/).pop() : "",
                    source: file ? `全局素材: ${file.split(/[/\\]/).pop()}` : "全局音频 (未上传)",
                    previewUrl: "",
                });
            }
        }

        // 列出当前分镜独享/顺延卡槽素材
        const curClip = data.clips?.find(c => c.index === clipIndex);
        if (curClip) {
            const cMedia = curClip.media || { images: [], videos: [], audios: [] };
            const cImages = cMedia.images || [];
            const cVideos = cMedia.videos || [];
            const cAudios = cMedia.audios || [];

            const startImgOrdinal = enableGlobal ? (modImgCount + gImgCount + 1) : (modImgCount + 1);
            const remImg = enableGlobal ? Math.max(0, 9 - modImgCount - gImgCount) : Math.max(0, 9 - modImgCount);
            for (let i = 0; i < remImg; i++) {
                const ordinal = startImgOrdinal + i;
                const file = cImages[i];
                options.push({
                    tag: `@图${ordinal}`,
                    label: `@图${ordinal}`,
                    hasFile: Boolean(file),
                    type: "image",
                    fileName: file ? file.split(/[/\\]/).pop() : "",
                    source: file ? `${curClip.name}独享: ${file.split(/[/\\]/).pop()}` : `${curClip.name}独享卡槽`,
                    previewUrl: file ? api.apiURL(`/view?filename=${encodeURIComponent(file)}&type=input`) : "",
                });
            }

            const startVidOrdinal = enableGlobal ? (modVidCount + gVidCount + 1) : (modVidCount + 1);
            const remVid = enableGlobal ? Math.max(0, 3 - modVidCount - gVidCount) : Math.max(0, 3 - modVidCount);
            for (let i = 0; i < remVid; i++) {
                const ordinal = startVidOrdinal + i;
                const file = cVideos[i];
                options.push({
                    tag: `@视频${ordinal}`,
                    label: `@视频${ordinal}`,
                    hasFile: Boolean(file),
                    type: "video",
                    fileName: file ? file.split(/[/\\]/).pop() : "",
                    source: file ? `${curClip.name}独享: ${file.split(/[/\\]/).pop()}` : `${curClip.name}独享卡槽`,
                    previewUrl: "",
                });
            }

            const startAudOrdinal = enableGlobal ? (modAudCount + gAudCount + 1) : (modAudCount + 1);
            const remAud = enableGlobal ? Math.max(0, 3 - modAudCount - gAudCount) : Math.max(0, 3 - modAudCount);
            for (let i = 0; i < remAud; i++) {
                const ordinal = startAudOrdinal + i;
                const file = cAudios[i];
                options.push({
                    tag: `@音频${ordinal}`,
                    label: `@音频${ordinal}`,
                    hasFile: Boolean(file),
                    type: "audio",
                    fileName: file ? file.split(/[/\\]/).pop() : "",
                    source: file ? `${curClip.name}独享: ${file.split(/[/\\]/).pop()}` : `${curClip.name}独享卡槽`,
                    previewUrl: "",
                });
            }
        }
    }

    // 排序：RefMod 最优先，已上传素材次之，未上传卡槽最后
    options.sort((a, b) => {
        if (a.isRefMod && !b.isRefMod) return -1;
        if (!a.isRefMod && b.isRefMod) return 1;
        if (a.hasFile && !b.hasFile) return -1;
        if (!a.hasFile && b.hasFile) return 1;
        return 0;
    });

    return options;
}

export function insertMentionTag(textarea, atIndex, tag) {
    const val = textarea.value;
    const cursorPos = textarea.selectionStart;

    const before = val.substring(0, atIndex);
    const after = val.substring(cursorPos);
    const replacement = tag + " ";

    textarea.value = before + replacement + after;
    const newPos = before.length + replacement.length;
    textarea.selectionStart = textarea.selectionEnd = newPos;
    textarea.focus();

    textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

export function renderMentionMenuItems(state) {
    const { element, options, activeIndex, textarea, atIndex } = state;
    element.innerHTML = "";

    const title = document.createElement("div");
    title.className = "fh-mc-mention-title";
    title.innerHTML = `<span>引用素材 <small style="opacity:0.6;font-weight:normal;">(↑↓选择, 回车确认)</small></span>`;
    element.appendChild(title);

    if (options.length === 0) {
        const empty = document.createElement("div");
        empty.className = "fh-mc-mention-empty";
        empty.textContent = "未找到匹配素材";
        element.appendChild(empty);
        return;
    }

    options.forEach((opt, idx) => {
        const item = document.createElement("div");
        item.className = `fh-mc-mention-item ${idx === activeIndex ? "is-active" : ""}`;

        const thumb = document.createElement("div");
        thumb.className = "fh-mc-mention-thumb";
        if (opt.isRefMod) {
            thumb.textContent = opt.type === "video" ? "🎬" : (opt.type === "image" ? "🖼️" : "🎵");
            thumb.style.background = "rgba(147, 51, 234, 0.25)";
            thumb.style.borderRadius = "4px";
            thumb.style.display = "flex";
            thumb.style.alignItems = "center";
            thumb.style.justifyContent = "center";
        } else if (opt.type === "image") {
            if (opt.previewUrl) {
                const img = document.createElement("img");
                img.src = opt.previewUrl;
                thumb.appendChild(img);
            } else {
                thumb.textContent = "🖼️";
                thumb.style.opacity = "0.5";
            }
        } else if (opt.type === "video") {
            thumb.textContent = "🎬";
            if (!opt.hasFile) thumb.style.opacity = "0.5";
        } else {
            thumb.textContent = "🎵";
            if (!opt.hasFile) thumb.style.opacity = "0.5";
        }

        const info = document.createElement("div");
        info.className = "fh-mc-mention-info";

        const tag = document.createElement("div");
        tag.className = "fh-mc-mention-tag";
        if (opt.isRefMod) {
            tag.innerHTML = `<span>${opt.tag}</span> <span class="fh-mc-refmod-tag-badge">RefMod</span>`;
        } else {
            tag.textContent = opt.tag;
        }

        const desc = document.createElement("div");
        desc.className = "fh-mc-mention-desc";
        desc.textContent = opt.source;

        info.appendChild(tag);
        info.appendChild(desc);

        item.appendChild(thumb);
        item.appendChild(info);

        item.onpointermove = () => {
            if (state.activeIndex !== idx) {
                state.activeIndex = idx;
                const items = element.querySelectorAll(".fh-mc-mention-item");
                items.forEach((it, i) => it.classList.toggle("is-active", i === idx));
            }
        };

        item.onpointerdown = (e) => {
            e.preventDefault();
            e.stopPropagation();
            insertMentionTag(textarea, atIndex, opt.tag);
            closeMentionMenu();
        };

        element.appendChild(item);
    });

    const activeItem = element.querySelectorAll(".fh-mc-mention-item")[activeIndex];
    if (activeItem) {
        activeItem.scrollIntoView({ block: "nearest" });
    }
}

export function openMentionMenu(node, textarea, atIndex, query, isGlobal, clipIndex) {
    const allOptions = getMentionOptions(node, isGlobal, clipIndex);
    const filteredOptions = query ? allOptions.filter(opt => {
        const q = query.toLowerCase();
        return opt.tag.toLowerCase().includes(q) ||
               opt.source.toLowerCase().includes(q) ||
               opt.label.toLowerCase().includes(q) ||
               opt.fileName.toLowerCase().includes(q);
    }) : allOptions;

    if (activeMentionMenu && activeMentionMenu.textarea === textarea) {
        activeMentionMenu.atIndex = atIndex;
        activeMentionMenu.query = query;
        activeMentionMenu.options = filteredOptions;
        activeMentionMenu.activeIndex = Math.min(activeMentionMenu.activeIndex, Math.max(0, filteredOptions.length - 1));
        renderMentionMenuItems(activeMentionMenu);
        return;
    }

    closeMentionMenu();

    const menu = document.createElement("div");
    menu.className = "fh-mc-mention-menu";

    const coords = getCaretCoordinates(textarea, atIndex);
    menu.style.left = `${Math.max(10, Math.round(coords.left))}px`;
    menu.style.top = `${Math.max(10, Math.round(coords.top + coords.height + 4))}px`;

    const handleOutsideClick = (e) => {
        if (!menu.contains(e.target) && e.target !== textarea) {
            closeMentionMenu();
        }
    };
    setTimeout(() => {
        window.addEventListener("pointerdown", handleOutsideClick, true);
        window.addEventListener("wheel", handleOutsideClick, { passive: true });
    }, 10);

    const state = {
        element: menu,
        textarea,
        node,
        atIndex,
        query,
        options: filteredOptions,
        activeIndex: 0,
        cleanup: () => {
            window.removeEventListener("pointerdown", handleOutsideClick, true);
            window.removeEventListener("wheel", handleOutsideClick, { passive: true });
        }
    };
    activeMentionMenu = state;

    document.body.appendChild(menu);
    renderMentionMenuItems(state);

    requestAnimationFrame(() => {
        if (!activeMentionMenu || activeMentionMenu.element !== menu) return;
        const rect = menu.getBoundingClientRect();
        if (rect.bottom > window.innerHeight - 10) {
            const flippedTop = coords.top - rect.height - 4;
            if (flippedTop > 10) {
                menu.style.top = `${Math.round(flippedTop)}px`;
            }
        }
        if (rect.right > window.innerWidth - 10) {
            menu.style.left = `${Math.max(10, Math.round(window.innerWidth - rect.width - 10))}px`;
        }
    });
}

export function triggerMentionAtCaret(node, textarea, isGlobal, clipIndex) {
    textarea.focus();
    const pos = textarea.selectionStart;
    const val = textarea.value;
    textarea.value = val.substring(0, pos) + "@" + val.substring(pos);
    textarea.selectionStart = textarea.selectionEnd = pos + 1;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
}

export function attachMentionListeners(node, textarea, isGlobal, curClipIndex) {
    textarea.addEventListener("keydown", (e) => {
        if (!activeMentionMenu || activeMentionMenu.textarea !== textarea) return;

        if (e.key === "ArrowDown") {
            e.preventDefault();
            e.stopPropagation();
            const len = activeMentionMenu.options.length;
            if (len > 0) {
                activeMentionMenu.activeIndex = (activeMentionMenu.activeIndex + 1) % len;
                renderMentionMenuItems(activeMentionMenu);
            }
            return;
        }

        if (e.key === "ArrowUp") {
            e.preventDefault();
            e.stopPropagation();
            const len = activeMentionMenu.options.length;
            if (len > 0) {
                activeMentionMenu.activeIndex = (activeMentionMenu.activeIndex - 1 + len) % len;
                renderMentionMenuItems(activeMentionMenu);
            }
            return;
        }

        if (e.key === "Enter" || e.key === "Tab") {
            if (activeMentionMenu.options.length > 0) {
                e.preventDefault();
                e.stopPropagation();
                const selected = activeMentionMenu.options[activeMentionMenu.activeIndex];
                if (selected) {
                    insertMentionTag(textarea, activeMentionMenu.atIndex, selected.tag);
                }
                closeMentionMenu();
                return;
            }
        }

        if (e.key === "Escape") {
            e.preventDefault();
            e.stopPropagation();
            closeMentionMenu();
            return;
        }
    });

    const checkMention = () => {
        const pos = textarea.selectionStart;
        const textBefore = textarea.value.substring(0, pos);
        const match = textBefore.match(/@([^\s@]*)$/);
        if (match) {
            const atIndex = match.index;
            const query = match[1];
            openMentionMenu(node, textarea, atIndex, query, isGlobal, curClipIndex);
        } else {
            closeMentionMenu();
        }
    };

    textarea.addEventListener("input", checkMention);
    textarea.addEventListener("keyup", (e) => {
        if (["ArrowUp", "ArrowDown", "Enter", "Tab", "Escape"].includes(e.key)) return;
        checkMention();
    });
    textarea.addEventListener("click", checkMention);
    textarea.addEventListener("blur", () => {
        setTimeout(() => {
            if (activeMentionMenu && activeMentionMenu.textarea === textarea) {
                closeMentionMenu();
            }
        }, 200);
    });
}
