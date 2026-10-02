"use strict";
// Readable, text-only evidence views. Objects stay data; never display serialized JSON.
const readerStack=[];
let readerOpener=null;
const fieldNames={MOISTURE_PCT:"Moisture",YIELD_T_HA:"Yield",DISEASE_SCORE:"Disease score",source_file:"Source file",_source_file:"Source file",EXCLUDED_IRRIGATION_MISSED:"Excluded: irrigation missed",original_values:"Original corrected values",latest_corrections:"Latest applicable corrections",row_id:"Source row",line_no:"File line",_line_no:"File line",
 NUMBER_VALUE:"Observed value",TRAIT_CODE:"Trait",TRAIT_GUID:"Trait identifier",MATERIAL_ID:"Candidate",MATERIAL_GUID:"Material identifier",
 TRIAL_ID:"Trial",TRIAL_GUID:"Trial identifier",ENTRY_ROLE_LID:"Entry role",REPLICATION_NO:"Replication",UNIT:"Unit",
 recommendation_id:"Recommendation reference",revision_id:"Evidence revision",snapshot_id:"Source snapshot",rule_version:"Policy",
 material_id:"Candidate",material_guid:"Material identifier",rag:"System recommendation",supplied_rag:"Supplied recommendation",
 compatible_behavior:"Policy behavior",evidence_status:"Interpretation status",passed:"Meets GREEN gate",request_query:"Requested candidate",
 location:"Review location or meeting",overrides:"Differs from system recommendation",source_channel:"Captured through",trial_site:"Trial/site context",actor:"Recorded by",
 observed_at:"When observed",created_at:"Created",timestamp:"Recorded at",request_id:"Confirmation reference",previous_decision_id:"Previous decision",
 original_source_rows:"Original source rows",active_corrections:"Active corrections",trial_comparisons:"Trial comparisons",
 germplasm:"Material and pedigree",genomics:"Genomic evidence",lab:"Laboratory observations",bridge:"Trial membership",
 observation:"Field observations",operations:"Field operations",dictionary:"Trait definitions",earlier_decisions:"Earlier decisions"};
function readableLabel(key){return labels[key]||fieldNames[key]||String(key).replace(/^_/,"").replace(/_/g," ").toLowerCase().replace(/^./,x=>x.toUpperCase());}
function plainValue(value){return value===null||value===undefined||value===""?"Unknown":typeof value==="boolean"?(value?"Yes":"No"):String(value);}
function uiButton(host,label,handler){const b=element("button",label,host,"detail-button");b.type="button";b.onclick=handler;return b;}
function readableError(detail){
 if(typeof detail==="string")return detail;
 if(Array.isArray(detail))return detail.map(x=>`${(x.loc||[]).filter(k=>k!=="body").map(readableLabel).join(" / ")}: ${x.msg||"Please check this value."}`).join(" ");
 if(detail?.message)return detail.message+(detail.candidates?" Options: "+detail.candidates.map(x=>x.label||x.id).join(", "):"");
 return "The request could not be completed. Please check your entries and try again.";
}
function openReader(title,render){
 const dialog=$("evidence-dialog"),body=$("evidence-dialog-body");
 if(dialog.open)readerStack.push({title:$("evidence-dialog-title").textContent,nodes:[...body.childNodes],scroll:body.scrollTop,focus:document.activeElement});
 else{readerStack.length=0;readerOpener=document.activeElement;}
 body.replaceChildren();$("evidence-dialog-title").textContent=title;
 const content=element("section","",body);render(content);
 $("evidence-back").hidden=!readerStack.length;
 if(!dialog.open)dialog.showModal();body.scrollTop=0;$("evidence-dialog-title").focus();return content;
}
$("evidence-back").onclick=()=>{const prior=readerStack.pop();if(!prior)return;
 $("evidence-dialog-title").textContent=prior.title;$("evidence-dialog-body").replaceChildren(...prior.nodes);
 $("evidence-dialog-body").scrollTop=prior.scroll;$("evidence-back").hidden=!readerStack.length;
 (prior.focus?.isConnected?prior.focus:$("evidence-dialog-title")).focus();
};
$("evidence-close").onclick=()=>$("evidence-dialog").close();
$("evidence-dialog").addEventListener("close",()=>{readerStack.length=0;$("evidence-dialog-body").replaceChildren();if(readerOpener?.isConnected)readerOpener.focus();});
function definitionList(host,record){
 const list=element("dl","",host,"evidence-fields");
 for(const [key,value] of Object.entries(record)){
  element("dt",readableLabel(key),list);const cell=element("dd","",list);
  if(value!==null&&typeof value==="object")renderData(cell,value);else cell.textContent=plainValue(value);
 }
 return list;
}
function renderData(host,data){
 if(data===null||typeof data!=="object"){element("p",plainValue(data),host);return;}
 if(Array.isArray(data)){
  if(!data.length){element("p","No records for this section.",host,"small");return;}
  if(data.every(x=>x===null||typeof x!=="object")){const list=element("ul","",host);for(const x of data)element("li",plainValue(x),list);return;}
  for(const [index,row] of data.entries()){
   if(row===null||typeof row!=="object"){element("p",plainValue(row),host);continue;}
   const card=element("details","",host,"record-card");
   element("summary",row.material_id||row.MATERIAL_ID||row.TRIAL_ID||row.criterion||row.action||row.description||row.source_file||`Record ${index+1}`,card);
   definitionList(card,row);
  }return;
 }
 const scalars={},nested=[];
 for(const [key,value] of Object.entries(data)){
  if(value!==null&&typeof value==="object")nested.push([key,value]);else scalars[key]=value;
 }
 if(Object.keys(scalars).length)definitionList(host,scalars);
 for(const [key,value] of nested){const section=element("details","",host,"record-card");element("summary",readableLabel(key),section);renderData(section,value);}
}
function marginDescription(c){
 if(c.margin===null)return c.value===null?"Missing evidence":"Category test";
 if(c.margin===0)return "At threshold";
 const distance=formatMetric(c.field,Math.abs(c.margin)),unit=c.unit==="%"?"pp":c.unit;
 return `${distance} ${unit} ${c.margin>0?"above":"below"} ${c.test===">="?"minimum":c.test==="<="?"maximum":"threshold"}`;
}
function sourceRows(host,rows,r){
 if(!rows.length){element("p","No source rows available for this criterion.",host);return;}
 const wrap=element("div","",host,"source-scroll");wrap.tabIndex=0;wrap.setAttribute("role","region");wrap.setAttribute("aria-label","Source observations");
 const table=element("table","",wrap,"source-table"),thead=element("thead","",table),head=element("tr","",thead);
 for(const title of ["Material / role","Trial","Measurement","Effective value","Unit","Source record"])element("th",title,head).scope="col";
 const body=element("tbody","",table);
 for(const original of rows){
  const entry=(r.evidence?.bridge||[]).find(b=>b.TRIAL_ENTRY_GUID===original.TRIAL_ENTRY_RELATIONSHIP_GUID);
  const trait=(r.dictionary||[]).find(d=>d.TRAIT_GUID===original.TRAIT_GUID);
  const row=element("tr","",body);
  const material=original.MATERIAL_ID||entry?.MATERIAL_ID||(original.MATERIAL_GUID===r.material_guid?r.material_id:original.MATERIAL_GUID)||"Unknown";
  for(const value of [material+(entry?` (${entry.ENTRY_ROLE_LID==="CHECK"?"Check":"Candidate"})`:""),original.TRIAL_ID||entry?.TRIAL_ID||"Material-level; no trial link",
   readableLabel(original.TRAIT_CODE||trait?.TRAIT_CODE||original.OPERATION_TYPE_LID||"Record"),original.NUMBER_VALUE??original.GENOMIC_BREEDING_VALUE??original.STATUS_LID,
   original.UNIT||trait?.UNIT||"Not supplied"]){element("td",plainValue(value),row);}
  const cell=element("td","",row);const details=element("details","",cell);element("summary",original.source_file||"Source details",details);
  definitionList(details,{row_id:original.row_id,line_no:original.line_no,revision_id:original.revision_id});
  if(Object.keys(original.original_values||{}).length){definitionList(details,{original_values:original.original_values,latest_corrections:original.latest_corrections});details.open=true;}
  const extra=element("details","",details);element("summary","All original fields",extra);definitionList(extra,original);
 }
}
function renderCandidateEvidence(host,r){
 definitionList(host,{material_id:r.material_id,revision_id:r.revision_id,snapshot_id:r.snapshot_id,rule_version:r.rule_version});
 element("p","Original values are shown at full precision. Active corrections are listed separately; original source rows are retained.",host,"small");
 for(const [name,rows] of Object.entries(r.evidence||{})){
  const section=element("details","",host,"record-card");element("summary",`${readableLabel(name)} (${rows.length})`,section);
  if(name==="observation"||name==="lab")sourceRows(section,rows,r);else renderData(section,rows);
 }
 const changes=element("details","",host,"record-card");element("summary","Active corrections",changes);renderData(changes,r.active_corrections||[]);
 const dictionary=element("details","",host,"record-card");element("summary","Trait definitions and units",dictionary);renderData(dictionary,r.dictionary||[]);
}
function openCriterionEvidence(r,c){
 const payload=r.criterion_evidence[c.field];
 openReader(`${r.material_id} - ${labels[c.field]||c.field}`,host=>{
  definitionList(host,{material_id:payload.material_id,snapshot_id:payload.snapshot_id,revision_id:payload.revision_id,
   observed_value:c.value,unit:c.unit,comparison:c.test,threshold:c.threshold,assessment:c.status,margin:c.margin});
  element("p",payload.calculation,host);
  element("p","Effective values retain full precision. Original corrected values and the latest correction provenance are shown with each source row.",host,"small");
  for(const [name,rows] of Object.entries(payload.source_rows)){
   const section=element("details","",host,"record-card");element("summary",`${readableLabel(name)} (${rows.length})`,section);
   section.open=["observation","lab","genomics"].includes(name);
   if(["observation","lab"].includes(name))sourceRows(section,rows,r);else renderData(section,rows);
  }
  const trials=element("details","",host,"record-card");element("summary","Trial comparisons and exclusions",trials);
  renderData(trials,payload.trial_comparisons);
  const traits=element("details","",host,"record-card");element("summary","Matching trait definitions",traits);renderData(traits,payload.dictionary);
  const corrections=element("details","",host,"record-card");element("summary","Correction history (including superseded)",corrections);renderData(corrections,payload.active_corrections);
  uiButton(host,"View complete source evidence",()=>openReader(`${r.material_id} - complete source evidence`,body=>renderCandidateEvidence(body,r)));
 });
}
const toolTitles={get_candidate:"Candidate evidence",score_candidate:"Candidate assessment",get_candidate_rule:"Provisional policy",query_candidates:"Matching candidates",list_sources:"Source files",find_candidate:"Candidate identity"};
function tracesForCitation(a,c){
 if(!c.found)return [];
 if(c.ref.startsWith("tool:"))return (a.tool_calls||[]).filter(t=>t.name===c.ref.slice(5));
 const split=c.ref.lastIndexOf("#"),file=c.ref.slice(0,split),id=c.ref.slice(split+1);
 function matches(v){if(!v||typeof v!=="object")return false;
  if(v.source_file===file&&String(v.row_id)===id)return true;
  if(Array.isArray(v.evidence_row_ids)&&v.evidence_row_ids.includes(c.ref))return true;
  return Object.values(v).some(matches);
 }
 return (a.tool_calls||[]).filter(t=>matches(t.result));
}
function openCitation(a,c,index){openReader(`Source ${index+1} - ${toolTitles[c.ref.slice(5)]||"Original evidence"}`,host=>{
 definitionList(host,{candidate_context:a.context.candidate||"Dataset-wide",revision_id:a.context.revision_id,source_reference:c.ref});
 const traces=tracesForCitation(a,c);
 if(!traces.length){element("p","This reference could not be verified against this answer's evidence.",host);return;}
 for(const trace of traces){element("h3",toolTitles[trace.name]||readableLabel(trace.name),host);
  const result=trace.result?.result??trace.result;
  if(result?.evidence)renderCandidateEvidence(host,result);else renderData(host,result);
 }
});}
function answerText(host,text,a){
 // Only text nodes and explicit strong elements are created. Model HTML is never executed.
 for(const paragraph of displayAnswer(text).split(/\n\s*\n/)){
  const p=element("p","",host,"answer-paragraph");
  for(const part of paragraph.split(/(\*\*[^*]+\*\*|\[[^\]]+\])/g)){
   if(part.startsWith("**")&&part.endsWith("**"))element("strong",part.slice(2,-2),p);
   else if(part.startsWith("[")&&part.endsWith("]")){
    const index=(a.citations||[]).findIndex(c=>c.ref===part.slice(1,-1));
    if(index>=0)uiButton(p,`Source ${index+1}`,()=>openCitation(a,a.citations[index],index));else p.appendChild(document.createTextNode(part));
   }else p.appendChild(document.createTextNode(part));
  }
 }
}
function openAnswer(a){openReader(`Answer for ${a.context.candidate||"the dataset"}`,host=>{
 element("p",`Request context: ${a.context.candidate||"Dataset-wide"} / ${a.context.revision_id}`,host,"small");
 if(a.status!=="answered")element("p",a.status==="unverified"?"This answer could not be verified. Review the source evidence.":readableLabel(a.status),host,"warn");
 const paragraphs=(a.text||"No answer returned.").split(/\n\s*\n/);
 answerText(host,paragraphs.shift(),a);
 if(paragraphs.length){const more=element("details","",host,"answer-details");element("summary","More detail",more);answerText(more,paragraphs.join("\n\n"),a);}
 element("p",a.disclaimer||"",host,"small");
 const sources=element("section","",host,"answer-sources");element("h3","Sources",sources);
 (a.citations||[]).forEach((c,i)=>uiButton(sources,`Source ${i+1}: ${toolTitles[c.ref.slice(5)]||"Original record"}${c.found?"":" (unverified)"}`,()=>openCitation(a,c,i)));
});}
