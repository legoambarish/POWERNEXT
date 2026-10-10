# Phase B bounded resistor networks

`powernext_v3.networks` is the bounded physical network catalogue used by the
Phase B extension.  It is isolated from the legacy `powernext/physics` source
so historical hashes and numerical fixtures remain unchanged.

Each leaf is one confirmed discrete component: `30`, `46`, `180`, `520`,
`3700`, or `5000` ohm.  A network is a two-terminal series (`S`) or parallel
(`P`) tree.  `canonicalize(tree)` flattens nested equal operations and sorts
children, making associatively or commutatively equivalent trees identical.
`equivalent_resistance(tree)` returns an exact `fractions.Fraction`.

`enumerate_networks(max_modules=4)` returns frozen `NetworkRecipe` records in a
stable order.  It retains every canonical physical tree even when another
tree has the same equivalent resistance.  Cumulative catalogue counts are:

| module bound | recipes | exact-equivalent groups |
| ---: | ---: | ---: |
| 1 | 6 | 6 |
| 2 | 48 | 48 |
| 3 | 412 | 407 |
| 4 | 4192 | 4080 |

`electrical_groups()` groups records by exact Fraction keys.  `combined_bom`
multiplies the component leaves in the front and tail trees by the uniform
stage count and returns deterministic rows.  With no inventory argument,
`available_count` and `shortfall` remain `None` and `availability_status` is
`UNKNOWN`; the function does not assume stock.  A supplied mapping gives
known counts for listed components, and `None` can preserve unknown stock for a
listed value.

`stress_division` (also exported as `per_element_stress`) accepts terminal
voltage or current and reports the voltage, current, power, and path of every
physical resistor leaf.  These are ideal network-sharing values and do not
establish component pulse, insulation, thermal, or mounting ratings.
