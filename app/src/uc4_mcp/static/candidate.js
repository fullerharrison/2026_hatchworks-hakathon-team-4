"use strict";
const $ = id => document.getElementById(id);
const state = {ranges:{}, selected:null, detail:null, timer:null, listRequest:0, detailRequest:0, decisionRequest:null};
const labels = {YIELD_VS_CHECK_PCT:"Yield vs checks (%)", DISEASE_SCORE_MEAN:"Disease score",
 MOISTURE_PCT_MEAN:"Moisture (%)", GERMINATION_PCT:"Germination (%)", FUMONISIN_PPM:"Fumonisin (ppm)",
 N_TRIALS_USED:"Usable trials", N_TRIALS:"Total trials", MARKER_DISEASE_RESISTANCE:"Disease resistance marker",
 GENOMIC_BREEDING_VALUE:"Genomic breeding value", COLD_TEST_PCT:"Cold test (%)",
 PEDIGREE:"Pedigree", STAGE_CODE_LID:"Breeding stage", RESEARCH_STATION_GUID:"Research station", SITE:"Site", NOTE:"Note"};
function show(v) { return v === null || v === undefined || v === "" ? "unknown" :
 typeof v==="number"?v.toLocaleString(undefined,{maximumFractionDigits:2}):String(v); }
function element(tag, text, parent, cls) { const x=document.createElement(tag);x.textContent=text;if(cls)x.className=cls;parent.appendChild(x);return x; }
function clear(id) { $(id).replaceChildren(); }
async function call(path, options={}) {
 const response=await fetch(path,options);let data;
 try {data=await response.json();} catch {data={detail:await response.text()};}
 if(!response.ok) throw new Error(typeof data.detail==="string" ? data.detail : JSON.stringify(data.detail||data));
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
  const b=element("button","Remove",span);b.type="button";b.onclick=()=>{delete state.ranges[metric];ranges();loadList();};
 }
}
async function loadList() {
 const request=++state.listRequest;
 $("list-error").textContent="";
 const q=query();$("export").href="/candidates.csv"+(q?"?"+q:"");
 try {
  const data=await call("/candidates"+(q?"?"+q:""));
  let next=data.next_offset;
  while(next!==null){const page=await call("/candidates?"+(q?q+"&":"")+"offset="+next);
   if(page.revision_id!==data.revision_id)throw new Error("Evidence changed while loading; refresh the list.");
   data.rows.push(...page.rows);next=page.next_offset;}
  if(request!==state.listRequest)return;
  $("count").textContent=`Candidates: ${data.total} matching of ${data.total_available}`;
  $("revision").textContent=`Evidence revision ${data.revision_id} · source ${data.snapshot_id.slice(0,12)}`;
  clear("rows");for(const r of data.rows) {
   const tr=document.createElement("tr");tr.tabIndex=0;if(r.material_guid===state.selected)tr.className="selected";
   for(const value of [r.material_id,r.rag,r.metrics.YIELD_VS_CHECK_PCT,r.metrics.DISEASE_SCORE_MEAN,
    r.metrics.N_TRIALS_USED,r.excluded_trials,r.latest_decision?.action])element("td",show(value),tr).title=String(value??"unknown");
   tr.onclick=()=>loadDetail(r.material_id);tr.onkeydown=e=>{if(e.key==="Enter")loadDetail(r.material_id);};$("rows").appendChild(tr);
  }
 } catch(e) {$("list-error").textContent=e.message;}
}
async function loadDetail(query) {
 const request=++state.detailRequest;
 try {
  const r=await call("/candidates/"+encodeURIComponent(query));if(request!==state.detailRequest)return;
  state.detail=r;state.selected=r.material_guid;
  $("detail").hidden=false;$("detail-title").textContent=`${r.material_id} · candidate evidence`;
  const b=$("recommendation");b.className="banner "+r.rag.toLowerCase();b.replaceChildren();
  element("p",`${r.rag} · ${r.reason}`,b,"verdict");
  element("p",`Supplied: ${r.supplied_rag} · ${r.supplied_reason}`,b);
  element("p",`Provisional rule ${r.rule_version} · ${r.revision_id}`,b,"small");
  $("source-note").textContent=r.metadata_note;
  clear("criteria");for(const c of r.criteria){const tr=document.createElement("tr");
   for(const x of [labels[c.field]||c.field,show(c.value),`${c.test} ${show(c.threshold)}`,c.passed?"yes":"no"])element("td",x,tr).title=String(c.value??"unknown");
   $("criteria").appendChild(tr);}
  clear("metrics");for(const [k,v] of Object.entries(r.metrics))if(!r.criteria.some(c=>c.field===k))element("p",`${labels[k]||k}: ${show(v)}`,$("metrics"));
  for(const [field,item] of Object.entries(r.reviewed_metadata))element("p",`${labels[field]||field}: ${item.value} (reviewed enrichment)`,$("metrics"));
  const summary=$("evidence-summary");summary.replaceChildren();
  element("p",`Usable trials: ${r.metrics.N_TRIALS_USED}; excluded trials: ${r.excluded_trials}`,summary);
  for(const warning of r.warnings)element("p",warning,summary,"warn");
  for(const warning of r.source_warnings)element("p",`Revision-wide source check: ${warning.check} (${warning.violations} records)`,summary,"warn");
  for(const [k,v] of Object.entries(r.evidence))element("p",`${k}: ${v.length} source rows`,summary);
  const table=element("table","",summary);const head=element("tr","",table);
  for(const text of ["Trial","Yield vs checks (%)","Irrigation exclusion"])element("th",text,head);
  for(const trial of r.trial_comparisons){const row=element("tr","",table);
   for(const value of [trial.TRIAL_ID,show(trial.TRIAL_YIELD_VS_CHECK_PCT),trial.EXCLUDED_IRRIGATION_MISSED?"Excluded":"Included"])element("td",value,row);}
  $("evidence").textContent=JSON.stringify({trial_comparisons:r.trial_comparisons,original_source_rows:r.evidence,
   active_corrections:r.active_corrections,dictionary:r.dictionary},null,2);
  renderDecisions(r);targets();renderEnrichment(r);loadList();
 } catch(e) {$("list-error").textContent=e.message;}
}
function renderDecisions(r){clear("decision-history");for(const d of r.decisions.slice().reverse()){
 const item=element("div",`${d.action} by ${d.actor} at ${d.timestamp}`,$("decision-history"),"history-item");
 element("p",`${d.reason} · ${d.context.location} · ${d.context.source_channel}`,item);
 element("p",`System ${d.recommendation.rag} · revision ${d.recommendation.revision_id} · override ${d.overrides?"yes":"no"}`,item,"small");
}if(!r.decisions.length)element("p","No breeder decisions yet.",$("decision-history"));}
function targets(){const select=$("enrich-target");select.replaceChildren();
 if($("enrich-kind").value==="metadata"){
  for(const field of ["NOTE","PEDIGREE","STAGE_CODE_LID","RESEARCH_STATION_GUID","SITE"]){const option=element("option",labels[field],select);option.value=JSON.stringify({kind:"metadata",field});}
 } else {
  for(const table of ["observation","lab","genomics","operations"])
  for(const row of state.detail.evidence[table]){
   const fields=table==="operations"?["STATUS_LID","ACTUAL_DATE","DELAY_DAYS"]:
    table==="genomics"?["GENOMIC_BREEDING_VALUE","MARKER_DISEASE_RESISTANCE"]:["NUMBER_VALUE"];
   for(const field of fields){const unit=field==="NUMBER_VALUE"?
    state.detail.dictionary.find(d=>d.TRAIT_GUID===row.TRAIT_GUID)?.UNIT||"":field==="GENOMIC_BREEDING_VALUE"?"index":"";
    const option=element("option",`${table} · ${row.row_id} · ${row.TRAIT_CODE||row.OPERATION_TYPE_LID||field} · ${field}`,select);
    option.value=JSON.stringify({kind:"correction",table,row_id:row.row_id,field,unit});
   }
  }
 }
 $("enrich-unit").value=select.selectedOptions.length?JSON.parse(select.value).unit||"":"";
 supersedes();
}
function supersedes(){const select=$("enrich-supersedes");select.replaceChildren();element("option","None",select).value="";
 if(!$("enrich-target").value)return;const target=JSON.parse($("enrich-target").value);
 for(const item of state.detail.active_corrections){if(item.field===target.field &&
  item.row_id===(target.row_id||state.detail.material_guid)){
  element("option",`${item.value} · ${item.actor} · ${item.created_at}`,select).value=item.id;}}
}
function renderEnrichment(r){clear("enrichment-history");for(const item of r.enrichment_history.slice().reverse()){
 const div=element("div",`${item.status.toUpperCase()} · ${labels[item.field]||item.field} · ${show(item.value)} · ${item.actor}`,$("enrichment-history"),"history-item");
 element("p",`${item.reason} · ${item.source} · observed ${item.observed_at}`,div);
 if(item.review)element("p",`Reviewed by ${item.review.actor}: ${item.review.reason}`,div,"small");
 if(item.events?.length){const events=element("details","",div);element("summary","Review history",events);
  for(const event of item.events)element("p",`${event.timestamp} · ${event.action} · ${event.actor}: ${event.reason}`,events,"small");}
 const button=(label,handler)=>{const b=element("button",label,div);b.type="button";b.onclick=()=>handler(item);};
 if(item.status==="draft")button("Submit for review",x=>review(x,"submit"));
 if(item.status==="submitted"){button("Approve",x=>review(x,"approve"));button("Reject",x=>review(x,"reject"));}
 if(item.status==="approved")button("Preview impact and activate",activate);
}if(!r.enrichment_history.length)element("p","No enrichment yet.",$("enrichment-history"));}
async function review(item,action){try{const actor=$("actor").value.trim();const reason=$("enrich-reason").value.trim();
 if(!actor||reason.length<5)throw new Error("Enter your name and a review reason (5+ characters).");
 await post(`/enrichment/${item.id}/review`,{action,actor,reason});await loadDetail(state.detail.material_id);
 $("enrichment-message").textContent=`${action} recorded`;
}catch(e){$("enrichment-message").textContent=e.message;}}
async function activate(item){try{const preview=await call(`/enrichment/${item.id}/preview`);
 const panel=$("enrichment-message");panel.replaceChildren();
 element("p",`${preview.candidate_count} candidates have changed measurements or RAG. ${item.field}: ${item.value}`,panel);
 for(const warning of preview.source_warnings)element("p",`Source check: ${warning.check} (${warning.violations} records)`,panel,"warn");
 for(const row of preview.affected){element("p",`${row.material_id}: ${row.before} → ${row.after}`,panel);
  for(const key of Object.keys(row.before_metrics))if(row.before_metrics[key]!==row.after_metrics[key])
   element("p",`${key}: ${show(row.before_metrics[key])} → ${show(row.after_metrics[key])}`,panel,"small");}
 const button=element("button","Activate reviewed change",panel);button.type="button";
 button.onclick=async()=>{try{
  const actor=$("actor").value.trim(),reason=$("enrich-reason").value.trim();
  if(!actor||reason.length<5)throw new Error("Enter your name and an activation reason (5+ characters).");
  button.disabled=true;
  await post(`/enrichment/${item.id}/activate`,{base_revision:preview.base_revision,actor,reason});
  await loadDetail(state.detail.material_id);panel.textContent="New evidence revision active.";
 }catch(e){panel.textContent=e.message;}};
}catch(e){$("enrichment-message").textContent=e.message;}}
for(const id of ["search","rag","decision","marker","excluded","sort","descending","include-missing"])
 $(id).addEventListener(id==="search"?"input":"change",()=>{clearTimeout(state.timer);state.timer=setTimeout(loadList,150);});
$("add-range").onclick=()=>{const metric=$("metric").value,min=$("min").value,max=$("max").value;
 if(min===""&&max==="")return;state.ranges[metric]={...(min!==""?{min:Number(min)}:{}),...(max!==""?{max:Number(max)}:{})};
 ranges();loadList();};
$("reset").onclick=()=>{for(const id of ["search","rag","decision","marker","excluded"])$(id).value="";
 $("sort").value="material_id";$("descending").checked=false;$("include-missing").checked=false;
 $("min").value="";$("max").value="";
 state.ranges={};ranges();loadList();};
$("enrich-kind").onchange=targets;$("enrich-target").onchange=()=>{$("enrich-unit").value=JSON.parse($("enrich-target").value).unit||"";supersedes();};
$("decision-form").onsubmit=async e=>{e.preventDefault();if(!state.detail)return;
 const r=state.detail,latest=r.decisions.at(-1);
 const body={query:r.material_guid,action:$("action").value,actor:$("actor").value,
 reason:$("reason").value,context:{location:$("location").value,source_channel:$("source-channel").value,
 trial_site:$("trial-context").value},recommendation_id:r.recommendation_id,
 previous_decision_id:latest?.id||null};
 const signature=JSON.stringify(body);
 if(state.decisionRequest?.signature!==signature)state.decisionRequest={signature,id:crypto.randomUUID()};
 try{await post("/decisions",{...body,request_id:state.decisionRequest.id});state.decisionRequest=null;
 await loadDetail(r.material_id);$("decision-message").textContent="Decision recorded.";
 }catch(err){$("decision-message").textContent=err.message;if(err.message.includes("changed"))await loadDetail(r.material_id);}};
$("enrichment-form").onsubmit=async e=>{e.preventDefault();if(!state.detail)return;
 try{const target=JSON.parse($("enrich-target").value);
  const value=target.field==="NUMBER_VALUE"||target.field==="GENOMIC_BREEDING_VALUE"||target.field==="DELAY_DAYS"?
   Number($("enrich-value").value):target.field==="ACTUAL_DATE"&&$("enrich-value").value.toLowerCase()==="unknown"?
   null:$("enrich-value").value;
  await post("/enrichment",{query:state.detail.material_guid,...target,value,actor:$("actor").value,
   reason:$("enrich-reason").value,observed_at:$("observed-at").value,
   source:$("enrich-source").value,supersedes:$("enrich-supersedes").value||null});await loadDetail(state.detail.material_id);
  $("enrichment-message").textContent="Draft saved.";
 }catch(err){$("enrichment-message").textContent=err.message;}};
$("ask-form").onsubmit=async e=>{e.preventDefault();$("answer").textContent="Checking evidence…";
 try{const a=await post("/ask",{question:$("question").value,history:[]});
  $("answer").textContent=a.text+"\n"+a.disclaimer;
 }catch(err){$("answer").textContent=err.message;}};
$("historical-panel").ontoggle=async()=>{if(!$("historical-panel").open)return;
 try{const [legacy,revisions]=await Promise.all([call("/historical-decisions"),call("/revisions")]);
  $("historical-records").textContent=JSON.stringify({legacy_decisions:legacy,...revisions},null,2);
 }catch(e){$("historical-records").textContent=e.message;}};
loadList();
