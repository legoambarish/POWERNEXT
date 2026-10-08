from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'ui/app.js';s=p.read_text(encoding='utf-8')
start=s.index('function bindMeasurement(){');end=s.index('\nfunction measurementTemplate()',start)
s=s[:start]+'''function bindMeasurement(){
  const token=renderToken,runId=state.bundle?.run?.run_id,current=()=>token===renderToken&&runId===state.bundle?.run?.run_id;
  document.getElementById('measurement-metadata').addEventListener('change',async event=>{const f=event.target.files[0];if(f){const text=await f.text();if(current())document.getElementById('measurement-json').value=text;}});
  document.getElementById('measurement-csv').addEventListener('change',e=>{const f=e.target.files[0],lab=e.target.closest('.drop');if(f&&lab)lab.querySelector('span').textContent=`${f.name} · ${fmt(f.size/1024,1,1)} kB`;});
  document.getElementById('import-measurement').addEventListener('click',async event=>{
    const button=event.currentTarget,err=document.getElementById('measurement-error');err.innerHTML='';button.disabled=true;
    try{if(!runId)throw new Error('Open a saved engineering request before attaching its acquisition evidence.');
      const file=document.getElementById('measurement-csv').files[0];if(!file)throw new Error('Select a CSV waveform export.');if(file.size>10_000_000)throw new Error('Maximum CSV size is 10 MB.');
      const metadata_text=document.getElementById('measurement-json').value;let metadata;try{metadata=JSON.parse(metadata_text);}catch{throw new Error('Acquisition metadata is not valid JSON.');}
      const bytes=new Uint8Array(await file.arrayBuffer());if(!current())return;let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      const imported=await api(`/api/runs/${runId}/measurements`,{csv_base64:btoa(binary),metadata,metadata_text});if(!current())return;
      const record=await api(`/api/runs/${runId}/measurement/${imported.measurement_id}`);if(!current())return;
      state.measurement={...record,measurement_id:imported.measurement_id};showMeasurement();await savedMeasurements();if(current())toast('Raw waveform, metadata and diagnostics saved.');
    }catch(error){if(current())err.innerHTML=`<div class="note fail">${esc(error.message)}</div>`;}finally{button.disabled=false;}
  });
}'''+s[end:]
start=s.index('async function savedMeasurements(){');end=s.index('\n',start)
s=s[:start]+'''async function savedMeasurements(){if(!state.bundle?.result)return;const token=renderToken,runId=state.bundle.run.run_id,rows=await api(`/api/runs/${runId}/measurements`);if(token!==renderToken||runId!==state.bundle?.run?.run_id)return;const el=document.getElementById('saved-measurements');if(el)el.innerHTML=rows.length?`<section class="card"><div class="card-head"><h3>Archived measurements for this run</h3></div><div class="actions">${rows.map(r=>`<button class="btn sm" data-shot="${esc(r.measurement_id)}">${view.icon('flask',13)} ${esc(r.shot_id)}</button>`).join('')}</div></section>`:'';}'''+s[end:]
old="if(el.dataset.shot){state.measurement=await api(`/api/runs/${state.bundle.run.run_id}/measurement/${el.dataset.shot}`);await showMeasurement();return;}"
new="if(el.dataset.shot){const token=renderToken,rid=state.bundle.run.run_id;const measurement=await api(`/api/runs/${rid}/measurement/${el.dataset.shot}`);if(token!==renderToken||rid!==state.bundle?.run?.run_id)return;state.measurement={...measurement,measurement_id:el.dataset.shot};await showMeasurement();return;}"
assert old in s;s=s.replace(old,new)
p.write_text(s,encoding='utf-8')
p=root/'ui/imports.js';s=p.read_text(encoding='utf-8')
s=s.replace('<p class="note caution">Diagnostics are unqualified. Calibration is not fitted, source identity is not authenticated, and this record is ineligible for model training or operational approval.</p>', '<p class="micro">Unqualified trace diagnostics · no fitted calibration · source declaration retained.</p>${r.measurement_quality?.flags?.length?`<div class="quality-flags"><h4>Acquisition checks</h4><ul>${r.measurement_quality.flags.map(f=>`<li><b>${esc(f.code.replaceAll(\'_\',\' \'))}</b> — ${esc(f.detail)}</li>`).join(\'\')}</ul></div>`:\'\'}')
s=s.replace("const keys=['crest_magnitude_V',fk,'T2_s'];", "const keys=['crest_magnitude_V',fk,'T2_s'];const vScale=Math.abs(d.metrics?.crest_magnitude_V??0)<1000?1:1000,vUnit=vScale===1?'V':'kV';")
s=s.replace("k==='crest_magnitude_V'?1000:1e-6,unit=k==='crest_magnitude_V'?'kV':'µs'","k==='crest_magnitude_V'?vScale:1e-6,unit=k==='crest_magnitude_V'?vUnit:'µs'")
s=s.replace('${fmt(p.voltage_rmse_V,1000)} kV','${fmt(p.voltage_rmse_V,vScale)} ${vUnit}')
p.write_text(s,encoding='utf-8')
