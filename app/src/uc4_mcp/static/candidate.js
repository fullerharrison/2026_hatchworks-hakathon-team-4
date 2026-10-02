"use strict";
const $ = id => document.getElementById(id);
const state = {ranges:{}, selected:null, detail:null, timer:null, listRequest:0, detailRequest:0, decisionRequest:null};
const labels = {YIELD_VS_CHECK_PCT:"Yield vs checks (%)", DISEASE_SCORE_MEAN:"Disease score",
 MOISTURE_PCT_MEAN:"Moisture (%)", GERMINATION_PCT:"Germination (%)", FUMONISIN_PPM:"Fumonisin (ppm)",
 N_TRIALS_USED:"Usable trials", N_TRIALS:"Total trials", MARKER_DISEASE_RESISTANCE:"Disease resistance marker",
 GENOMIC_BREEDING_VALUE:"Genomic breeding value", COLD_TEST_PCT:"Cold test (%)",
 PEDIGREE:"Pedigree", STAGE_CODE_LID:"Breeding stage", RESEARCH_STATION_GUID:"Research station", SITE:"Site", NOTE:"Note"};
function show(v) { return v === null || v === undefined || v === "" ? "unknown" :
 typeof v==="number"?v.toLocaleString(undefined,{minimumFractionDigits:Number.isInteger(v)?0:2,maximumFractionDigits:2}):String(v); }
function element(tag, text, parent, cls) { const x=document.createElement(tag);x.textContent=text;if(cls)x.className=cls;parent.appendChild(x);return x; }
function clear(id) { $(id).replaceChildren(); }
async function call(path, options={}) {
 const response=await fetch(path,options);let data;
 const text=await response.text();try{data=JSON.parse(text);}catch{throw new Error(`Request failed (${response.status}). Please try again.`);}
 if(!response.ok){const error=new Error(readableError(data.detail||data));error.status=response.status;throw error;}
 return data;
}
const post=(path,body)=>call(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
function query() {
 const p=new URLSearchParams();
 for(const id of ["search","rag","decision","marker","excluded","sort"])if($(id).value)p.set(id,$(id).value);
 if($("descending").checked)p.set("descending","true");
 if($("include-missing").checked)p.set("include_missing","true");
 if(Object.keys(state.ranges).length)p.set("ranges",JSON.stringify(state.ranges));
 return p.toString();
}
function ranges() {
 clear("ranges");for(const [metric,bounds] of Object.entries(state.ranges)) {
  const span=element("span",`${labels[metric]||metric}: ${bounds.min??"−∞"} to ${bounds.max??"∞"} `,$("ranges"),"tag");
  const b=element("button","Remove",span);b.type="button";b.onclick=()=>{delete state.ranges[metric];preferences.changed();ranges();loadList();};
 }
}
async function loadList() {
 preferences.remember();
 const request=++state.listRequest;
 if(typeof renderFilters==="function")renderFilters();
 $("list-error").textContent="";
 const q=query();$("export").href="/candidates.csv"+(q?"?"+q:"");
 try {
  const data=await call("/candidates"+(q?"?"+q:""));
  let next=data.next_offset;
  while(next!==null){const page=await call("/candidates?"+(q?q+"&":"")+"offset="+next);
   if(page.revision_id!==data.revision_id)throw new Error("Evidence changed while loading; refresh the list.");
   data.rows.push(...page.rows);next=page.next_offset;}
  if(request!==state.listRequest)return;
  if(typeof filterIntent!=="undefined")filterIntent.context(data);
  enrichmentRevision(data.revision_id);
  if(!preferences.checkSnapshot(data.snapshot_id)){loadList();return;}
  preferences.selectionStatus(data.rows);
  $("count").textContent=`Candidates: ${data.total} matching of ${data.total_available}`;
  $("revision").textContent=`Evidence revision ${data.revision_id} · source ${data.snapshot_id.slice(0,12)}`;
  clear("rows");for(const r of data.rows) {
   const tr=document.createElement("tr");tr.tabIndex=0;if(r.material_guid===state.selected)tr.className="selected";
   for(const value of [r.material_id,r.rag,formatMetric("YIELD_VS_CHECK_PCT",r.metrics.YIELD_VS_CHECK_PCT),formatMetric("DISEASE_SCORE_MEAN",r.metrics.DISEASE_SCORE_MEAN),
    r.metrics.N_TRIALS_USED,r.excluded_trials,r.latest_decision?.action])element("td",show(value),tr).title=String(value??"unknown");
   tr.onclick=()=>loadDetail(r.material_id,{navigate:true});tr.onkeydown=e=>{if(e.key==="Enter")loadDetail(r.material_id,{navigate:true});};$("rows").appendChild(tr);
  }
 } catch(e) {if(request===state.listRequest)$("list-error").textContent=e.message;}
}
async function loadDetail(query, {navigate=false}={}) {
 state.detailTarget=query;
 const request=++state.detailRequest;
 enrichmentInvalidate();
 state.loadingDetail=true;$("record-decision").disabled=true;
 document.querySelectorAll('[role="tab"]').forEach(tab=>tab.disabled=true);
 invalidateDecisionReview();
 const previous=state.detail;
 try {
  const r=await call("/candidates/"+encodeURIComponent(query));if(request!==state.detailRequest)return;
  if(!previous || previous.material_guid!==r.material_guid)resetDecisionDraft();
  if(!preferences.checkSnapshot(r.snapshot_id)){loadList();return;}
  state.detail=r;state.selected=r.material_guid;state.loadingDetail=false;$("record-decision").disabled=!!state.savingDecision;
  document.querySelectorAll('[role="tab"]').forEach(tab=>tab.disabled=false);
  $("decision-identity").textContent=`Decision for ${r.material_id} / ${r.revision_id}`;
  updateAskContext();
  $("detail").hidden=false;$("candidate-status").textContent=`System recommendation: ${r.rag}`;$("detail-title").textContent=`${r.material_id} · candidate evidence`;
  const b=$("recommendation");b.className="banner "+r.rag.toLowerCase();b.replaceChildren();
  element("p",`${r.rag} · ${r.reason}`,b,"verdict");
  element("p",`Supplied: ${r.supplied_rag} · ${r.supplied_reason}`,b);
  element("p",`Provisional rule ${r.rule_version} · ${r.revision_id}`,b,"small");
  $("source-note").textContent=r.metadata_note;
  clear("criteria");for(const c of r.assessments){const tr=document.createElement("tr");
   for(const x of [labels[c.field]||c.field,`${formatMetric(c.field,c.value)} ${c.unit}`,`${c.test} ${formatMetric(c.field,c.threshold)}`,marginDescription(c),c.status])element("td",x,tr).title=String(c.value??"unknown");
   uiButton(tr.lastChild,"View evidence",()=>openCriterionEvidence(r,c));
   addHelp(tr.firstChild,glossary[c.field]);$("criteria").appendChild(tr);}
  clear("metrics");for(const [k,v] of Object.entries(r.metrics))if(!r.criteria.some(c=>c.field===k))addHelp(element("p",`${labels[k]||k}: ${formatMetric(k,v)}${r.policy.context_only.includes(k)?" - Context only under this policy":""}`,$("metrics")),glossary[k]);
  for(const [field,item] of Object.entries(r.reviewed_metadata))element("p",`${labels[field]||field}: ${item.value} (reviewed enrichment)`,$("metrics"));
  const summary=$("evidence-summary");summary.replaceChildren();
  element("p",`Trial evidence: ${r.metrics.N_TRIALS_USED} used / ${r.metrics.N_TRIALS} total / ${r.excluded_trials} excluded`,summary);
  for(const warning of r.warnings)element("p",warning.replace(/\d+\.\d+/g,x=>Number(x).toFixed(2)),summary,"warn");
  element("p","Missing trial geography limits regional interpretation. Material-level lab results have no trial key and cannot be assigned to a trial. Unknown pedigree and stage limit lineage and advancement-stage interpretation.",summary,"small");
  for(const warning of r.source_warnings)element("p",`Revision-wide source check: ${warning.check} (${warning.violations} records)`,summary,"warn");
  for(const [k,v] of Object.entries(r.evidence))element("p",`${readableLabel(k)}: ${v.length} source rows`,summary);
  uiButton(summary,"Compare trials",()=>openReader(`${r.material_id} - trial comparisons`,host=>renderData(host,r.trial_comparisons)));
  $("open-evidence").onclick=()=>openReader(`${r.material_id} - source evidence`,host=>renderCandidateEvidence(host,r));
  renderDecisions(r);renderDecisionState();enrichmentDetail(r, previous);renderEnrichment(r);
  if(navigate||!previous||previous.material_guid!==r.material_guid){selectCandidateTab("evidence");if(navigate)$("detail-title").focus({preventScroll:true});}
  loadList();return true;
 } catch(e) {
  if(request!==state.detailRequest)return;
  state.loadingDetail=false;
  document.querySelectorAll('[role="tab"]').forEach(tab=>tab.disabled=false);
  if(e.status===404){preferences.clearSelection();preferences.remember();preferences.notice("Saved or selected candidate is no longer available. Selection cleared.");}
  $("list-error").textContent=e.message;return false;
 }
}
function renderDecisions(r){clear("decision-history");for(const d of r.decisions.slice().reverse()){
 const item=element("div","",$("decision-history"),"history-item");
 element("h4",d.action,item);element("strong",`Recorded by ${d.actor}`,item);element("p",d.timestamp,item);
 element("p","Name is self-declared and unverified.",item,"small");
 element("p",`${d.reason} · ${d.context.location} · ${d.context.source_channel}`,item);
 element("p",`System ${d.recommendation.rag} · revision ${d.recommendation.revision_id} · override ${d.overrides?"yes":"no"}`,item,"small");
 const audit=element("details","",item);element("summary","Decision details",audit);
 element("p",`Event ${d.id} / Self-declared, unverified name / Trial/site: ${d.context.trial_site||"Unknown"}`,audit,"small");
 element("p",`Recommendation ${d.recommendation.recommendation_id}`,audit,"small");
 uiButton(item,"View original recommendation and evidence",()=>{
  openReader(`${d.material_id} - recorded recommendation`,host=>{
   definitionList(host,{event_id:d.id,previous_decision_id:d.previous_decision_id,...d.recommendation});
   uiButton(host,"Browse original evidence",async()=>{
    const evidenceHost=openReader(`${d.material_id} - original evidence`,body=>element("p","Loading original evidence...",body));
    try{
     const original=await call("/revisions/"+encodeURIComponent(d.recommendation.revision_id)+"/candidates/"+encodeURIComponent(d.material_guid));
     evidenceHost.replaceChildren();renderCandidateEvidence(evidenceHost,original);
    }catch(e){evidenceHost.textContent="Original evidence unavailable. The saved recommendation remains available. "+e.message;}
   });
  });
 });
}if(!r.decisions.length)element("p","No breeder decisions yet.",$("decision-history"));}
for(const id of ["search","rag","decision","marker","excluded","sort","descending","include-missing"])
 $(id).addEventListener(id==="search"?"input":"change",()=>{preferences.changed();clearTimeout(state.timer);state.timer=setTimeout(loadList,150);});
$("add-range").onclick=()=>{const metric=$("metric").value,min=$("min").value,max=$("max").value;
 if(min===""&&max==="")return;state.ranges[metric]={...(min!==""?{min:Number(min)}:{}),...(max!==""?{max:Number(max)}:{})};
 preferences.changed();ranges();loadList();};
$("open-history").onclick=()=>{
 const host=openReader("Earlier decisions and revisions",body=>element("p","Loading history...",body));
 Promise.all([call("/historical-decisions"),call("/revisions")]).then(([legacy,revisions])=>{
  if(!host.isConnected)return;host.replaceChildren();
  element("p","Legacy decisions keep their original trial scope. Missing snapshot identity remains unknown.",host);
  renderData(host,{earlier_decisions:legacy,...revisions});
 }).catch(e=>{if(host.isConnected)host.textContent=e.message;});
};
