/**
 * Tab bar, Global tab, and Clip tab UI builder for FeiHou Easy H3 Multi-Clip.
 */

import { installStyles } from "./styles.js";
import { getData, syncData } from "./data_model.js";
import { getGenerationMode, hideNativeGlobalPrompt } from "./widget_sync.js";
import { attachMentionListeners, triggerMentionAtCaret } from "./mention_menu.js";
import { renderGallerySection } from "./gallery.js";
import { refmodsInputIsConnected, refreshRefmodCatalog, refmodReferences } from "./refmod_helper.js";

export function buildUI(node, container) {
    if (!node || !container) return;
    installStyles();
    hideNativeGlobalPrompt(node);
    container.innerHTML = "";
    const data = getData(node);
    if (!data || !Array.isArray(data.clips)) return;

    // Tab Bar
    const tabBar = document.createElement("div");
    tabBar.className = "fh-mc-tab-bar";

    const stopEvents = (e) => e.stopPropagation();
    tabBar.onmousedown = stopEvents;
    tabBar.onpointerdown = stopEvents;

    // Global Tab Button
    const globalBtn = document.createElement("button");
    globalBtn.type = "button";
    globalBtn.className = `fh-mc-tab-btn ${data.activeTab === "global" ? "is-active" : ""}`;
    const globalStatusText = data.enable_global ? "🌐 全局共享" : "🌐 全局 (已停用)";
    globalBtn.innerHTML = `<span>${globalStatusText}</span>`;
    globalBtn.onclick = (e) => {
        e.stopPropagation();
        data.activeTab = "global";
        syncData(node, data);
        buildUI(node, container);
    };
    tabBar.appendChild(globalBtn);

    // Clip Tab Buttons (Clip 1 is mandatory and non-deletable)
    data.clips.forEach((clip, idx) => {
        const clipBtn = document.createElement("button");
        clipBtn.type = "button";
        clipBtn.className = `fh-mc-tab-btn ${data.activeTab === clip.index ? "is-active" : ""}`;

        const titleSpan = document.createElement("span");
        titleSpan.className = "fh-mc-tab-btn-title";
        titleSpan.textContent = `🎬 ${clip.name}`;
        titleSpan.title = clip.name;
        clipBtn.appendChild(titleSpan);

        // Clip 1 is mandatory: only clips with index > 1 can be closed, provided total clips > 1
        if (clip.index !== 1 && data.clips.length > 1) {
            const closeBtn = document.createElement("span");
            closeBtn.className = "fh-mc-tab-close";
            closeBtn.textContent = "✕";
            closeBtn.title = `删除 ${clip.name}`;
            closeBtn.onclick = (e) => {
                e.stopPropagation();
                data.clips.splice(idx, 1);
                // Re-index remaining clips, ensuring first is 1
                data.clips.forEach((c, i) => {
                    c.index = i + 1;
                    if (c.name.startsWith("分镜 ")) c.name = `分镜 ${i + 1}`;
                });
                if (data.activeTab === clip.index) data.activeTab = 1;
                syncData(node, data);
                buildUI(node, container);
            };
            clipBtn.appendChild(closeBtn);
        }

        clipBtn.onclick = (e) => {
            e.stopPropagation();
            data.activeTab = clip.index;
            syncData(node, data);
            buildUI(node, container);
        };
        tabBar.appendChild(clipBtn);
    });

    // Add Clip Button
    const addBtn = document.createElement("button");
    addBtn.type = "button";
    addBtn.className = "fh-mc-tab-add";
    addBtn.textContent = "+ 新增分镜";
    addBtn.onclick = (e) => {
        e.stopPropagation();
        const nextIdx = data.clips.length + 1;
        data.clips.push({
            index: nextIdx,
            name: `分镜 ${nextIdx}`,
            prompt: "",
            override_steps: false,
            override_seed: false,
            seconds: 8.0,
            steps: 8,
            transition_step: 6,
            seed: 0,
            media: { images: [], videos: [], audios: [] }
        });
        data.activeTab = nextIdx;
        syncData(node, data);
        buildUI(node, container);
    };
    tabBar.appendChild(addBtn);
    container.appendChild(tabBar);

    // Tab Body
    const body = document.createElement("div");
    body.className = "fh-mc-section";

    const genMode = getGenerationMode(node);
    const isText = genMode === "text";
    const isImage = genMode === "image";
    const isReference = genMode === "reference";

    const enableGlobal = Boolean(data.enable_global);
    const gImgCount = (data.global_media?.images || []).length;
    const gVidCount = (data.global_media?.videos || []).length;
    const gAudCount = (data.global_media?.audios || []).length;

    const isRefConnected = isReference && refmodsInputIsConnected(node);
    if (isRefConnected) {
        void refreshRefmodCatalog();
    }
    const rawRefmods = isRefConnected ? refmodReferences(node) : [];
    const modVidCount = rawRefmods.filter(r => r.type === "video").length;
    const modImgCount = rawRefmods.filter(r => r.type === "image").length;
    const modAudCount = rawRefmods.filter(r => r.type === "audio").length;

    if (data.activeTab === "global") {
        // Global Content

        // 1. Global Switch Row
        const switchRow = document.createElement("div");
        switchRow.className = "fh-mc-switch-row";

        const labelWrap = document.createElement("div");
        labelWrap.className = "fh-mc-switch-label-wrap";

        const switchTitle = document.createElement("div");
        switchTitle.className = "fh-mc-switch-title";
        switchTitle.innerHTML = `
          <span>🌐 启用全局共享素材与提示词</span>
          <span class="fh-mc-badge-purple">${enableGlobal ? "已开启" : "已关闭"}</span>
        `;

        const switchDesc = document.createElement("div");
        switchDesc.className = "fh-mc-switch-desc";
        switchDesc.textContent = enableGlobal
            ? "开启：全局提示词作为前缀拼接到各分镜；全局素材全分镜共享并扣除各分镜配额。"
            : "关闭：各分镜完全独立运行，不继承全局提示词与素材，各分镜拥有独立满额素材配额（@图1~@图9）。";

        labelWrap.appendChild(switchTitle);
        labelWrap.appendChild(switchDesc);

        const switchLabel = document.createElement("label");
        switchLabel.className = "fh-mc-switch";

        const switchInput = document.createElement("input");
        switchInput.type = "checkbox";
        switchInput.checked = enableGlobal;
        switchInput.onchange = (e) => {
            e.stopPropagation();
            data.enable_global = switchInput.checked;
            syncData(node, data);
            buildUI(node, container);
        };

        const switchSlider = document.createElement("span");
        switchSlider.className = "fh-mc-switch-slider";

        switchLabel.appendChild(switchInput);
        switchLabel.appendChild(switchSlider);

        switchRow.appendChild(labelWrap);
        switchRow.appendChild(switchLabel);
        body.appendChild(switchRow);

        if (!enableGlobal) {
            const notice = document.createElement("div");
            notice.className = "fh-mc-disabled-notice";
            notice.textContent = "⚠️ 全局共享已关闭：当前分镜不会继承全局提示词与素材。请切换到具体分镜 Tab 进行独立提示词与素材设置。";
            body.appendChild(notice);
        }

        // 2. Global Prompt Row
        const labelRow = document.createElement("div");
        labelRow.className = "fh-mc-label-row";

        let badgeHtml = "";
        let showMentionBtn = true;
        if (isText) {
            badgeHtml = `<span class="fh-mc-badge-purple">📝 文生视频模式（无需素材，纯提示词驱动）</span>`;
            showMentionBtn = false;
        } else if (isImage) {
            badgeHtml = `<span class="fh-mc-badge-purple">🖼️ 首尾帧模式（限2张图片，首帧/尾帧）</span>`;
        } else {
            let quotaText = `配额: 图 ${gImgCount}/9 | 视 ${gVidCount}/3 | 音 ${gAudCount}/3`;
            if (modVidCount > 0 || modImgCount > 0 || modAudCount > 0) {
                const parts = [];
                parts.push(`图 ${gImgCount}${modImgCount > 0 ? `+${modImgCount}` : ""}/9`);
                parts.push(`视 ${gVidCount}${modVidCount > 0 ? `+${modVidCount}` : ""}/3`);
                parts.push(`音 ${gAudCount}${modAudCount > 0 ? `+${modAudCount}` : ""}/3`);
                quotaText = `配额: ${parts.join(" | ")} (含RefMod)`;
            }
            badgeHtml = enableGlobal
                ? `<span class="fh-mc-badge-purple">${quotaText}</span>`
                : `<span class="fh-mc-badge-purple">全局素材未启用</span>`;
        }

        labelRow.innerHTML = `
          <span>全局提示词${enableGlobal ? "（自动作为前缀拼接到各分镜）" : "（已停用）"}</span>
          <div style="display:flex;align-items:center;gap:6px;">
            ${(showMentionBtn && enableGlobal) ? '<button type="button" class="fh-mc-mention-btn" title="输入 @ 引用素材，或点击在此插入 @">@ 引用素材</button>' : ''}
            ${badgeHtml}
          </div>
        `;
        body.appendChild(labelRow);

        const promptInput = document.createElement("textarea");
        promptInput.className = "fh-mc-prompt-input";
        promptInput.rows = 6;
        if (!enableGlobal) {
            promptInput.disabled = true;
            promptInput.placeholder = "全局共享已关闭（分镜将不继承此全局提示词）";
        } else {
            promptInput.disabled = false;
            promptInput.placeholder = isText
                ? "输入全局共享提示词，例如：Masterpiece, cinematic lighting, photorealistic, 4k resolution..."
                : isImage
                ? "输入全局共享提示词，输入 @ 可快捷引用首尾帧素材，例如：@图1 电影感镜头，冷色调，4k高清画质..."
                : "输入全局共享提示词，输入 @ 可快捷引用素材，例如：@图1 电影感镜头，冷色调，4k高清画质...";
        }
        promptInput.value = data.global_prompt || "";
        promptInput.oninput = () => {
            data.global_prompt = promptInput.value;
            syncData(node, data);
        };
        if (!isText && enableGlobal) {
            attachMentionListeners(node, promptInput, true, null);
        }

        const mentionBtn = labelRow.querySelector(".fh-mc-mention-btn");
        if (mentionBtn && enableGlobal) {
            mentionBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                triggerMentionAtCaret(node, promptInput, true, null);
            };
        }
        body.appendChild(promptInput);

        // 3. Global Media Galleries
        if (isText) {
            // Text mode: hide all galleries
        } else if (isImage) {
            // Image mode: only 2 slots
            const imgLabels = [
                { badge: "@图1 (首帧)", hint: "+ 上传首帧" },
                { badge: "@图2 (尾帧)", hint: "+ 上传尾帧 (可选)" }
            ];
            renderGallerySection(
                node, container, body,
                enableGlobal ? "全局首/尾帧图片（全分镜可用）" : "全局首/尾帧图片（已停用）",
                "image", 2, 1, data.global_media?.images || [], (newList) => {
                    data.global_media.images = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, imgLabels, !enableGlobal, buildUI
            );
        } else {
            // Reference mode
            const maxGlobalImg = Math.max(0, 9 - modImgCount);
            const startGlobalImg = modImgCount + 1;
            const globalImgTitle = enableGlobal
                ? (modImgCount > 0
                    ? `全局图片素材（RefMod 已占用图1~${modImgCount}，普通图片顺延自 @图${startGlobalImg}）`
                    : "全局图片素材（全分镜可用）")
                : "全局图片素材（已停用）";

            renderGallerySection(
                node, container, body,
                globalImgTitle,
                "image", maxGlobalImg, startGlobalImg, data.global_media?.images || [], (newList) => {
                    data.global_media.images = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, null, !enableGlobal, buildUI
            );

            const maxGlobalVid = Math.max(0, 3 - modVidCount);
            const startGlobalVid = modVidCount + 1;
            const globalVidTitle = enableGlobal
                ? (modVidCount > 0
                    ? `全局视频素材（RefMod 已占用视频1~${modVidCount}，普通视频顺延自 @视频${startGlobalVid}）`
                    : "全局视频素材（若接入 RefMod 则占用视频1）")
                : "全局视频素材（已停用）";

            renderGallerySection(
                node, container, body,
                globalVidTitle,
                "video", maxGlobalVid, startGlobalVid, data.global_media?.videos || [], (newList) => {
                    data.global_media.videos = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, null, !enableGlobal, buildUI
            );

            const maxGlobalAud = Math.max(0, 3 - modAudCount);
            const startGlobalAud = modAudCount + 1;
            const globalAudTitle = enableGlobal
                ? (modAudCount > 0
                    ? `全局音频素材（RefMod 已占用音频1~${modAudCount}，普通音频顺延自 @音频${startGlobalAud}）`
                    : "全局音频素材（全分镜可用）")
                : "全局音频素材（已停用）";

            renderGallerySection(
                node, container, body,
                globalAudTitle,
                "audio", maxGlobalAud, startGlobalAud, data.global_media?.audios || [], (newList) => {
                    data.global_media.audios = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, null, !enableGlobal, buildUI
            );
        }
    } else {
        // Active Clip Content
        const curClip = data.clips.find(c => c.index === data.activeTab) || data.clips[0];
        const labelRow = document.createElement("div");
        labelRow.className = "fh-mc-label-row";

        let badgeHtml = "";
        let showMentionBtn = true;
        if (isText) {
            badgeHtml = `<span class="fh-mc-badge-purple">📝 文生视频分镜</span>`;
            showMentionBtn = false;
        } else if (isImage) {
            badgeHtml = `<span class="fh-mc-badge-purple">🖼️ 首尾帧分镜（覆盖全局首尾帧）</span>`;
        } else if (!enableGlobal) {
            badgeHtml = `<span class="fh-mc-badge-purple">⚡ 独立配额模式（图9/视3/音3）</span>`;
        } else {
            badgeHtml = `<span class="fh-mc-badge-purple">提示词中可使用 @图、@视频 引用</span>`;
        }

        labelRow.innerHTML = `
          <span>${curClip.name} 独立提示词</span>
          <div style="display:flex;align-items:center;gap:6px;">
            ${showMentionBtn ? '<button type="button" class="fh-mc-mention-btn" title="输入 @ 引用素材，或点击在此插入 @">@ 引用素材</button>' : ''}
            ${badgeHtml}
          </div>
        `;
        body.appendChild(labelRow);

        const promptInput = document.createElement("textarea");
        promptInput.className = "fh-mc-prompt-input";
        promptInput.rows = 6;
        promptInput.placeholder = isText
            ? `输入${curClip.name}的分镜提示词...`
            : isImage
            ? `输入${curClip.name}的分镜提示词，可输入 @ 引用首/尾帧，例如：@图1 少女推门...`
            : `输入${curClip.name}的分镜提示词，输入 @ 可快捷引用素材，例如：@图1 少女缓缓推开木门，回眸微笑...`;
        promptInput.value = curClip.prompt || "";
        promptInput.oninput = () => {
            curClip.prompt = promptInput.value;
            syncData(node, data);
        };
        if (!isText) {
            attachMentionListeners(node, promptInput, false, curClip.index);
        }

        const mentionBtn = labelRow.querySelector(".fh-mc-mention-btn");
        if (mentionBtn) {
            mentionBtn.onclick = (e) => {
                e.preventDefault();
                e.stopPropagation();
                triggerMentionAtCaret(node, promptInput, false, curClip.index);
            };
        }
        body.appendChild(promptInput);

        // Overrides box
        const overridesBox = document.createElement("div");
        overridesBox.className = "fh-mc-overrides-box";

        const stepRow = document.createElement("div");
        stepRow.className = "fh-mc-overrides-row";
        const stepChk = document.createElement("input");
        stepChk.type = "checkbox";
        stepChk.checked = !!curClip.override_steps;
        stepChk.id = `step_chk_${curClip.index}`;
        const stepLbl = document.createElement("label");
        stepLbl.htmlFor = `step_chk_${curClip.index}`;
        stepLbl.textContent = "覆盖该分镜时长与采样步数";

        stepChk.onchange = () => {
            curClip.override_steps = stepChk.checked;
            syncData(node, data);
            buildUI(node, container);
        };

        stepRow.appendChild(stepChk);
        stepRow.appendChild(stepLbl);

        if (curClip.override_steps) {
            const inputsWrap = document.createElement("span");
            inputsWrap.style.display = "inline-flex";
            inputsWrap.style.alignItems = "center";
            inputsWrap.style.gap = "4px";
            inputsWrap.style.marginLeft = "8px";

            const secLbl = document.createElement("span");
            secLbl.textContent = "时长:";
            const secIn = document.createElement("input");
            secIn.className = "fh-mc-input-num";
            secIn.type = "number";
            secIn.step = "0.5";
            secIn.min = "1";
            secIn.max = "12";
            secIn.value = curClip.seconds || 8.0;
            secIn.oninput = () => { curClip.seconds = parseFloat(secIn.value) || 8.0; syncData(node, data); };

            const secUnit = document.createElement("span");
            secUnit.textContent = "s";

            const stpLbl = document.createElement("span");
            stpLbl.textContent = "总步数:";
            const stpIn = document.createElement("input");
            stpIn.className = "fh-mc-input-num";
            stpIn.type = "number";
            stpIn.min = "1";
            stpIn.max = "100";
            stpIn.value = curClip.steps || 8;
            stpIn.oninput = () => { curClip.steps = parseInt(stpIn.value) || 8; syncData(node, data); };

            const trnLbl = document.createElement("span");
            trnLbl.textContent = "一采转折:";
            const trnIn = document.createElement("input");
            trnIn.className = "fh-mc-input-num";
            trnIn.type = "number";
            trnIn.min = "1";
            trnIn.max = "100";
            trnIn.value = curClip.transition_step || 6;
            trnIn.oninput = () => { curClip.transition_step = parseInt(trnIn.value) || 6; syncData(node, data); };

            inputsWrap.append(secLbl, secIn, secUnit, stpLbl, stpIn, trnLbl, trnIn);
            stepRow.appendChild(inputsWrap);
        }
        overridesBox.appendChild(stepRow);

        // Seed Override Row
        const seedRow = document.createElement("div");
        seedRow.className = "fh-mc-overrides-row";
        const seedChk = document.createElement("input");
        seedChk.type = "checkbox";
        seedChk.checked = !!curClip.override_seed;
        seedChk.id = `seed_chk_${curClip.index}`;
        const seedLbl = document.createElement("label");
        seedLbl.htmlFor = `seed_chk_${curClip.index}`;
        seedLbl.textContent = "独立控制随机种子 (Seed)";

        seedChk.onchange = () => {
            curClip.override_seed = seedChk.checked;
            syncData(node, data);
            buildUI(node, container);
        };

        seedRow.appendChild(seedChk);
        seedRow.appendChild(seedLbl);

        if (curClip.override_seed) {
            const seedWrap = document.createElement("span");
            seedWrap.style.display = "inline-flex";
            seedWrap.style.alignItems = "center";
            seedWrap.style.gap = "4px";
            seedWrap.style.marginLeft = "8px";

            const seedInLbl = document.createElement("span");
            seedInLbl.textContent = "Seed:";
            const seedIn = document.createElement("input");
            seedIn.className = "fh-mc-input-num";
            seedIn.style.width = "90px";
            seedIn.type = "number";
            seedIn.value = curClip.seed || 0;
            seedIn.oninput = () => { curClip.seed = parseInt(seedIn.value) || 0; syncData(node, data); };

            seedWrap.append(seedInLbl, seedIn);
            seedRow.appendChild(seedWrap);
        }
        overridesBox.appendChild(seedRow);

        body.appendChild(overridesBox);

        // Clip Media Gallery
        curClip.media = curClip.media || { images: [], videos: [], audios: [] };

        if (isText) {
            // Text mode: hide all material boxes
        } else if (isImage) {
            // Image mode: 2 slots
            const imgLabels = [
                { badge: "@图1 (首帧)", hint: "+ 上传该分镜首帧" },
                { badge: "@图2 (尾帧)", hint: "+ 上传该分镜尾帧 (可选)" }
            ];
            renderGallerySection(
                node, container, body,
                `${curClip.name} 独享首/尾帧图片`,
                "image", 2, 1, curClip.media.images || [],
                (newList) => {
                    curClip.media.images = newList;
                    syncData(node, data);
                    buildUI(node, container);
                },
                imgLabels, false, buildUI
            );
        } else {
            // Reference mode
            const remImgCap = enableGlobal ? Math.max(0, 9 - modImgCount - gImgCount) : Math.max(0, 9 - modImgCount);
            const startImg = enableGlobal ? (modImgCount + gImgCount + 1) : (modImgCount + 1);
            const remVidCap = enableGlobal ? Math.max(0, 3 - modVidCount - gVidCount) : Math.max(0, 3 - modVidCount);
            const startVid = enableGlobal ? (modVidCount + gVidCount + 1) : (modVidCount + 1);
            const remAudCap = enableGlobal ? Math.max(0, 3 - modAudCount - gAudCount) : Math.max(0, 3 - modAudCount);
            const startAud = enableGlobal ? (modAudCount + gAudCount + 1) : (modAudCount + 1);

            const imgTitle = enableGlobal
                ? `分镜独享图片（剩余配额: ${remImgCap}，顺延标号: @图${startImg}~@图9）`
                : `${curClip.name} 独享图片（独立配额: ${remImgCap}，标号: @图${startImg}~@图9）`;
            renderGallerySection(
                node, container, body,
                imgTitle,
                "image", remImgCap, startImg, curClip.media.images || [],
                (newList) => {
                    curClip.media.images = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, null, false, buildUI
            );

            const vidTitle = enableGlobal
                ? `分镜独享视频（剩余配额: ${remVidCap}，顺延标号: @视频${startVid}~@视频3）`
                : `${curClip.name} 独享视频（独立配额: ${remVidCap}，标号: @视频${startVid}~@视频3）`;
            renderGallerySection(
                node, container, body,
                vidTitle,
                "video", remVidCap, startVid, curClip.media.videos || [],
                (newList) => {
                    curClip.media.videos = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, null, false, buildUI
            );

            const audTitle = enableGlobal
                ? `分镜独享音频（剩余配额: ${remAudCap}，顺延标号: @音频${startAud}~@音频3）`
                : `${curClip.name} 独享音频（独立配额: ${remAudCap}，标号: @音频${startAud}~@音频3）`;
            renderGallerySection(
                node, container, body,
                audTitle,
                "audio", remAudCap, startAud, curClip.media.audios || [],
                (newList) => {
                    curClip.media.audios = newList;
                    syncData(node, data);
                    buildUI(node, container);
                }, null, false, buildUI
            );
        }
    }

    container.appendChild(body);
}
