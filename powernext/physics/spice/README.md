# Historical fixed-circuit SPICE illustrations — not executed

These four unchanged decks describe the historical fixed N=10, 150 kV/stage single-tail examples named in each deck. They are retained as optional circuit illustrations, not current recommendations or independent acceptance evidence. The current examples folder contains different configurations; do not compare them without matching all input values. The decks do not include the optional parallel-tail hypothesis.

They were **not executed** in this revalidation environment; ngspice was unavailable. No SPICE installation is needed for the application. If separately running `ngspice -b LI_GSHUNT_v0.cir`, first regenerate a reference with exactly the deck's component values and initial state. The control block writes voltage/current traces. Compare on common times containing the full evaluated tail. Current independent numerical checks instead used Radau, LSODA, matrix exponential and full-stage graphs, as documented in the phase reports.

Use charged-capacitor initial conditions, not an ideal imposed voltage pulse. Check raw trace headers and polarity/current sign. Halve the maximum step and tighten tolerance, compare again, and document convergence. Repeat for both tail placements. A converged SPICE agreement verifies the same assumed circuit, not the actual CPRI wiring.
