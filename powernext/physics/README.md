# Current physics package

Profile CPRI_IVG_OCT04_2026_v2; simulator 0.2.0. Six actual component values: 30, 46, 180, 520, 3700 and 5000 ohm. Connectivity remains provisional. See CIRCUIT_TOPOLOGY_SPEC.md (frozen with the training data), CPRI_EQUIPMENT_PROFILE.json and physics_engine/recipes.py.

DEV_UNIFORM_SINGLE_v2 uses equal stage charge, Cg=0.5 microfarad/N, front=N*rf and tail=N*rt with one actual component in each role per active stage. GSHUNT puts the tail across erected generator capacitance; OSHUNT puts it at the output. Both are documented reduced models, not identified CPRI fired schematics. All 6x6 choices over N=2..15 give 504 configurations per requested topology and mode.

HYP_LI_TAIL_180_PAR_520_v1 is an explicit LI/GSHUNT hypothesis, never a default. Each stage has separate 180 and 520 ohm tail branches. The derived equivalent is 133.7142857 ohm/stage. This adds 84 configurations. CPRI has confirmed the parts but not this connection, quantities, slots or pulse ratings. DEV_UNIFORM_SERIES_v1 survives in source only for explicitly historical reproduction and is outside the current request schema/optimizer.

The passive RLC equations, charge and energy checks are unchanged in meaning. A guarded modal solver has independent Radau and full-stage comparisons. LI uses virtual-origin 1.2/50 microseconds, front +/-30%, tail +/-20%, crest +/-3%. Competition SI uses Tp 250/2500 microseconds, Tp +/-20%, tail +/-60%, crest +/-3%; this does not claim the IEC 60060-1:2025 standard-SI definition. Mathematical targets use the same evaluator. Measured/noisy/overshooting waveforms are not standards-qualified.

Examples are current simulations and contain their own metrics; none is a laboratory observation. Historical copies are preserved in the integration audit folder, outside active runtime. Run the complete release tests from the root. REQUEST_SCHEMA.json describes current inputs; runtime physics validation remains authoritative.
