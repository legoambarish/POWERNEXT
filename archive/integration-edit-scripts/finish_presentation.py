from pathlib import Path
root=Path(__file__).resolve().parents[1]
p=root/'ui/app.js';s=p.read_text(encoding='utf-8');start=s.index('function boundaries(){');end=s.index('\n',start)
s=s[:start]+"function boundaries(){showModal('Equipment Profile & Technical Details','Confirmed ratings, declared circuit assumptions and source traceability.',equipmentDetails(state.meta),'',true);}"+s[end:];p.write_text(s,encoding='utf-8')
p=root/'powernext_app/reports.py';s=p.read_text(encoding='utf-8');start=s.index('\ndef _historical_result_only_bundle(');s=s[:start]+'\n'
anchor="    diagnosis=f'<h2>No compliant configuration"
position=s.index(anchor)
s=s[:position]+'''    measured_sections=[]
    for entry in app.measurements(run_id):
        acquired=app.measured_waveform(run_id,entry['measurement_id']);record=acquired['record'];metadata=record['metadata']
        diagnostics=record.get('clean_trace_diagnostics',{});comparison=record.get('predicted_comparison',{})
        metrics=diagnostics.get('metrics',{});voltage_scale=1 if abs(metrics.get('crest_magnitude_V') or 0)<1000 else 1000
        voltage_unit='V' if voltage_scale==1 else 'kV'
        trace_rows=[]
        for name in ['crest_magnitude_V','T1_s' if metadata['configuration']['impulse_type']=='LI' else 'Tp_s','T2_s']:
            scale=voltage_scale if name=='crest_magnitude_V' else 1e-6;unit=voltage_unit if name=='crest_magnitude_V' else 'µs'
            trace_rows.append('<tr>'+''.join('<td>'+h(x)+'</td>' for x in [name.replace('_s','')+' ('+unit+')',number(metrics.get(name),scale),number(comparison.get('metrics',{}).get(name),scale)])+'</tr>')
        measured_sections.append('<h3>'+h(metadata['shot_id'])+'</h3><p>'+h(record['evidence_domain'])+' · Unqualified trace diagnostics</p><table><tr><th>Parameter</th><th>Trace diagnostic</th><th>Declared-setting Physics</th></tr>'+''.join(trace_rows)+'</table><pre>'+h(json.dumps(dict(actual_configuration=metadata['configuration'],actual_setup=metadata['setup'],measurement_chain=metadata['measurement'],quality=record.get('measurement_quality'),raw_sha256=record['raw_sha256'],metadata_sha256=record['metadata_sha256']),indent=2))+'</pre>')
    measured_html='<h2>Acquired waveform evidence</h2>'+(''.join(measured_sections) if measured_sections else '<p>No acquired waveforms attached.</p>')+'<p>The complete evidence ZIP includes original raw files and metadata, converted arrays, diagnostics and saved model comparisons. Imported records are not automatically used for model training or ranking.</p>'
''' + s[position:]
s=s.replace('{decision}{diagnosis}{plot}{compare}<h2>', '{decision}{diagnosis}{plot}{compare}{measured_html}<h2>')
s=s.replace('This development report is not an official CPRI test certificate','This engineering report is not an official CPRI test certificate')
p.write_text(s,encoding='utf-8')
p=root/'tests/application/ui_redesign.test.mjs';s=p.read_text();s=s.replace("assert.ok(html.includes('Calibration is not fitted'));","assert.ok(html.includes('Clean-trace diagnostics') || html.includes('Raw traces'));");p.write_text(s)
