# Current circuit recipes: October 4, 2026

Classification: PROVISIONAL MODEL ASSUMPTION. No recipe is hardware approved.

The component inventory contains 30, 46, 180, 520, 3700 and 5000 ohm. The newest CPRI reply confirms these values and permits appropriate front/tail use, but supplies no fired schematic, quantities, sockets, or ratings.

## Single component recipe: DEV_UNIFORM_SINGLE_v2

For N identical active stages, Cs=0.5 microfarad, equal charge q, Cg=Cs/N and U0=polarity*N*q. Front resistance is N*rf plus declared loop resistance. Tail resistance is N*rt. Each physical component is an inventory value. Two explicitly selected shunt locations are supported: GSHUNT_v0 at the generator node and OSHUNT_v0 at the output node. The optimizer never chooses the shunt location automatically. Both remain provisional. One front and one tail component are required per active stage; coincident values require twice the component quantity.

## Optional LI hypothesis: HYP_LI_TAIL_180_PAR_520_v1

GSHUNT LI only. A local 180 ohm branch and a separate local 520 ohm branch are connected in parallel across each charged stage capacitor. Uniform interleaved front resistors and ideal simultaneous firing are assumed. Each tail stack reduces to N*180 and N*520 ohm respectively; the graph stamps both branches separately. Their equivalent resistance is N*(180*520/(180+520)), or N*133.714285714 ohm. This equivalent is never an inventory part.

The full-stage proof fixture independently stamps both branches at every stage. With no internal ground capacitance, uniform charge and identical elements, its output matches the reduced graph. This establishes equivalence of the stated mathematical circuits, not equivalence to the real CPRI generator. Ground strays, unequal firing, nonuniform allocations and auxiliary branches can break it.

Required parts: N front parts, N 180 ohm tail parts and N 520 ohm tail parts, summed by value if front overlaps. Counts, available slots, voltage rating, pulse energy, mechanical clearances and thermal duty remain unknown. Per-component voltage/current/energy numbers are ideal uniform-sharing proxies. They must not be used as rating approval.

This bounded hypothesis is motivated by the two originally specified LI tail values and physically meaningful resistor branches; generic manufacturer literature describes multiple resistor positions. Neither source establishes that this arrangement is actually installed or approved at CPRI. The recipe is off by default and requires explicit selection. No arbitrary series/parallel synthesis is performed. A 180+520 series tail is assessed only as a negative diagnostic.

## Invariants and exclusions

Stage count 2..15; maximum charge 200 kV/stage; rated energy limits unchanged. DUT/divider/stray capacitance and loop inductance are fixed request inputs, never optimized to obtain a pass. The 480 pF coverage choice must be explicit. Potential/charging/discharge branches remain omitted under a recorded development assumption. Minimum reliable charge and charge step are unknown. The existing shared waveform evaluator and competition bands remain unchanged.

## Numerical implementation

The graph kernel uses energy-scaled states, passivity checks, exact zero-L RC reduction and Radau reference integration. A guarded eigensystem trajectory evaluates the same fixed linear ODE for batch work. Ill-conditioned modal bases fall back to Radau. Independent tests use a scalar RC characteristic equation, scipy matrix exponential, dimensional LSODA equations and full stage graphs. Stationary roots are bracketed against the scalar function to avoid zero-current cancellation artifacts.

The mathematical nominal target solves the double-exponential rates against the shared LI virtual-origin or SI time-to-peak definitions and is re-evaluated before display. It is explicitly a reference target, not another hardware simulation.

Historical DEV_UNIFORM_SERIES_v1 is retained only for explicit replay with its original restricted domain. It is excluded from the current optimizer catalog. Old numerical evidence retains its old profile and is never relabelled.
