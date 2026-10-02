"use strict";

const filterIntent = (() => {
 const units = {YIELD_VS_CHECK_PCT:"%", DISEASE_SCORE_MEAN:"score", MOISTURE_PCT_MEAN:"%",
  GERMINATION_PCT:"%", FUMONISIN_PPM:"ppm", N_TRIALS_USED:"trials", GENOMIC_BREEDING_VALUE:"index", COLD_TEST_PCT:"%"};
 const names = {search:"Candidate ID", rag:"System RAG", decision:"Existing breeder choice", marker:"Disease marker", excluded:"Excluded trials"};
 let current = null, draft = null, generation = 0;
 const status = message => { $("filter-intent-status").textContent = message; };
 function invalidate(message = "") {
  ++generation; draft = null; $("filter-preview").hidden = true;
  $("filter-interpret").disabled = false; $("filter-apply").disabled = false;
  status(message);
 }
 function context(data) {
  const next = {snapshot_id:data.snapshot_id, revision_id:data.revision_id};
  if(current && JSON.stringify(current) !== JSON.stringify(next))invalidate("Evidence changed. Interpret again before applying filters.");
  current = next;
 }
 function render(filters) {
  const host = $("filter-preview-fields"); host.replaceChildren();
  const grid = element("div", "", host, "filter-grid");
  for(const [id, label] of Object.entries(names)) {
   const wrap = element("label", label, grid), input = $(id).cloneNode(true);
   input.id = `proposal-${id}`; input.removeAttribute("aria-describedby");
   input.value = id === "excluded" ? (filters[id] === null ? "" : String(filters[id])) : filters[id];
   wrap.appendChild(input);
  }
  const missing = element("label", "Include missing values ", host);
  const checkbox = element("input", "", missing); checkbox.type = "checkbox"; checkbox.id = "proposal-include-missing"; checkbox.checked = filters.include_missing;
  element("p", "Ranges are inclusive and combined with AND. Leave both limits blank to remove a range.", host, "small");
  const activeRanges = element("div", "", host);
  const otherRanges = element("details", "", host);
  element("summary", "Other trait ranges (unrestricted unless entered)", otherRanges);
  for(const [metric, unit] of Object.entries(units)) {
   const row = element("div", "", filters.ranges[metric] ? activeRanges : otherRanges, "filter-grid");
   element("span", labels[metric], row);
   for(const bound of ["min", "max"]) {
    const wrap = element("label", `${bound === "min" ? "Minimum (≥)" : "Maximum (≤)"} · ${unit}`, row);
    const input = element("input", "", wrap); input.type = "number"; input.step = metric === "N_TRIALS_USED" ? "1" : "any";
    if(metric === "N_TRIALS_USED")input.min = "0";
    input.id = `proposal-${metric}-${bound}`; input.value = filters.ranges[metric]?.[bound] ?? "";
    input.setAttribute("aria-label", `${labels[metric]} ${bound === "min" ? "minimum" : "maximum"}`);
   }
  }
  $("filter-preview").hidden = false;
 }
 function read() {
  const filters = Object.fromEntries(Object.keys(names).map(id => [id, $(`proposal-${id}`).value]));
  filters.excluded = filters.excluded === "" ? null : filters.excluded === "true";
  filters.include_missing = $("proposal-include-missing").checked; filters.ranges = {};
  for(const [metric, unit] of Object.entries(units)) {
   const bounds = {unit};
   for(const bound of ["min", "max"]) {
    const input = $(`proposal-${metric}-${bound}`);
    if(input.value !== "")bounds[bound] = Number(input.value);
   }
   if(Object.keys(bounds).length > 1)filters.ranges[metric] = bounds;
  }
  return filters;
 }
 $("filter-request").addEventListener("input", () => invalidate());
 $("filter-cancel").onclick = () => { invalidate("Filter preview cancelled."); $("filter-request").focus(); };
 $("filter-preview").addEventListener("input", () => { ++generation; $("filter-apply").disabled = false; status("Preview edited. Apply filters to confirm."); });
 $("filter-request-form").onsubmit = async event => {
  event.preventDefault(); invalidate();
  if(!current) { status("Wait for the candidate list to load, then retry."); return; }
  const attempt = generation;
  $("filter-interpret").disabled = true; status("Interpreting your filter request…");
  try {
   const result = await post("/filters/interpret", {...current, text:$("filter-request").value});
   if(attempt !== generation)return;
   if(result.status !== "ready") { status(result.clarification); return; }
   draft = {snapshot_id:result.snapshot_id, revision_id:result.revision_id};
   render(result.filters); status("Review and edit the proposed filters. The current list has not changed.");
  } catch(error) { if(attempt === generation)status(error.message + " Manual filters remain available."); }
  finally { if(attempt === generation)$("filter-interpret").disabled = false; }
 };
 $("filter-preview").onsubmit = async event => {
  event.preventDefault(); if(!draft)return;
  const attempt = ++generation;
  $("filter-apply").disabled = true; status("Validating the edited filters…");
  try {
   const result = await post("/filters/validate", {...draft, filters:read()});
   if(attempt !== generation)return;
   const filters = result.filters;
   clearTimeout(state.timer); ++state.listRequest;
   for(const id of Object.keys(names))$(id).value = id === "excluded" ? (filters[id] === null ? "" : String(filters[id])) : filters[id];
   $("review_state").value = "all";
   $("include-missing").checked = filters.include_missing;
   boundaryControls.clear();
   state.ranges = Object.fromEntries(Object.entries(filters.ranges).map(([metric, bounds]) =>
    [metric, Object.fromEntries(["min", "max"].filter(k => bounds[k] !== null).map(k => [k, bounds[k]]))]));
   preferences.changed(); ranges(); await loadList();
   // A newer request or manual edit owns its own status message.
   if(generation === attempt + 1)status("Filters applied. " + result.total + " matching candidates at validation.");
  } catch(error) { if(attempt === generation)status(error.message); }
  finally { if(attempt === generation)$("filter-apply").disabled = false; }
 };
 return {context, invalidate};
})();
