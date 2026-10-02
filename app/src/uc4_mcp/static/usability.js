"use strict";
const glossary = {
 search:"Search the material ID or GUID; a fragment can match several candidates.",
 rag:"System recommendation under the provisional candidate policy. It is separate from supplied RAG and the breeder's choice.",
 decision:"The latest recorded breeder action. Undecided means no action has been recorded.",
 marker:"Genomic disease-resistance category; it is not a measured field disease score.",
 excluded:"Trials excluded because irrigation was missed under this dataset's policy.",
 sort:"Order matching candidates by the selected field; this does not change eligibility.",
 descending:"Reverse the selected sort order.",
 metric:"Choose the measurement to filter. Multiple ranges are combined with AND.",
 min:"Inclusive lower bound in the selected trait's units.", max:"Inclusive upper bound in the selected trait's units.",
 "include-missing":"Include candidates with missing values for selected ranges; a missing value does not pass a scoring gate.",
 actor:"Self-declared, unverified name recorded with your decision and enrichment actions.",
 action:"Advance, Hold or Discard is your decision, independent of system and supplied RAG.",
 location:"Where the review happened, such as a meeting; not the agronomic trial site. Use Unknown if unavailable.",
 "source-channel":"Where feedback was captured, for example Breeder review or a meeting transcript.",
 "trial-context":"Optional trial or site context supplied by the reviewer; this does not add a source-data relationship.",
 reason:"Your reason for this decision, 5–1000 characters after trimming whitespace. Never reused for another candidate.",
 "enrich-kind":"A note adds context; a correction changes a sourced value after review and activation.",
 "enrich-target":"Original source row and field being corrected, or the metadata field being added.",
 "enrich-supersedes":"An earlier active addition explicitly replaced by this draft; its history remains available.",
 "enrich-value":"Proposed value. It does not affect recommendations until reviewed and activated.",
 "enrich-unit":"Unit from the trait dictionary for this source field; no automatic conversion is performed.",
 "observed-at":"When the new evidence was observed, not the time you submit this form.",
 "enrich-source":"Reference to the notebook, lab record or other evidence supporting the addition.",
 "enrich-reason":"Why the change is needed; preserve the distinction between observation and interpretation.",
 question:"Read-only evidence question. Selected candidate is the default context; explicitly named candidates take precedence.",
 "ask-dataset":"Remove the selected-candidate default while retaining the displayed evidence revision.",
 YIELD_VS_CHECK_PCT:"Candidate yield relative to checks (%): replication means within trials, then equally weighted usable-trial means, then ratio of candidate/check means ×100. Inspect comparisons and check observations.",
 DISEASE_SCORE_MEAN:"Mean reconstructed field disease score; lower is favored by this provisional policy. Scale and biological protocol need SME review.",
 MOISTURE_PCT_MEAN:"Mean reconstructed harvest moisture (%), across usable trial evidence.",
 GERMINATION_PCT:"Material-level laboratory germination (%). No trial key is supplied; it cannot be attributed to a trial.",
 FUMONISIN_PPM:"Material-level laboratory fumonisin concentration (ppm), without a supplied trial relationship.",
 N_TRIALS_USED:"Candidate trials retained by the current policy; missed-irrigation trials are excluded.",
 N_TRIALS:"Total distinct trials with candidate membership, before irrigation exclusions.",
 MARKER_DISEASE_RESISTANCE:"Genomic marker category, separate from field disease score. Resistant or Intermediate meets the GREEN marker gate.",
 GENOMIC_BREEDING_VALUE:"Genomic breeding-value index; context only. Biological calibration needs SME review.",
 COLD_TEST_PCT:"Material-level cold-test percentage; context only. Protocol and biological interpretation need SME review.",
 PEDIGREE:"Lineage metadata; unknown unless separately enriched and reviewed.",
 STAGE_CODE_LID:"Breeding stage metadata; unknown unless separately enriched and reviewed.",
 RESEARCH_STATION_GUID:"Station identifier; it does not establish coordinates or a trial-to-site relationship.",
 SITE:"Reviewed site metadata; it does not establish an unsupported trial relationship.",
 NOTE:"Additional context, not a numerical scoring gate."
};
function addHelp(host,text){
 const wrap=element("span","",host,"help-wrap"),button=element("button","ⓘ",wrap,"help-button");
 button.type="button";button.setAttribute("aria-label",`Explain ${host.firstChild?.textContent.trim()||"field"}`);button.setAttribute("aria-expanded","false");
 const tip=element("span",text,wrap,"help-text");tip.hidden=true;tip.id=`help-${document.querySelectorAll(".help-text").length}`;button.setAttribute("aria-controls",tip.id);
 const link=element("a"," Inspect policy and evidence",tip);link.href="#rules-panel";
 link.onclick=()=>{$("rules-panel").open=true;};
 const toggle=open=>{tip.hidden=!open;button.setAttribute("aria-expanded",String(open));};
 button.onclick=e=>{e.preventDefault();toggle(true);};
 wrap.onmouseenter=()=>toggle(true);wrap.onmouseleave=()=>{if(!wrap.contains(document.activeElement))toggle(false);};
 button.onfocus=()=>toggle(true);wrap.onfocusout=e=>{if(!wrap.contains(e.relatedTarget))toggle(false);};
 wrap.onkeydown=e=>{if(e.key==="Escape"){toggle(false);e.stopPropagation();}};
}
for(const [id,definition] of Object.entries(glossary)){
 const input=$(id);if(input?.closest("label"))addHelp(input.closest("label"),definition);
}
const headerFields=["search","rag","YIELD_VS_CHECK_PCT","DISEASE_SCORE_MEAN","N_TRIALS_USED","excluded","decision"];
document.querySelectorAll("#rows").forEach(body=>body.closest("table").querySelectorAll("th").forEach((th,i)=>addHelp(th,glossary[headerFields[i]])));
function formatMetric(field,value){
 if(value===null||value===undefined)return "Unknown";
 if(Array.isArray(value))return value.join(" or ");
 return typeof value==="number" ? value.toLocaleString(undefined,{minimumFractionDigits:field.startsWith("N_TRIALS")?0:2,maximumFractionDigits:field.startsWith("N_TRIALS")?0:2}) : String(value);
}
function criterionEvidence(r,field){
 const lab=["GERMINATION_PCT","FUMONISIN_PPM","COLD_TEST_PCT"].includes(field);
 const genomic=["MARKER_DISEASE_RESISTANCE","GENOMIC_BREEDING_VALUE"].includes(field);
 const keys=lab?["lab"]:genomic?["genomics"]:["bridge","observation","operations"];
 return {definition:glossary[field]||"Interpretation needs SME review",revision:r.revision_id,
  source_rows:Object.fromEntries(keys.map(k=>[k,r.evidence[k]])),dictionary:r.dictionary,
  trial_comparisons:lab||genomic?undefined:r.trial_comparisons,active_corrections:r.active_corrections};
}
function renderFilters(){
 clear("active-filters");
 for(const id of ["search","rag","decision","marker","excluded","include-missing"]){
  const input=$(id),value=input.type==="checkbox"?(input.checked?"Included":""):input.value;if(!value)continue;
  const filterNames={search:"Candidate",rag:"System RAG",decision:"Breeder choice",marker:"Disease marker",excluded:"Excluded trials","include-missing":"Missing values"};
  const chip=element("span",`${filterNames[id]}: ${value} `,$("active-filters"),"tag"),button=element("button","Remove",chip);button.type="button";
  button.onclick=()=>{if(input.type==="checkbox")input.checked=false;else input.value="";preferences.changed();loadList();};
 }
}
async function loadRules(){try{
 const rule=await call("/rule"),host=$("rules-content");clear("rules-content");
 element("p",`${rule.rule_version} — Provisional, inferred from synthetic evidence`,host);
 for(const [key,title] of [["gates","GREEN requires all"],["knockouts","RED knockouts (only with usable field data)"],["warnings","Warnings only"]]){
  element("h3",title,host);for(const c of rule[key]){const p=element("p",`${labels[c.field]} ${c.test} ${formatMetric(c.field,c.threshold)} ${c.unit}`,host);addHelp(p,glossary[c.field]);}
 }
 element("p",rule.missing_data,host);element("p","Otherwise AMBER. Cold test and genomic breeding value are context only. Scoring uses unrounded values.",host);
 uiButton(host,"View policy evidence",()=>openReader("Policy evidence and interpretation",body=>renderData(body,rule.criteria)));
}catch(e){$("rules-content").textContent=e.message;}}
function resetDecisionDraft(){
 state.decisionEditingFor=null;
 invalidateDecisionReview();
 for(const id of ["action","reason","trial-context"])$(id).value="";
 preferences.defaultsToForm();
 state.decisionRequest=null;$("decision-message").textContent="";contextSummary();
}
function contextSummary(){$("context-summary").textContent=`Review context: ${$("location").value||"Missing location"} / ${$("source-channel").value||"Missing channel"}`;}
for(const id of ["location","source-channel"])$(id).addEventListener("input",contextSummary);
$("decision-context").addEventListener("invalid",()=>{$("decision-context").open=true;},true);
function invalidateDecisionReview(){
 state.decisionReview=null;
 $("decision-review").hidden=true;$("decision-form").hidden=false;
}
const decisionReceipts=new Map();
function renderDecisionState(){
 const r=state.detail;if(!r)return;
 const receipt=decisionReceipts.get(r.material_guid);
 const latest=r.decisions.at(-1);
 // Server history order is authoritative, including decisions in the same second.
 const saved=receipt&&!r.decisions.some(d=>d.id===receipt.id)?receipt:latest;
 const editing=saved&&state.decisionEditingFor===saved.id;
 $("decision-saved").hidden=!saved||!!editing;
 $("decision-entry").hidden=!!saved&&!editing;
 $("another-decision").disabled=!!state.savingDecision||!!state.loadingDetail||latest?.id!==saved?.id;
 if(saved){
  clear("decision-saved-summary");
  element("p",saved.action,$("decision-saved-summary"),"verdict");
  element("strong",`Recorded by ${saved.actor}`,$("decision-saved-summary"));
  element("p",saved.reason,$("decision-saved-summary"));
  element("p",`${saved.timestamp} · Event ${saved.id}`,$("decision-saved-summary"),"small");
  element("p","Name is self-declared and unverified.",$("decision-saved-summary"),"small");
 }
}
$("another-decision").onclick=()=>{
 if(state.savingDecision||state.loadingDetail)return;
 const latest=state.detail?.decisions.at(-1);if(!latest)return;
 resetDecisionDraft();state.decisionEditingFor=latest.id;renderDecisionState();$("actor").focus();
};
$("view-decision-history").onclick=()=>selectCandidateTab("history",true);
function decisionMatches(body){
 const r=state.detail;
 return r && !state.loadingDetail && body.query===r.material_guid &&
  body.recommendation_id===r.recommendation_id && body.previous_decision_id===(r.decisions.at(-1)?.id||null);
}
$("edit-decision").onclick=()=>{
 if(state.savingDecision)return;
 invalidateDecisionReview();$("reason").focus();
};
$("decision-form").onsubmit=e=>{
 e.preventDefault();if(!state.detail||state.loadingDetail||state.savingDecision)return;
 const r=state.detail;
 if(r.decisions.length&&state.decisionEditingFor!==r.decisions.at(-1).id)return;
 const body={query:r.material_guid,action:$("action").value,actor:$("actor").value.trim(),reason:$("reason").value.trim(),
 context:{location:$("location").value.trim(),source_channel:$("source-channel").value.trim(),trial_site:$("trial-context").value.trim()},
 recommendation_id:r.recommendation_id,previous_decision_id:r.decisions.at(-1)?.id||null};
 for(const [id,value,min] of [["actor",body.actor,1],["reason",body.reason,5],["location",body.context.location,1],["source-channel",body.context.source_channel,1]]){
  if(value.length<min){
   if(["location","source-channel"].includes(id))$("decision-context").open=true;
   $("decision-message").textContent=id==="reason"?"Reason must contain at least 5 characters after trimming whitespace.":"Please complete "+(id==="actor"?"your name":"review context")+".";
   $(id).focus();return;
  }
 }
 if(!$("decision-form").reportValidity())return;
 const signature=JSON.stringify(body);
 if(state.decisionRequest?.signature!==signature)state.decisionRequest={signature,id:crypto.randomUUID()};
 // Store a serialized snapshot: final confirmation never reads mutable form fields.
 state.decisionReview={signature,id:state.decisionRequest.id};
 const prior=r.decisions.at(-1);
 $("decision-previous").textContent=prior?`Previous decision: ${prior.action}, recorded by ${prior.actor} at ${prior.timestamp}. Recording adds another history event; it does not replace the previous decision.`:"";
 clear("decision-review-summary");
 definitionList($("decision-review-summary"),{material_id:r.material_id,rag:r.rag,
  action:body.action,overrides:body.action!==({GREEN:"ADVANCE",AMBER:"HOLD",RED:"DISCARD"}[r.rag]),
  actor:body.actor+" (self-declared, unverified)",reason:body.reason,...body.context,revision_id:r.revision_id});
 const identity=element("details","",$("decision-review-summary"));
 element("summary","Recommendation identity",identity);
 definitionList(identity,{material_guid:r.material_guid,recommendation_id:r.recommendation_id});
 $("decision-message").textContent="Review only. Nothing has been recorded.";
 $("decision-form").hidden=true;$("decision-review").hidden=false;
 $("record-decision").disabled=false;$("decision-review-title").focus();
};
$("record-decision").onclick=async()=>{
 const review=state.decisionReview;
 if(!review||state.savingDecision)return;
 const body=JSON.parse(review.signature);
 if(!decisionMatches(body)){
  invalidateDecisionReview();$("decision-message").textContent="Candidate or evidence changed. Review the current candidate again.";return;
 }
 const request=state.detailRequest;
 state.savingDecision=true;$("record-decision").disabled=true;$("edit-decision").disabled=true;
 try{
 const saved=await post("/decisions",{...body,request_id:review.id});
  decisionReceipts.set(body.query,saved);
  if(state.selected===body.query&&(!state.loadingDetail||[body.query,saved.material_id].includes(state.detailTarget))){
   resetDecisionDraft();
   const receipt=`Decision recorded: ${saved.id} / ${saved.timestamp}`;
   $("decision-message").textContent=receipt;
   renderDecisionState();
   if(state.candidateTab==="decision")$("decision-saved-title").focus();
   const refreshed=await loadDetail(body.query);
   if(state.selected===body.query){
    $("decision-message").textContent=receipt+(refreshed===false?" - History refresh failed. Reload to view the saved event.":"");
   }
  }
 }catch(err){
  if(request===state.detailRequest){
   if(err.status===409){
    invalidateDecisionReview();state.decisionRequest=null;state.decisionEditingFor=null;
    const refreshed=await loadDetail(body.query);
    if(state.detailRequest===request+1 && state.selected===body.query)
     $("decision-message").textContent=refreshed===false
      ?"Evidence or latest decision changed. Refresh failed; reload before reviewing again."
      :"Evidence or latest decision changed. Review the refreshed candidate before recording.";
   }else{
    $("decision-message").textContent="Save could not be confirmed. Retry Record decision with this same confirmation. "+err.message;
   }
  }
 }finally{
 state.savingDecision=false;$("record-decision").disabled=!!state.loadingDetail;$("edit-decision").disabled=false;
  renderDecisionState();
 }
};
function displayAnswer(text){
 return text.split(/(\[[^\]]+\])/g).map(part=>part.startsWith("[")?part:part.replace(/\b\d+\.\d+\b/g,value=>Number(value).toFixed(2))).join("");
}
function updateAskContext(){const r=state.detail;$("ask-context").textContent=`${r&&!$("ask-dataset").checked?r.material_id:"Dataset-wide"} / ${r?.revision_id||"current revision captured on submit"}`;}
$("ask-dataset").onchange=updateAskContext;
const mobile=matchMedia("(max-width: 767px)");
function selectCandidateTab(name,focus=false){
 state.candidateTab=name;
 for(const tab of document.querySelectorAll('[role="tab"]')){
  const selected=tab.id===`tab-${name}`;
  tab.setAttribute("aria-selected",String(selected));tab.tabIndex=selected?0:-1;
  $(tab.getAttribute("aria-controls")).hidden=!selected;
 }
 if(focus)$("tab-"+name).focus();
 if(!$("detail").hidden)window.scrollTo({top:Math.max(0,window.scrollY+$("detail").getBoundingClientRect().top-(mobile.matches?0:$("ask-home").offsetHeight)-12),behavior:"instant"});
}
const candidateTabs=[...document.querySelectorAll('[role="tab"]')];
candidateTabs.forEach((tab,index)=>{
 tab.onclick=()=>selectCandidateTab(tab.id.slice(4));
 tab.onkeydown=e=>{
  const next=e.key==="ArrowRight"?(index+1)%candidateTabs.length:e.key==="ArrowLeft"?(index+candidateTabs.length-1)%candidateTabs.length:e.key==="Home"?0:e.key==="End"?candidateTabs.length-1:null;
  if(next!==null){e.preventDefault();selectCandidateTab(candidateTabs[next].id.slice(4),true);}
 };
});
function placeAsk(){if(!mobile.matches&&$("ask-dialog").open)$("ask-dialog").close();(mobile.matches?$("ask-mobile"):$("ask-home")).appendChild($("ask-panel"));}
mobile.addEventListener("change",placeAsk);placeAsk();
function navigationOffsets(){
 const askHeight=mobile.matches?0:$("ask-home").offsetHeight;
 document.documentElement.style.setProperty("--ask-height",`${askHeight}px`);
 document.documentElement.style.scrollPaddingTop=`${askHeight+$("candidate-navigation").offsetHeight+12}px`;
}
const navigationObserver=new ResizeObserver(navigationOffsets);
navigationObserver.observe($("ask-home"));navigationObserver.observe($("candidate-navigation"));
$("ask-launcher").onclick=()=>{$("ask-dialog").showModal();$("question").focus();};
$("ask-close").onclick=()=>{$("ask-dialog").close();$("ask-launcher").focus();};
let askSequence=0,askBusy=false;
const askUnavailable="Ask is unavailable right now. Your question has been kept. Try again shortly, or continue in Evidence.";
$("ask-form").onsubmit=async e=>{
 e.preventDefault();if(askBusy)return;const sequence=++askSequence,r=state.detail;
 const body={question:$("question").value,history:[],candidate:r&&!$("ask-dataset").checked?r.material_guid:null,revision_id:r?.revision_id||null};
 const button=$("ask-form").querySelector('button[type="submit"]');
 askBusy=true;button.disabled=true;$("ask-form").setAttribute("aria-busy","true");
 $("answer").textContent="Checking evidence… You can continue reviewing Evidence while waiting.";
 try{const a=await post("/ask",body);if(sequence!==askSequence)return;clear("answer");
  if(a.status==="error"){
   element("span",`Ask unavailable: ${a.context.candidate||"Dataset-wide"} / ${a.context.revision_id}`,$("answer"));
   element("p",askUnavailable,$("answer"),"warn");return;
  }
  element("span",`${a.status==="answered"?"Answer ready":"Review response"}: ${a.context.candidate||"Dataset-wide"} / ${a.context.revision_id}`,$("answer"));
  uiButton($("answer"),"View answer",()=>openAnswer(a));
 }catch(err){if(sequence===askSequence){
  const message=[404,409,422].includes(err.status)?err.message:askUnavailable;
  $("answer").textContent=`Ask failed for ${r?.material_id||"dataset"} / ${body.revision_id||"current revision"}: ${message}`;
 }}finally{askBusy=false;button.disabled=false;$("ask-form").setAttribute("aria-busy","false");}
};
