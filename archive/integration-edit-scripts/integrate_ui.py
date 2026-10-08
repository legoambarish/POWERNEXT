"""One-time integration edits with explicit anchors; retained change provenance."""
from pathlib import Path
root=Path(__file__).resolve().parents[1]
def edit(name,pairs):
    if name in ('ui/index.html','ui/discovery.js'):return
    p=root/name;s=p.read_text(encoding='utf-8')
    for old,new in pairs:
        if old not in s:
            if new in s:continue
            raise ValueError(f'Missing edit anchor {name}: {old[:80]}')
        s=s.replace(old,new)
    p.write_text(s,encoding='utf-8')
edit('ui/index.html',[
 ('>Plan test</button>','>Configuration</button>'),('>Results<span','>Recommendations<span'),('>Saved runs</button>','>History</button>'),('>Lab data</button>','>Waveform Review</button>'),
 ('    <button type="button" data-nav="history"','    <button type="button" data-nav="discovery" data-screen="discovery">ML Prediction & Discovery</button>\n    <button type="button" data-nav="history"'),
 ('<span class="b-ic" aria-hidden="true">!</span><span><b>Provisional topology and recipes.</b> A numerical pass is not hardware verification or operational approval. Offline · no hardware control.</span>','<span><b>Offline engineering workbench</b> · CPRI competition waveform profile · declared equivalent circuits</span>'),
 ('>Evidence limits</button>','>Equipment & technical details</button>')])
edit('ui/discovery.js',[('INCLUDED_IN_DECLARED_TOTAL','INCLUDED_IN_OTHER_COMPONENTS')])
edit('ui/views.js',[
 ("export function runFrame(s){","export function runFrame(s){"),
 ("${RUN_TABS.map", "${[...RUN_TABS.filter(x=>x[0]!=='screening'),['adjustment','Next adjustment','arrow']].map"),
 ("Synthetic demo · saved artifact","Saved simulation"),
 ("Synthetic scenarios","Example cases"),("Synthetic demos","Saved simulations"),("Synthetic demo · not timed","Saved simulation · not timed"),
 ("'No approved or evaluable configuration exists. No setting has been invented.'","'No configuration can be selected within this request’s declared inventory and scope.'"),
 ('Approved-only scope currently has zero confirmed CPRI recipes. Development assumptions are not promoted to fill this gap. Confirm the fired circuit and approved recipes with CPRI, then rerun.',"${p.request.catalog_scope==='approved'?'The approved-only catalog is empty because circuit recipes await CPRI confirmation.':'The declared component availability or selected recipe set produces an empty catalog. Review available components and selected arrangements.'}"),
 ("'Waveform timing in this catalogue','No evaluated front/tail resistor combination puts every timing parameter inside its limits.'","'Waveform conformity in this catalogue','No evaluated configuration meets every required crest and timing band together.'"),
 ("r=>r.changes_from_current?.length??0","r=>r.changes_from_current?.filter(x=>x.field!=='stage_charge_V').length??0"),
 ("String(r.changes_from_current.length)","String(r.changes_from_current.filter(x=>x.field!=='stage_charge_V').length)"),
 ("head('Laboratory validation','Measured waveform import'","head('Waveform Review & Evidence','Acquired waveform analysis'"),
 ('<div class="prov-banner">${icon(\'flask\',18)}<div><b>No genuine CPRI measurement is included in this release.</b><span>Calibration is not fitted. Imported traces are drawn in orange and labelled with user-declared provenance; demo and simulated waveforms are never relabelled as measurements.</span></div></div>', '<p class="micro">Raw traces, acquisition metadata and diagnostic comparisons are preserved together. Imported traces are unqualified until independently reviewed.</p>'),
 ('Plan new test','New configuration'),
 ('<option value="SYNTHETIC_DEMO">Saved simulations</option>','<option value="SYNTHETIC_DEMO">Saved simulations</option><option value="REOPENED_EVIDENCE">Reopened evidence</option>'),
 ("r.source==='SYNTHETIC_DEMO'?'Saved simulation · not timed':`Computed locally", "r.source==='SYNTHETIC_DEMO'?'Saved simulation · not timed':r.source==='REOPENED_EVIDENCE'?'Reopened evidence':`Computed locally")])
edit('ui/waveform.js',[
 ("const pad=(hi-lo)*.1||1;","const vScale=Math.max(Math.abs(lo),Math.abs(hi))<1000?1:1000,vUnit=vScale===1?'V':'kV';\n  const pad=(hi-lo)*.1||1;"),
 ('niceTicks(lo/1000,hi/1000,6)','niceTicks(lo/vScale,hi/vScale,6)'),('sy(v*1000)','sy(v*vScale)'),('${fmt(v,1,0)}','${fmt(v,1,3)}'),
 ('${fmt(request.target_crest_V,1000)} kV','${fmt(request.target_crest_V,vScale)} ${vUnit}'),
 ('signed DUT voltage in kV','signed DUT voltage in ${vUnit}'),('Signed DUT voltage (kV)','Signed DUT voltage (${vUnit})'),
 ('${fmt(s.wave.voltage_V[j],1000,3)} kV','${fmt(s.wave.voltage_V[j],vScale,3)} ${vUnit}'),('${fmt(v,1000,3)} kV','${fmt(v,vScale,3)} ${vUnit}')])
edit('ui/app.js',[
 ("const UI_VERSION='0.4.0'","const UI_VERSION='1.0.0'"),
 ("if([...RUN_SCREENS,'plan','history','measured'].includes(action))","if([...RUN_SCREENS,'plan','history','measured','discovery'].includes(action))"),
 ("main.innerHTML=view.historyView(filterHistory(),state.bundle?.run.run_id);bindHistory();return;", "main.innerHTML=view.historyView(filterHistory(),state.bundle?.run.run_id)+'<section class=\"card\"><h3>Reopen a complete evidence bundle</h3><p>Restore the original result, raw traces, metadata and diagnostics from an exported ZIP.</p><input id=\"reopen-file\" type=\"file\" accept=\".zip\" aria-label=\"Evidence ZIP\"><button id=\"reopen-bundle\" class=\"btn\">Reopen evidence</button><div id=\"reopen-error\" role=\"alert\"></div></section>';bindHistory();bindReopen();return;"),
 ("if(state.screen==='screening'){main.innerHTML=frame+'<div id=\"scenario-screen\"></div>';mountScenarioScreen(document.getElementById('scenario-screen'),{row:state.row,request:result.request,api,isCurrent:()=>token===renderToken});return;}","if(state.screen==='screening'){navigate('discovery');return;}"),
 ('Result, request, run metadata, report and every hashed waveform artifact.','Result, request, run metadata, report, every hashed waveform and all imported raw traces, metadata and diagnostics. Reopen this ZIP from History.'),
 ("toast('Raw measured export archived. Calibration remains not fitted.');","toast('Raw waveform, metadata and diagnostics saved.');"),
 ("{csv_base64:btoa(binary),metadata}","{csv_base64:btoa(binary),metadata,metadata_text:document.getElementById('measurement-json').value}"),
 ("showModal('Synthetic scenarios'","showModal('Example cases'"),
 ('the saved synthetic artifact. Nothing was recalculated.','a saved simulation record.')])
