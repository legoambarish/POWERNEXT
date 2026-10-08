"""Offline report rendering; every plotted sample comes from the saved curve."""
from html import escape
import io,base64,json,zipfile,threading
from .common import read_json,safe_child,file_hash

_PLOT_LOCK=threading.Lock()

def figure_png(wave,request):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib.figure import Figure
    with _PLOT_LOCK:
        fig=Figure(figsize=(9,3.5),dpi=140);ax=fig.subplots()
        m=wave['metrics'];polarity=request['polarity']
        ax.plot([t*1e6 for t in wave['time_s']],[v/1000 for v in wave['voltage_V']],color='#245ae3',linewidth=1.7,label='Saved physics reference')
        if wave.get('target'):
            target=wave['target'];ax.plot([t*1e6 for t in target['time_s']],[v/1000 for v in target['voltage_V']],color='#63758b',linestyle='--',linewidth=1.2,label='Mathematical nominal target')
        ax.set(xlabel='Time (µs)',ylabel='Signed DUT voltage (kV)')
        center=polarity*request['target_crest_V']/1000
        # Target bounds are taken from the saved candidate score by caller.
        if request.get('_crest_bounds'):
            bounds=sorted([polarity*v/1000 for v in request['_crest_bounds']]);ax.axhspan(*bounds,color='#6e91c8',alpha=.14,label='Allowed crest band')
        if m.get('T2_s'):ax.set_xlim(min(0,m.get('virtual_origin_s') or 0)*1e6,m['t50_falling_s']*1e6*1.4)
        names=[('t30_s','30%'),('t90_s','90%'),('virtual_origin_s','Virtual origin'),('t50_falling_s','Falling 50%')] if request['impulse_type']=='LI' else [('beginning_s','Beginning'),('t_peak_s','Peak / Tp'),('t50_falling_s','Falling 50%')]
        for key,label in names:
            if m.get(key) is not None:ax.axvline(m[key]*1e6,color='#8b99ab',lw=.65,ls='--')
        ax.grid(alpha=.16);ax.legend(frameon=False,fontsize=8,loc='upper right');fig.tight_layout()
        stream=io.BytesIO();fig.savefig(stream,format='png');return stream.getvalue()

def html_report(app,run_id):
    bundle=app.get_run(run_id);p=bundle['result'];meta=bundle['run']
    if p is None:raise ValueError('Wait for the run to complete')
    selected=p.get('best_configuration') or p.get('closest_noncompliant')
    def h(x):return escape(str(x))
    def number(v,scale=1):return 'Unavailable' if v is None else f'{v/scale:,.6g}'
    def tail(row):return ' || '.join(str(x) for x in row.get('tail_recipe',{}).get('component_values_ohm',[row['configuration']['tail_per_stage_ohm']]))
    request=p.get('request',meta['request']);front='T1_s' if request['impulse_type']=='LI' else 'Tp_s'
    rows=[]
    for c in p.get('candidates',[])[:5]:
        config=c['configuration'];m=(c.get('prediction') or {}).get('physics_reference',{}).get('metrics',{})
        rows.append('<tr>'+''.join(f'<td>{h(x)}</td>' for x in [c['rank'],config['stages'],number(config['stage_charge_V'],1000),config['front_per_stage_ohm'],tail(c),number(m.get('crest_magnitude_V'),1000),number(m.get(front),1e-6),number(m.get('T2_s'),1e-6),c['assessment']['compliance_status'],number(c['score']['J']) if c.get('score') else 'Not scored'])+'</tr>')
    plot='';compare='';decision='No selected evaluable configuration.'
    if selected:
        c=selected['configuration'];m=selected['prediction']['physics_reference']['metrics']
        wave=app.waveform(run_id,selected['candidate_id']);req=dict(request)
        if selected.get('score'):req['_crest_bounds']=selected['score']['components']['crest']['limits']
        plot='<img alt="Saved authoritative reference waveform with timing markers" src="data:image/png;base64,'+base64.b64encode(figure_png(wave,req)).decode()+'">'
        label='Numerically recommended configuration' if p.get('best_configuration') else 'Closest noncompliant configuration — not a recommendation'
        decision=f'<h2>{label}</h2><p><b>{c["stages"]} active stages · {number(c["stage_charge_V"],1000)} kV/stage</b><br>Front {h(c["front_per_stage_ohm"])} Ω/stage · Tail {h(tail(selected))} Ω/stage<br>{h(c["recipe_id"])} · {h(selected["recipe_status"])}<br>{h(selected["ranking_reason"])}</p>'
        decision+='<h3>Required components under the hypothesis</h3><pre>'+h(json.dumps(selected.get('component_bill_of_materials'),indent=2))+'</pre><p>Available quantities, placement and pulse ratings are unconfirmed. Equivalent resistance is derived, not an inventory component. The dashed target is a mathematical reference with the same LI/SI timing definitions, not an equipment prediction.</p>'
        evidence=app.evidence(run_id,selected['candidate_id']);baseline=evidence['baseline'];ml=selected['prediction'].get('ml_prediction')
        cells=[]
        for label,value,key,scale in [('Crest (kV)',m['crest_magnitude_V'],'crest_V',1000),(front.replace('_s','')+' (µs)',m.get(front),'front_s',1e-6),('T2 (µs)',m.get('T2_s'),'T2_s',1e-6)]:
            mlkey=front if key=='front_s' else key
            cells.append(f'<tr><th>{label}</th><td>{number(baseline.get(key) if baseline else None,scale)}</td><td>{number(ml.get(mlkey) if ml else None,scale)}</td><td>{number(value,scale)}</td></tr>')
        compare='<h2>Physics + trained ML</h2><table><tr><th>Parameter</th><th>RC baseline (L=0)</th><th>ML estimate</th><th>Checked reference</th></tr>'+''.join(cells)+'</table><p>Final numerical compliance uses the saved reference waveform. ML scalars are separate estimates. Model: '+h(selected['prediction'].get('model_id','Unavailable / fallback'))+'</p>'
    measured_sections=[]
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
    diagnosis=f'<h2>No compliant configuration</h2><pre>{h(json.dumps(p["no_solution"],indent=2))}</pre>' if p.get('no_solution') else ''
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>PowerNext engineering recommendation</title><style>body{{font:14px/1.55 system-ui,sans-serif;color:#163149;max-width:1080px;margin:32px auto;padding:0 24px}}h1{{font-size:27px}}h2{{font-size:19px;margin-top:28px}}.notice{{background:#fff5da;border-left:4px solid #b88519;padding:14px}}table{{border-collapse:collapse;width:100%;font-size:12px}}th,td{{padding:9px;text-align:left;border-bottom:1px solid #dce3eb}}pre{{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.5 monospace;background:#f4f6f8;padding:12px}}img{{width:100%}}@media print{{body{{margin:0;max-width:none}}h2{{break-after:avoid}}table,img{{break-inside:avoid}}}}</style><header><small>POWERNEXT / TRACK 1 / ENGINEERING RECORD</small><h1>{h(request['impulse_type'])} · {number(request['target_crest_V'],1000)} kV test</h1><p>{h(meta['created_at'])} · {h(meta['source'])} · {h(run_id)}</p></header><div class="notice"><b>Provisional recipe · Operational approval not established</b><br>Numerical status: {h(p['status'])}. This engineering report is not an official CPRI test certificate, laboratory validation or IEC certification.</div>{decision}{diagnosis}{plot}{compare}{measured_html}<h2>Ranked shortlist</h2><table><tr><th>Rank</th><th>Stages</th><th>kV/stage</th><th>Front Ω</th><th>Tail Ω</th><th>Crest kV</th><th>{front.replace('_s','')} µs</th><th>T2 µs</th><th>Numerical</th><th>J</th></tr>{''.join(rows)}</table><h2>Request and value provenance</h2><pre>{h(json.dumps(dict(request=request,annotations=meta.get('annotations',{})),indent=2))}</pre><h2>Assumptions, warnings and constraints</h2><pre>{h(json.dumps(dict(assumptions=selected.get('assumptions',[]) if selected else [],warnings=selected.get('warnings',[]) if selected else [],reason_codes=selected.get('reason_codes',[]) if selected else p.get('reason_codes'),hard_constraints=selected.get('hard_constraints') if selected else None),indent=2))}</pre><h2>Traceable versions</h2><pre>{h(json.dumps(dict(optimizer=p.get('optimizer_version'),result_id=p.get('result_id'),stack_sha256=p.get('stack_sha256'),physics=p.get('provenance',{}).get('physics'),models=p.get('provenance',{}).get('model_selection'),compatibility=bundle['artifact_compatibility']),indent=2))}</pre></html>'''

def bundle_zip(app,run_id):
    from .evidence import build_bundle
    return build_bundle(app,run_id,html_report(app,run_id))

