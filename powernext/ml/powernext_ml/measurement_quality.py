"""Observable acquisition checks; no single-trace physical fault attribution."""
import numpy as np

def inspect_trace(t,v,meta):
    m=meta['measurement'];c=meta['configuration'];y=(v-m['baseline_V'])*m['polarity'];peak=float(np.max(y));flags=[]
    def flag(code,detail):flags.append(dict(code=code,detail=detail))
    if 'polarity' in c and c['polarity']!=m['polarity']:flag('POLARITY_METADATA_CONFLICT','Actual configuration and measurement polarity disagree; model overlay is withheld.')
    if peak<=0 or abs(float(np.min(y)))>max(peak,0)*1.05:flag('DECLARED_POLARITY_INCONSISTENT','Dominant excursion opposes the declared polarity. Check polarity and baseline, not a presumed physical cause.')
    if not t[0]<=m['beginning_s']<t[-1]:flag('BEGINNING_OUTSIDE_RECORD','Declared beginning lies outside the captured record.')
    if peak>0:
        idx=int(np.argmax(y));plateau=int(np.sum(np.isclose(y,peak,rtol=0,atol=max(peak*1e-10,1e-12))))
        if plateau>=3:flag('POSSIBLE_CLIPPING_OR_FLAT_PEAK','Repeated maximum samples may indicate clipping or a plateau; digitizer range is needed to distinguish them.')
        if y[-1]>.5*peak:flag('TAIL_NOT_CAPTURED','Record ends above half crest; extend the acquisition window.')
        if y[0]>.03*peak:flag('PRETRIGGER_OR_BASELINE_REVIEW','Record starts above 3% crest under the declared baseline; beginning/front may be incomplete.')
        front_samples=int(np.sum((y[:idx]>=.3*peak)&(y[:idx]<=.9*peak)))
        if front_samples<5:flag('SPARSE_FRONT_SAMPLING','Fewer than five samples between 30% and 90%; extracted timing needs acquisition review.')
        if idx==0 or idx==len(y)-1:flag('PEAK_AT_RECORD_BOUNDARY','Peak may be outside the recording interval.')
        steps=np.abs(np.diff(y));large=steps>peak*.25
        if large.any():flag('ABRUPT_STEP_OR_COARSE_SAMPLING','A sample step exceeds 25% crest; possible chopping, truncation or inadequate sampling. No cause inferred.')
    pre=y[t<m['beginning_s']]
    if len(pre)>=8 and peak>0 and np.std(pre)>peak*.005:flag('PRETRIGGER_NOISE_OR_BASELINE','Pretrigger RMS variation exceeds 0.5% crest under the declared beginning.')
    header=(m['time_column']+' '+m['voltage_column']).lower()
    for unit,declared in [('ns',m['time_unit']),('us',m['time_unit']),('kv',m['voltage_unit'].lower())]:
        if '('+unit+')' in header or '['+unit+']' in header:
            if unit!=declared.lower():flag('HEADER_UNIT_CONFLICT','Column header unit conflicts with declared unit; data is retained without guessing a correction.')
    return dict(status='REVIEW_REQUIRED' if flags else 'NO_SIMPLE_ACQUISITION_FLAGS',flags=flags,sample_count=len(t),
                sampling_interval_min_s=float(np.min(np.diff(t))),sampling_interval_max_s=float(np.max(np.diff(t))),
                qualified_measurement=False,root_cause_inferred=False,
                unit_policy='Explicit units and divider factor only. Plausibility cannot establish correct units.',
                next_action='Review flags with the raw trace, digitizer range, timebase, divider ratio and actual setting. Preserve the original export.')
