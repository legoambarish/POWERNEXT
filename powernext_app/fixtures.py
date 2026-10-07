"""Current synthetic examples; focus IDs select an existing saved candidate."""
DEMOS=[
    dict(id='si',request='SI_request.json',result='SI_recommendation.json',title='A compliant switching impulse',label='SI · 1.3 MV',story='Fourteen numerical passes. Inspect why nine stages win.',tag='START HERE'),
    dict(id='li',request='LI_parallel_request.json',result='LI_parallel_recommendation.json',title='LI with an explicit circuit hypothesis',label='LI · 1.55 MV',story='Three conditional passes with a 180 || 520 ohm tail. Wiring remains unconfirmed.',tag='HYPOTHESIS'),
    dict(id='li_single',request='LI_request.json',result='LI_recommendation.json',title='The single-resistor LI limitation',label='LI · 1.55 MV',story='Same fixed load and tolerances. None of the 504 single-resistor settings comply.',tag='NO SOLUTION'),
    dict(id='li_disagreement',request='LI_disagreement_request.json',result='LI_disagreement_recommendation.json',title='Physics rejects an ML false acceptance',label='LI · marginal crest',story='Inspect rank 8: ML scalar estimates pass, but physics rejects the crest. No ML pruning.',tag='EVIDENCE',focus_candidate_id='cfg_3754ce6cb55b96c7'),
    dict(id='crest',request='SI_crest_change.json',result='SI_crest_change_recommendation.json',title='Raise only the requested crest',label='SI · 1.8 MV',story='The preferred stage count moves from nine to eleven.',tag='COMPARE'),
    dict(id='load',request='SI_load_change.json',result='SI_load_change_recommendation.json',title='Change the test object',label='SI · 1.8 nF DUT',story='A larger load changes the preferred setting to eight stages.',tag='COMPARE'),
    dict(id='ood',request='SI_ood.json',result='SI_ood_recommendation.json',title='Outside learned support',label='SI · 50 nF DUT',story='Physics fallback for every candidate. No forced ML estimate.',tag='FALLBACK'),
    dict(id='band',request='SI_tolerance_band.json',result='SI_tolerance_band_recommendation.json',title='Charge limits with alternatives',label='SI · charge limit',story='Rank 2 passes at 200 kV per stage. The expanded catalog also finds an exact-crest leader.',tag='BOUNDARY',focus_candidate_id='cfg_1ef05d2a542a16f6'),
    dict(id='infeasible',request='SI_infeasible.json',result='SI_infeasible_recommendation.json',title='A defensible infeasible result',label='SI · 2.4 MV / 50 nF',story='Voltage and timing limits remain visible alongside the closest case.',tag='NO SOLUTION'),
    dict(id='approved',request='SI_approved_only.json',result='SI_approved_only_recommendation.json',title='Require approved recipes',label='No approved recipes',story='Missing confirmation is an information gap, not a fabricated setting.',tag='HARDWARE'),
    dict(id='output_shunt',request='SI_output_shunt.json',result='SI_output_shunt_recommendation.json',title='A different declared topology',label='SI · output shunt',story='The topology is a fixed request condition, never a hidden search variable.',tag='EXPERT'),
    dict(id='low',request='SI_low_voltage.json',result='SI_low_voltage_recommendation.json',title='Low voltage needs a practical check',label='SI · 50 kV',story='Numerical pass at about 8.103 kV per stage. Reliable firing minimum is unknown.',tag='BOUNDARY'),
]

def demo(identifier):
    return next((d for d in DEMOS if d['id']==identifier),None)
