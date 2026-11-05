/**
 * RefMod connection detection, catalog caching, and reference resolution
 * for FeiHou Easy H3 Multi-Clip.
 */

import { api } from "../../../scripts/api.js";
import { app } from "../../../scripts/app.js";

let refmodCatalog = new Map();
let refmodCatalogRequest = null;
let refmodCatalogUpdatedAt = 0;

export function refmodsInputIsConnected(node) {
    return Boolean((node?.inputs || []).some((input) => input.name === "refmods" && input.link != null));
}

export function getNativeGraphLink(graph, linkId) {
    if (!graph || linkId == null) return null;
    for (const links of [graph.links, graph._links]) {
        if (!links) continue;
        if (typeof links.get === "function") {
            const link = links.get(linkId) ?? links.get(String(linkId));
            if (link) return link;
        }
        const link = links[linkId] ?? links[String(linkId)];
        if (link) return link;
    }
    return null;
}

export function getWidgetValue(node, name, fallback = "") {
    const widget = node?.widgets?.find((w) => w?.name === name);
    return widget?.value ?? fallback;
}

export async function refreshRefmodCatalog(force = false) {
    if (refmodCatalogRequest) return refmodCatalogRequest;
    if (!force && Date.now() - refmodCatalogUpdatedAt < 5000) return refmodCatalog;
    refmodCatalogUpdatedAt = Date.now();
    refmodCatalogRequest = (async () => {
        try {
            const response = await api.fetchApi("/feihou_easy_h3/refmods");
            if (!response.ok) throw new Error(`RefMod metadata: ${response.status}`);
            const data = await response.json();
            const next = new Map((data.references || []).map(entry => [entry.name, entry.members]));
            refmodCatalog = next;
            return refmodCatalog;
        } catch (error) {
            console.warn("Easy H3 MultiClip: could not refresh RefMod references", error);
            return refmodCatalog;
        } finally {
            refmodCatalogRequest = null;
        }
    })();
    return refmodCatalogRequest;
}

export function getRefmodCatalog() {
    return refmodCatalog;
}

export function refmodSourceNode(node, depth = 0) {
    if (!node || depth > 16 || node.mode === 2 || node.mode === 4) return null;
    const type = String(node.comfyClass || node.type || "");
    if (["MiniMaxH3RefModsLoader", "MiniMaxH3RefModsAxis"].includes(type)) return node;
    const graph = node.graph || app?.graph || window.app?.graph;
    if (type === "GetNode") {
        const setter = (graph?._nodes || []).find(item => item.type === "SetNode" && item.widgets?.[0]?.value === node.widgets?.[0]?.value);
        return refmodSourceNode(setter, depth + 1);
    }
    const input = (node.inputs || []).find(item => item.name === "refmods")
        || (["Reroute", "SetNode", "MiniMaxH3RefModSave", "MiniMaxH3RefModBundleSave"].includes(type) ? node.inputs?.[0] : null);
    if (input?.link == null) return null;
    const link = getNativeGraphLink(graph, input.link);
    const originId = link?.origin_id ?? link?.originId ?? link?.from_id ?? link?.fromId;
    return refmodSourceNode(graph?.getNodeById?.(originId), depth + 1);
}

export function refmodReferences(node) {
    const source = refmodSourceNode(node);
    if (!source) return [];
    const axis = String(source.comfyClass || source.type) === "MiniMaxH3RefModsAxis";
    const refs = [];
    for (let slot = 1; slot <= 8; slot++) {
        const value = Number(getWidgetValue(source, axis ? `value_${slot}` : `strength_${slot}`, axis ? 0 : 1));
        if (!Number.isFinite(value) || (axis ? Math.abs(value) < 1e-6 : value <= 0)) continue;
        const name = String(getWidgetValue(source, axis ? `mod_${value > 0 ? "b" : "a"}_${slot}` : `mod_${slot}`, "(none)"));
        if (!name || name === "(none)") continue;

        const selection = String(getWidgetValue(source, `components_${slot}`, "All"));
        let members = refmodCatalog.get(name);
        if (!members || members.length === 0) {
            // Fallback before catalog is fetched or for single item: default to video kind
            members = [{ index: 0, name: name, kind: "video" }];
        }

        const copies = axis ? 1 : Number(getWidgetValue(source, `copies_${slot}`, 1));
        for (const member of members) {
            const kind = member.kind || "video";
            const component = kind === "audio" ? "Audio" : "Visual";
            if (selection !== "All" && selection !== component) continue;
            const compStrength = Number(getWidgetValue(source, `${component.toLowerCase()}_strength_${slot}`, 1));
            if (Number.isFinite(compStrength) && compStrength <= 0) continue;

            for (let copy = 0; copy < copies; copy++) {
                refs.push({
                    type: kind,
                    name: member.name || name,
                    modName: name,
                    fullLabel: `${member.name || name} · RefMod`,
                    source: `RefMod · ${name}`,
                    sourceId: source.id,
                    sourceSlot: slot,
                    refmodKey: `${source.id}:${slot}:${name}:${member.index ?? 0}:${copy}`,
                    previewUrl: "",
                });
            }
        }
    }
    return refs;
}
