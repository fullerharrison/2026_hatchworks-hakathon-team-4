"use strict";
const boundaryControls = (() => {
 let rule=null;
 const specs=kind=>kind==="green_gate"?rule?.gates:rule?.knockouts;
 const selected=()=>specs($("boundary-kind").value)?.find(c=>c.field===$("boundary-field").value);
 function structurallyValid(b){
  return !!b && typeof b==="object" && !Array.isArray(b) && Object.keys(b).sort().join(",")==="field,kind,side,tolerance" &&
   ["green_gate","red_knockout"].includes(b.kind) && ["both","meets","fails"].includes(b.side) &&
   typeof b.tolerance==="number" && Number.isFinite(b.tolerance) && b.tolerance>=0 &&
   typeof b.field==="string" && b.field.length>0 &&
   (b.field!=="N_TRIALS_USED"||Number.isInteger(b.tolerance));
 }
 function valid(b){return structurallyValid(b) && !!specs(b.kind)?.some(c=>c.field===b.field&&typeof c.threshold==="number");}
 function choices(){
  const previous=$("boundary-field").value;$("boundary-field").replaceChildren();
  for(const c of specs($("boundary-kind").value)||[])if(typeof c.threshold==="number"){
   const option=element("option",labels[c.field],$("boundary-field"));option.value=c.field;
  }
  if([...$("boundary-field").options].some(o=>o.value===previous))$("boundary-field").value=previous;
  const red=$("boundary-kind").value==="red_knockout";
  $("boundary-side").options[1].textContent=red?"Triggers knockout test":"Meets GREEN gate";
  $("boundary-side").options[2].textContent=red?"Does not trigger knockout test":"Fails GREEN gate";
  band();
 }
 function band(){
  const c=selected();if(!c)return;
  const text=$("boundary-tolerance").value,t=Number(text),unit=c.unit==="%"?"percentage points":c.unit;
  $("boundary-tolerance").step=c.field==="N_TRIALS_USED"?"1":"any";
  $("boundary-band").textContent=`${c.test} ${c.threshold} ${c.unit}; tolerance in ${unit}. `+
   (text!==""&&Number.isFinite(t)&&t>=0?`Inclusive band: ${c.threshold-t} to ${c.threshold+t} ${c.unit}.`:"Enter a tolerance to enable proximity.");
 }
 function sortOption(){
  const option=$("sort").querySelector('[value="boundary_distance"]');
  if(state.boundary&&!option){const o=element("option","Distance to boundary",$("sort"));o.value="boundary_distance";}
  if(!state.boundary&&option){if($("sort").value==="boundary_distance")$("sort").value="material_id";option.remove();}
 }
 function clear(){state.boundary=null;$("boundary-tolerance").value="";$("boundary-side").value="both";sortOption();band();}
 function restore(b){state.boundary=valid(b)?structuredClone(b):null;if(state.boundary){$("boundary-kind").value=b.kind;choices();$("boundary-field").value=b.field;$("boundary-tolerance").value=b.tolerance;$("boundary-side").value=b.side;}sortOption();band();}
 function chip(){if(!state.boundary)return;const b=state.boundary,c=specs(b.kind).find(c=>c.field===b.field);
  const host=element("span",`Near ${labels[b.field]} ${c.test} ${c.threshold} ${c.unit}, ±${b.tolerance} ${c.unit==="%"?"pp":c.unit}, ${b.side} `,$("active-filters"),"tag");
  uiButton(host,"Remove",()=>{clear();preferences.changed();loadList();});
 }
 function init(policy){rule=policy;$("boundary-controls").disabled=false;choices();}
 $("boundary-kind").onchange=choices;$("boundary-field").onchange=band;$("boundary-tolerance").oninput=band;
 $("boundary-form").onsubmit=e=>{e.preventDefault();const b={field:$("boundary-field").value,kind:$("boundary-kind").value,tolerance:Number($("boundary-tolerance").value),side:$("boundary-side").value};
  if($("boundary-tolerance").value===""||!valid(b)){$("boundary-error").textContent="Enter a finite nonnegative tolerance; usable trials require an integer.";return;}
  $("boundary-error").textContent="";state.boundary=b;sortOption();preferences.changed();loadList();
 };
 $("boundary-clear").onclick=()=>{clear();preferences.changed();loadList();};
 return {init,valid,structurallyValid,initialized:()=>rule!==null,clear,restore,chip};
})();
function renderDecisiveReview(r){
 const host=$("decisive-review");host.replaceChildren();element("h3","Why this candidate has this status",host);
 element("p",r.review.no_usable_field_data?"No usable field data; AMBER takes precedence over triggered knockout tests.":r.reason,host);
 for(const c of r.review.decisive_assessments){
  const card=element("div","",host,"decisive-criterion");
  const status=r.review.knockout_precedence_applies&&r.review.triggered_knockout_fields.includes(c.field)?"Triggers knockout test":c.status;
  element("p",`${labels[c.field]}: ${formatMetric(c.field,c.value)} ${c.unit}; ${c.test} ${formatMetric(c.field,c.threshold)} ${c.unit}. ${marginDescription(c)}; ${status}.`,card).title=String(c.value??"Unknown");
  uiButton(card,"View evidence",()=>openCriterionEvidence(r,c));
 }
}
