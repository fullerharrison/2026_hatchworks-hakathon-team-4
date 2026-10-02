"use strict";
let enrichmentGeneration = 0, enrichmentPreviewRevision = null;
const enrichmentNames = {STATUS_LID:"Operation status", ACTUAL_DATE:"Actual operation date", DELAY_DAYS:"Operation delay", ...labels};
const enrichmentUnits = {YIELD_VS_CHECK_PCT:"%", DISEASE_SCORE_MEAN:"score", MOISTURE_PCT_MEAN:"%", GERMINATION_PCT:"%", FUMONISIN_PPM:"ppm", N_TRIALS_USED:"trials", N_TRIALS:"trials", GENOMIC_BREEDING_VALUE:"index", COLD_TEST_PCT:"%"};
const enrichmentDefinitions = {
 YIELD_T_HA:"Harvested yield per area for one field observation, in tonnes per hectare. Candidate yield versus checks is computed separately as a percentage.",
 DISEASE_SCORE:"Field disease score for one observation. Lower scores are favored by this provisional policy; the biological scale needs expert review.",
 MOISTURE_PCT:"Harvest moisture percentage for one field observation.",
 STATUS_LID:"Recorded operation status: completed, delayed or missed. Missed irrigation can exclude shared trials under the current policy.",
 ACTUAL_DATE:"The actual operation date, distinct from when supporting evidence was observed. Choose Unknown to explicitly clear this date.",
 DELAY_DAYS:"Reported operation delay in days. Supply the value supported by the source record; no date difference is inferred."
};
function enrichmentInvalidate(){++enrichmentGeneration;enrichmentPreviewRevision=null;$("enrichment-message").replaceChildren();}
function enrichmentRevision(revision){if(enrichmentPreviewRevision && enrichmentPreviewRevision!==revision){enrichmentInvalidate();$("enrichment-message").textContent="Evidence changed. Preview impact again before activation.";}}
function enrichmentDetail(r, previous){
 if(!previous || previous.material_guid!==r.material_guid){$("enrichment-form").reset();$("enrich-author").value=$("actor").value;targets();}
 else {const saved=$("enrich-target").value;targets(true,saved);}
}
function enrichmentTarget(){return $("enrich-target").value ? JSON.parse($("enrich-target").value) : null;}
function enrichmentPrior(t){return state.detail.active_corrections.filter(x=>x.table===(t.table||"germplasm") && x.row_id===(t.row_id||state.detail.material_guid) && x.field===t.field).at(-1);}
function targets(preserve=false, saved=""){
 const select=$("enrich-target");select.replaceChildren();
 const add=(text,value)=>{element("option",text,select).value=JSON.stringify(value);};
 if($("enrich-kind").value==="metadata")for(const field of ["NOTE","PEDIGREE","STAGE_CODE_LID","RESEARCH_STATION_GUID","SITE"])add(labels[field],{kind:"metadata",field});
 else for(const table of ["observation","lab","genomics","operations"])for(const row of state.detail.evidence[table]){
  const fields=table==="operations"?["STATUS_LID","ACTUAL_DATE","DELAY_DAYS"]:table==="genomics"?["GENOMIC_BREEDING_VALUE","MARKER_DISEASE_RESISTANCE"]:["NUMBER_VALUE"];
  const bridge=state.detail.evidence.bridge.find(x=>x.TRIAL_ENTRY_GUID===row.TRIAL_ENTRY_RELATIONSHIP_GUID);
  for(const field of fields){
   const trait=state.detail.dictionary.find(x=>x.TRAIT_GUID===row.TRAIT_GUID);
   const unit=field==="NUMBER_VALUE"?trait?.UNIT||"":field==="GENOMIC_BREEDING_VALUE"?"index":field==="DELAY_DAYS"?"days":"";
   const name=field==="NUMBER_VALUE"?readableLabel(row.TRAIT_CODE||trait?.TRAIT_CODE||"Measurement"):enrichmentNames[field];
   const scope=table==="lab"?"Material-level lab":table==="operations"?`Shared operation ${row.OPERATION_TYPE_LID}`:bridge?.ENTRY_ROLE_LID==="CHECK"?"Shared check":table==="genomics"?"Material-level genomics":"Candidate field observation";
   const t={kind:"correction",table,row_id:row.row_id,field,unit};const prior=enrichmentPrior(t);
   add(`${name} · ${show(prior?prior.value:row[field])} ${unit} · ${scope} · ${bridge?.TRIAL_ID||`source line ${row.line_no}`}`,t);
  }
 }
 if(saved && [...select.options].some(x=>x.value===saved))select.value=saved;
 enrichmentTargetChanged(preserve);
}
function enrichmentTargetChanged(preserve=false){
 const t=enrichmentTarget();if(!t)return;
 const prior=enrichmentPrior(t), supersedes=$("enrich-supersedes"), old=supersedes.value;
 supersedes.replaceChildren();element("option","Choose earlier addition",supersedes).value="";
 supersedes.parentElement.hidden=!prior||t.field==="NOTE";supersedes.required=!!prior&&t.field!=="NOTE";
 if(prior && t.field!=="NOTE")element("option",`${show(prior.value)} · ${prior.actor} · ${prior.created_at}`,supersedes).value=prior.id;
 if(preserve)supersedes.value=old;
 $("enrich-unit").value=t.unit||"Not applicable";
 const input=$("enrich-value"), choice=$("enrich-choice");
 const enums=t.field==="STATUS_LID"?["COMPLETED","DELAYED","MISSED"]:t.field==="MARKER_DISEASE_RESISTANCE"?["RESISTANT","INTERMEDIATE","SUSCEPTIBLE"]:null;
 input.hidden=!!enums;input.required=!enums;choice.hidden=!enums;choice.required=!!enums;choice.disabled=!enums;
 const choiceValue=choice.value;choice.replaceChildren();
 if(enums){element("option","Choose a value",choice).value="";for(const value of enums)element("option",value,choice).value=value;if(preserve)choice.value=choiceValue;}
 if(!preserve){input.value="";$("enrich-unknown").checked=false;}
 input.type=["NUMBER_VALUE","GENOMIC_BREEDING_VALUE","DELAY_DAYS"].includes(t.field)?"number":t.field==="ACTUAL_DATE"?"date":"text";input.step="any";
 $("enrich-unknown-wrap").hidden=t.field!=="ACTUAL_DATE";input.disabled=!!enums || t.field==="ACTUAL_DATE"&&$("enrich-unknown").checked;
 $("enrich-definition").textContent=t.kind==="metadata"?`${glossary[t.field]} Supply when this evidence was observed and a traceable source reference.`:`Correct one sourced value in ${t.unit||"the selected category or date"}. When observed describes the supporting evidence, not submission time. ${t.table==="lab"?"Lab evidence belongs to the material and has no trial relationship.":t.table==="operations"?"This shared operation may change several candidates.":t.table==="observation"?"Related check observations can affect several candidates.":"Genomic evidence belongs to the material, not an individual trial."}`;
 const host=$("enrich-source-details");host.replaceChildren();
 if(t.kind==="correction"){
  const row=state.detail.evidence[t.table].find(x=>x.row_id===t.row_id);
  const code=t.field==="NUMBER_VALUE"?state.detail.dictionary.find(x=>x.TRAIT_GUID===row.TRAIT_GUID)?.TRAIT_CODE:t.field;
  element("p",enrichmentDefinitions[code]||glossary[code]||"Use the value and unit documented in the selected source.",host);
 }
 if(t.kind==="correction")element("p",$("enrich-target").selectedOptions[0].textContent,host,"small");
 const details=element("details","",host);element("summary","View source details",details);
 if(t.kind==="correction"){
  const row=state.detail.evidence[t.table].find(x=>x.row_id===t.row_id);
  element("p",`Original: ${show(row[t.field])} · Current: ${show(prior?prior.value:row[t.field])} ${t.unit}`,details);
  renderData(details,[row]);
 }else element("p",`Current: ${t.field==="NOTE"?"Notes accumulate":show(prior?.value)}. Candidate: ${state.detail.material_id}`,details);
}
function enrichmentButton(host,label,action){const b=element("button",label,host);b.type="button";b.onclick=action;return b;}
function renderEnrichment(r){
 clear("enrichment-history");for(const item of r.enrichment_history.slice().reverse()){
  const div=element("div",`${item.status.toUpperCase()} · ${enrichmentNames[item.field]||readableLabel(item.field)} · ${show(item.value)} · ${item.actor}`,$("enrichment-history"),"history-item");
  element("p",`${item.reason} · ${item.source} · observed ${item.observed_at}`,div);
  const events=element("details","",div);element("summary","Review history",events);
  for(const e of item.events||[])element("p",`${e.timestamp} · ${e.action} · ${e.actor}: ${e.reason}`,events);
  if(item.status==="draft")enrichmentButton(div,"Submit for review",()=>reviewEnrichment(item,"submit"));
  if(item.status==="submitted"){enrichmentButton(div,"Approve",()=>reviewEnrichment(item,"approve"));enrichmentButton(div,"Reject",()=>reviewEnrichment(item,"reject"));}
  if(item.status==="approved")enrichmentButton(div,"Preview impact",()=>previewEnrichment(item));
 }
}
function enrichmentActionForm(title, buttonText, callback){
 const opener=document.activeElement;
 enrichmentInvalidate();const panel=$("enrichment-message"), heading=element("h4",title,panel);heading.tabIndex=-1;
 const form=element("form","",panel);const actor=element("input","",element("label","Your name",form));actor.id="enrichment-action-actor";actor.required=true;actor.value=$("enrich-author").value||$("actor").value;
 const reason=element("textarea","",element("label","Reason for this action",form));reason.id="enrichment-action-reason";reason.required=true;reason.minLength=5;
 const error=element("p","",form);error.setAttribute("role","alert");
 const submit=element("button",buttonText,form);submit.type="submit";
 enrichmentButton(form,buttonText==="Activate reviewed change"?"Cancel activation":"Cancel",()=>{enrichmentInvalidate();if(opener?.isConnected)opener.focus();});
 const generation=enrichmentGeneration, candidate=state.detail.material_guid, detailRequest=state.detailRequest;
 form.onsubmit=async e=>{e.preventDefault();if(generation!==enrichmentGeneration)return;submit.disabled=true;
  try{if(!actor.value.trim()||reason.value.trim().length<5)throw new Error("Enter your name and a reason of at least 5 characters.");
   await callback({actor:actor.value.trim(),reason:reason.value.trim()});
   // A list refresh may observe our new revision before the write response arrives.
   // Refresh committed work unless the user has navigated to another detail view.
   if(detailRequest!==state.detailRequest)return;await loadDetail(candidate);
  }catch(e){if(generation===enrichmentGeneration){error.textContent=e.message;if(e.status===409){form.dataset.stale="true";submit.disabled=true;if(form.dataset.item)enrichmentButton(form,"Refresh preview",()=>{const item=state.detail.enrichment_history.find(x=>x.id===form.dataset.item);if(item)previewEnrichment(item);});else enrichmentButton(form,"Refresh review history",()=>loadDetail(candidate));return;}}}
  finally{if(generation===enrichmentGeneration && !form.dataset.stale)submit.disabled=false;}
 };
 heading.focus();return {panel,form,generation};
}
function reviewEnrichment(item, action){enrichmentActionForm(`${action} evidence addition`,action==="submit"?"Confirm submission":action==="approve"?"Confirm approval":"Confirm rejection",data=>post(`/enrichment/${item.id}/review`,{...data,action}));}
async function previewEnrichment(item){
 enrichmentInvalidate();const generation=enrichmentGeneration;$("enrichment-message").textContent="Computing impact…";
 try{const preview=await call(`/enrichment/${item.id}/preview`);if(generation!==enrichmentGeneration)return;
  const {panel,form}=enrichmentActionForm("Confirm activation","Activate reviewed change",data=>post(`/enrichment/${item.id}/activate`,{...data,base_revision:preview.base_revision}));
  form.dataset.item=item.id;enrichmentPreviewRevision=preview.base_revision;
  const content=document.createElement("div");panel.insertBefore(content,form);const change=preview.source_change;
  element("p",`${change.material_id} · ${readableLabel(change.trait_code||change.field)}: ${show(change.current)} → ${show(change.proposed)} ${change.unit||""}`,content);
  element("p",`Source: ${change.source} · Observed: ${change.observed_at} · Reason: ${change.reason}`,content);
  element("p",`Reviewed by ${item.review?.actor||"unknown"}: ${item.review?.reason||""}`,content);
  element("p",`${preview.candidate_count} ${preview.candidate_count===1?"candidate":"candidates"} with changed measurements or system recommendations.`,content);
  if(!preview.candidate_count)element("p","Measurements and system recommendations are unchanged. The addition will be available as reviewed evidence.",content);
  element("p","Activation creates a shared evidence revision. Earlier breeder decisions retain their original recommendation and evidence. Future decisions use the new revision.",content);
  const details=element("details","",content);element("summary","Revision and original source details",details);
  element("p",`Revision ${preview.base_revision} · Snapshot ${preview.snapshot_id}`,details);renderData(details,[change]);
  const scroll=element("div","",content,"scroll"), table=element("table","",scroll,"enrichment-impact"), head=element("tr","",element("thead","",table));
  for(const name of ["Candidate","Measurement","Unit","Current","Proposed","System recommendation"])element("th",name,head);
  const body=element("tbody","",table);
  for(const row of preview.affected){
   const changed=Object.keys(row.before_metrics).filter(k=>row.before_metrics[k]!==row.after_metrics[k]);
   for(const key of changed.length?changed:[null]){const tr=element("tr","",body);
    const values=[row.material_id,key?labels[key]||key:"Recommendation only",enrichmentUnits[key]||"—",key?show(row.before_metrics[key]):"—",key?show(row.after_metrics[key]):"—",`${row.before} → ${row.after}`];
    values.forEach((v,i)=>{element("td",v,tr).dataset.label=["Candidate","Measurement","Unit","Current","Proposed","System RAG"][i];});
    tr.title=key?`${row.before_metrics[key]} → ${row.after_metrics[key]}`:"";
   }
  }
  if(preview.affected.length){const exact=element("details","",content);element("summary","Exact measurement comparisons",exact);renderData(exact,preview.affected);}
  for(const row of preview.affected){const caveats=element("details","",content);element("summary",`${row.material_id}: recommendation reasons and caveats`,caveats);
   element("p",`Current: ${row.before_reason}`,caveats);element("p",`Proposed: ${row.after_reason}`,caveats);
   element("p",`Current caveats: ${(row.before_warnings||[]).join("; ")||"None"}`,caveats);
   element("p",`Proposed caveats: ${(row.after_warnings||[]).join("; ")||"None"}`,caveats);
  }
  for(const warning of preview.source_warnings)element("p",`Source check: ${warning.check} (${warning.violations} records)`,content,"warn");
 }catch(e){if(generation===enrichmentGeneration)$("enrichment-message").textContent=e.message;}
}
$("enrich-kind").onchange=()=>targets();$("enrich-target").onchange=()=>enrichmentTargetChanged();
$("enrich-unknown").onchange=()=>{$("enrich-value").disabled=$("enrich-unknown").checked;};
$("enrichment-form").onsubmit=async e=>{
 e.preventDefault();if(!state.detail||state.loadingDetail)return;
 const candidate=state.detail.material_guid, generation=enrichmentGeneration, button=e.submitter;button.disabled=true;
 try{const target=enrichmentTarget();if(!target)throw new Error("Choose evidence to update");let value=$("enrich-choice").hidden?$("enrich-value").value:$("enrich-choice").value;
  if(target.field==="ACTUAL_DATE"&&$("enrich-unknown").checked)value=null;
  else if(["NUMBER_VALUE","GENOMIC_BREEDING_VALUE","DELAY_DAYS"].includes(target.field)){if(!value.trim())throw new Error("Proposed value is required");value=Number(value);}
  await post("/enrichment",{query:candidate,...target,value,actor:$("enrich-author").value,reason:$("enrich-reason").value,observed_at:$("observed-at").value,source:$("enrich-source").value,supersedes:$("enrich-supersedes").value||null});
  if(generation!==enrichmentGeneration)return;await loadDetail(candidate);$("enrichment-message").textContent="Draft saved. Submit it for review when ready.";
 }catch(e){if(generation===enrichmentGeneration)$("enrichment-message").textContent=e.message;}finally{button.disabled=false;}
};
