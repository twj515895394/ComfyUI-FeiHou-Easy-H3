/**
 * Data model, normalization, and synchronization for FeiHou Easy H3 Multi-Clip.
 */

import { api } from "../../../scripts/api.js";

export const PROP_KEY = "feihou_multi_clip_data";

export function getDefaultData() {
    return {
        activeTab: "global",
        enable_global: true,
        global_prompt: "",
        global_media: { images: [], videos: [], audios: [] },
        clips: [
            {
                index: 1,
                name: "分镜 1",
                prompt: "",
                override_steps: false,
                override_seed: false,
                seconds: 8.0,
                steps: 8,
                transition_step: 6,
                seed: 0,
                media: { images: [], videos: [], audios: [] }
            }
        ]
    };
}

export function normalizeData(data) {
    const defaults = getDefaultData();
    if (!data || typeof data !== "object") return defaults;
    const res = Object.assign({}, defaults, data);

    res.enable_global = typeof res.enable_global === "boolean" ? res.enable_global : true;
    res.global_prompt = typeof res.global_prompt === "string" ? res.global_prompt : "";

    if (!res.global_media || typeof res.global_media !== "object") {
        res.global_media = { images: [], videos: [], audios: [] };
    } else {
        res.global_media.images = Array.isArray(res.global_media.images) ? res.global_media.images : [];
        res.global_media.videos = Array.isArray(res.global_media.videos) ? res.global_media.videos : [];
        res.global_media.audios = Array.isArray(res.global_media.audios) ? res.global_media.audios : [];
    }

    if (!Array.isArray(res.clips) || res.clips.length === 0) {
        res.clips = defaults.clips;
    } else {
        res.clips = res.clips.map((clip, i) => {
            const defClip = {
                index: i + 1,
                name: `分镜 ${i + 1}`,
                prompt: "",
                override_steps: false,
                override_seed: false,
                seconds: 8.0,
                steps: 8,
                transition_step: 6,
                seed: 0,
                media: { images: [], videos: [], audios: [] }
            };
            const c = Object.assign({}, defClip, clip || {});
            c.index = (i === 0) ? 1 : (c.index || (i + 1));
            c.name = c.name || `分镜 ${c.index}`;
            c.prompt = typeof c.prompt === "string" ? c.prompt : "";
            c.media = c.media && typeof c.media === "object" ? c.media : { images: [], videos: [], audios: [] };
            c.media.images = Array.isArray(c.media.images) ? c.media.images : [];
            c.media.videos = Array.isArray(c.media.videos) ? c.media.videos : [];
            c.media.audios = Array.isArray(c.media.audios) ? c.media.audios : [];
            return c;
        });
    }

    if (res.activeTab === undefined || (res.activeTab !== "global" && !res.clips.some(c => c.index === res.activeTab))) {
        res.activeTab = "global";
    }

    return res;
}

export function getData(node) {
    if (!node) return getDefaultData();
    node.properties = node.properties || {};
    let raw = node.properties[PROP_KEY];
    if (!raw) {
        const widget = node.widgets?.find(w => w.name === "multi_clip_data");
        if (widget && widget.value) {
            raw = widget.value;
        }
    }
    let data;
    if (!raw) {
        data = getDefaultData();
    } else {
        try {
            const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
            data = normalizeData(parsed);
        } catch {
            data = getDefaultData();
        }
    }
    if (!data.global_prompt) {
        const gpWidget = node.widgets?.find(w => w.name === "global_prompt");
        if (gpWidget && gpWidget.value) {
            data.global_prompt = gpWidget.value;
        }
    }
    return data;
}

export function syncData(node, data) {
    node.properties = node.properties || {};
    node.properties[PROP_KEY] = JSON.stringify(data);
    const widget = node.widgets?.find(w => w.name === "multi_clip_data");
    if (widget) {
        widget.value = JSON.stringify(data);
    }
    const globalPromptWidget = node.widgets?.find(w => w.name === "global_prompt");
    if (globalPromptWidget && data.global_prompt !== undefined) {
        globalPromptWidget.value = data.global_prompt;
    }
    node.setDirtyCanvas?.(true, true);
}

export async function uploadFile(file, type) {
    const body = new FormData();
    body.append("image", file, file.name || `media_${type}`);
    body.append("type", "input");
    const response = await api.fetchApi("/upload/image", { method: "POST", body });
    if (!response.ok) throw new Error(`Upload failed (${response.status})`);
    const uploaded = await response.json();
    return uploaded.subfolder ? `${uploaded.subfolder}/${uploaded.name}` : uploaded.name;
}
