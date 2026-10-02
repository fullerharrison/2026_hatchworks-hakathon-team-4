"use strict";

// Browser conveniences only. Never serialize decision drafts or evidence here.
const preferences = (() => {
 const key = "uc4.preferences";
 const fields = ["search", "rag", "decision", "marker", "excluded", "sort"];
 const checks = ["descending", "include-missing"];
 const initial = () => ({version:1, defaults:null, rememberView:false, view:null});
 let saved = initial(), snapshot = null, generation = 0, ready = false;
 const notice = text => { $("preferences-status").textContent = text; };
 const object = value => value !== null && typeof value === "object" && !Array.isArray(value);
 const options = id => Array.from($(id).options, option => option.value);
 function validView(view) {
  if(!object(view) || typeof view.snapshot !== "string" || !view.snapshot ||
     !(view.selected === null || typeof view.selected === "string" && view.selected.length > 0) ||
     !object(view.filters) || !object(view.ranges)) return false;
  for(const id of fields) {
   if(typeof view.filters[id] !== "string") return false;
   if(id !== "search" && !options(id).includes(view.filters[id])) return false;
  }
  if(checks.some(id => typeof view.filters[id] !== "boolean")) return false;
  for(const [metric, bounds] of Object.entries(view.ranges)) {
   if(!options("metric").includes(metric) || !object(bounds) || !Object.keys(bounds).length ||
      Object.keys(bounds).some(k => !["min", "max"].includes(k)) ||
      Object.values(bounds).some(v => typeof v !== "number" || !Number.isFinite(v)) ||
      (bounds.min !== undefined && bounds.max !== undefined && bounds.min > bounds.max)) return false;
  }
  return true;
 }
 function read() {
  try {
   const raw = localStorage.getItem(key);
   if(!raw) return initial();
   const value = JSON.parse(raw), d = value?.defaults;
   if(!object(value) || value.version !== 1 || typeof value.rememberView !== "boolean" ||
      !(d === null || object(d) && typeof d.name === "string" && d.name.length <= 80 &&
        typeof d.location === "string" && d.location.trim() &&
        typeof d.sourceChannel === "string" && d.sourceChannel.trim()) ||
      !(value.view === null || validView(value.view))) throw new Error("invalid");
   // Allowlist the record rather than copying unrelated stored fields forward.
   const view = value.rememberView && value.view ? {
    snapshot:value.view.snapshot, selected:value.view.selected,
    filters:Object.fromEntries([...fields, ...checks].map(id => [id, value.view.filters[id]])),
    ranges:value.view.ranges
   } : null;
   return {version:1, defaults:d === null ? null : {name:d.name, location:d.location, sourceChannel:d.sourceChannel},
    rememberView:value.rememberView, view};
  } catch(error) {
   notice(error instanceof SyntaxError || error.message === "invalid"
    ? "Saved preferences could not be restored. Reset to initial defaults; save again to replace them."
    : "Browser storage is unavailable. Preferences cannot be restored or saved.");
   return initial();
  }
 }
 function write(next) {
  try { localStorage.setItem(key, JSON.stringify(next)); saved = next; return true; }
  catch { notice("Preferences could not be saved. Browser storage is unavailable or full; this view is temporary."); return false; }
 }
 function defaultsToForm(includeName = true) {
  if(includeName || saved.defaults) $("actor").value = saved.defaults?.name || "";
  $("location").value = saved.defaults?.location || "Unknown";
  $("source-channel").value = saved.defaults?.sourceChannel || "Breeder review";
  contextSummary();
 }
 function editor() {
  $("preference-name").value = saved.defaults?.name || "";
  $("preference-location").value = saved.defaults?.location || "Unknown";
  $("preference-channel").value = saved.defaults?.sourceChannel || "Breeder review";
  $("remember-view").checked = saved.rememberView;
 }
 function capture() {
  const filters = Object.fromEntries(fields.map(id => [id, $(id).value]));
  for(const id of checks) filters[id] = $(id).checked;
  return {snapshot, filters, ranges:structuredClone(state.ranges), selected:state.selected};
 }
 function remember() {
  if(!ready || !snapshot || !saved.rememberView) return;
  const view = capture();
  if(validView(view)) write({...saved, view});
 }
 function changed() {
  filterIntent.invalidate();
  ++generation;
  remember();
 }
 function clearSelection() {
  ++state.detailRequest;
  state.selected = null; state.detail = null; state.loadingDetail = false;
  $("detail").hidden = true;
  $("selection-status").textContent = "";
  resetDecisionDraft();
  $("decision-identity").textContent = "";
  $("enrichment-form").reset();
  $("enrichment-message").textContent = "";
  updateAskContext();
 }
 function clearView() {
  filterIntent.invalidate();
  ++generation;
  clearTimeout(state.timer);
  ++state.listRequest;
  for(const id of fields) $(id).value = id === "sort" ? "material_id" : "";
  for(const id of checks) $(id).checked = false;
  $("metric").selectedIndex = 0;
  $("min").value = ""; $("max").value = "";
  state.ranges = {}; ranges();
  clearSelection();
 }
 function reset() {
  clearView(); defaultsToForm();
  if(saved.rememberView) write({...saved, view:null});
  remember(); loadList();
 }
 function checkSnapshot(current) {
  if(snapshot && current !== snapshot) {
   snapshot = current; clearView(); remember();
   notice("Source dataset changed. Filters and selection were reset; saved name and review context were retained.");
   return false;
  }
  snapshot = current;
  return true;
 }
 function selectionStatus(rows) {
  $("selection-status").textContent = state.selected && !rows.some(r => r.material_guid === state.selected)
   ? "Selected candidate is outside current filters." : "";
 }
 async function start() {
  saved = read(); editor(); defaultsToForm();
  // Old session opt-in never becomes permission for durable storage.
  if(!saved.defaults) { try { $("actor").value = sessionStorage.getItem("uc4.alias") || ""; } catch {} }
  $("preferences-form").addEventListener("input", () => notice("Unsaved preference edits. Select Save preferences to update your defaults."));
  $("preferences-form").onsubmit = event => {
   event.preventDefault();
   const defaults = {name:$("preference-name").value.trim(), location:$("preference-location").value.trim(),
    sourceChannel:$("preference-channel").value.trim()};
   if(!defaults.location || !defaults.sourceChannel) { notice("Enter a location or Unknown, and a source channel."); return; }
   if(write({...saved, defaults})) {
    defaultsToForm(); notice("Name and review context saved in this browser.");
    try { sessionStorage.removeItem("uc4.alias"); } catch {}
   }
  };
  $("remember-view").onchange = () => {
   ++generation;
   const enabled = $("remember-view").checked;
   if(write({...saved, rememberView:enabled, view:enabled && snapshot ? capture() : null}))
    notice(enabled ? "Filters and selected candidate will be remembered in this browser." : "Saved filters and selection removed. Name and review context retained.");
   else $("remember-view").checked = saved.rememberView;
  };
  $("forget-preferences").onclick = () => {
   let removed = true;
   try { localStorage.removeItem(key); } catch { removed = false; }
   try { sessionStorage.removeItem("uc4.alias"); } catch { removed = false; }
   saved = initial(); editor(); defaultsToForm(); reset();
   notice(removed ? "Preferences forgotten. Remembering is off. Recorded history is unchanged."
    : "Remembering is off for this page, but browser storage could not be cleared. Clear this site's browser data to finish forgetting preferences.");
  };
  $("reset").onclick = reset;
  // Other open tabs must not recreate forgotten preferences.
  window.addEventListener("storage", event => {
   if(event.key !== key && event.key !== null) return;
   const previousDefaults = JSON.stringify(saved.defaults);
   saved = read();
   $("remember-view").checked = saved.rememberView;
   if(previousDefaults !== JSON.stringify(saved.defaults)) { editor(); defaultsToForm(); }
   if(event.newValue === null) {
    try { sessionStorage.removeItem("uc4.alias"); } catch {}
    editor(); defaultsToForm(); clearView(); loadList(); notice("Preferences were forgotten in another tab.");
   }
  });
  const attempt = generation;
  try {
   const data = await call("/candidates?limit=1");
   snapshot = data.snapshot_id;
   if(attempt === generation && saved.rememberView && saved.view) {
    const view = saved.view;
    if(view.snapshot !== snapshot) {
     write({...saved, view:null});
     notice("Source dataset changed. Filters and selection were reset; saved name and review context were retained.");
    } else {
     for(const id of fields) $(id).value = view.filters[id];
     for(const id of checks) $(id).checked = view.filters[id];
     state.ranges = structuredClone(view.ranges); ranges();
     ready = true;
     if(view.selected) await loadDetail(view.selected);
     if(attempt !== generation) return;
    }
   }
  } catch { notice("Saved view could not be restored. Retry by reloading when the server is available."); }
  finally { ready = true; }
  await loadList();
 }
 return {start, remember, changed, defaultsToForm, reset, checkSnapshot, selectionStatus, notice, clearSelection};
})();

loadRules();
preferences.start();
