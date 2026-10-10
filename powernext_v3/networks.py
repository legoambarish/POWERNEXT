"""Bounded, canonical series/parallel resistor network synthesis.

This module is deliberately separate from the legacy physics engine.  It
describes physical resistor arrangements only; it does not decide whether a
particular arrangement is approved for a generator.  A resistor leaf is an
actual inventory value and every generated network keeps its tree, even when
another tree has the same exact equivalent resistance.

The public tree format is JSON friendly::

    {"op": "R", "ohm": 180}
    {"op": "P", "children": [{"op": "R", "ohm": 180}, ...]}

``S`` and ``P`` nodes are associative and commutative.  Canonicalization
therefore flattens nested nodes with the same operation and sorts children.
The bounded catalogue contains at most four resistor leaves per network.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from fractions import Fraction
from functools import lru_cache
import math
from numbers import Integral, Real
from typing import Any, TypeAlias


COMPONENTS: tuple[int, ...] = (30, 46, 180, 520, 3700, 5000)
"""Confirmed discrete resistor values admitted by this bounded catalogue."""

COMPONENT_VALUES = COMPONENTS
MAX_MODULES = 4


class NetworkValidationError(ValueError):
    """Raised when a network, bound, or inventory is outside the contract."""


# A frozen tree is ``("R", ohm)`` for leaves and ``("S"/"P", children)``
# for composite nodes.  It is kept private so callers always interact with
# the JSON-friendly form while recipe records remain deeply immutable.
_FrozenNode: TypeAlias = tuple[Any, ...]


def _invalid(message: str) -> NetworkValidationError:
    return NetworkValidationError(message)


def _component_value(value: Any, *, where: str = "resistor") -> int:
    """Validate one actual inventory component and return its integer value.

    JSON decoders commonly produce ``30.0`` for a numeric component even
    though the physical value is integral, so integral finite real numbers are
    accepted.  Booleans are rejected explicitly because ``True == 1`` would
    otherwise pass a loose numeric check.
    """

    if isinstance(value, bool) or not isinstance(value, Real):
        raise _invalid(f"{where} must be one of {COMPONENTS}; got {value!r}.")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise _invalid(f"{where} must be finite and numeric; got {value!r}.") from exc
    if not math.isfinite(number):
        raise _invalid(f"{where} must be finite; got {value!r}.")
    if not number.is_integer():
        raise _invalid(f"{where} must be an integral confirmed component; got {value!r}.")
    integer = int(number)
    if integer not in COMPONENTS:
        raise _invalid(f"{where} {integer} is not a confirmed component; use one of {COMPONENTS}.")
    return integer


def _sort_key(node: _FrozenNode) -> tuple[Any, ...]:
    """A total, deterministic ordering for canonical children."""

    if node[0] == "R":
        return (0, node[1])
    op = 0 if node[0] == "S" else 1
    return (1, op, tuple(_sort_key(child) for child in node[1]))


def _canonical_node(op: str, children: Sequence[_FrozenNode]) -> _FrozenNode:
    """Flatten and sort one composite node."""

    flattened: list[_FrozenNode] = []
    for child in children:
        if child[0] == op:
            flattened.extend(child[1])
        else:
            flattened.append(child)
    if len(flattened) < 2:
        raise _invalid(f"{op} nodes require at least two children.")
    flattened.sort(key=_sort_key)
    return (op, tuple(flattened))


def _parse_tree(node: Any, active: set[int] | None = None) -> tuple[_FrozenNode, int]:
    """Parse, validate, and canonicalize a caller-supplied tree."""

    if isinstance(node, NetworkRecipe):
        # Recipes are built by this module and carry a validated frozen tree.
        count = node.module_count
        if count > MAX_MODULES:
            raise _invalid(f"a network may contain at most {MAX_MODULES} modules; got {count}.")
        return node._node, count

    if not isinstance(node, Mapping):
        raise _invalid("a network tree must be a mapping with op/ohm or op/children fields.")

    active = set() if active is None else active
    identity = id(node)
    if identity in active:
        raise _invalid("network tree contains a cycle.")
    active.add(identity)
    try:
        if "op" not in node:
            raise _invalid("network node is missing its op field.")
        op = node["op"]
        if not isinstance(op, str) or op not in {"R", "S", "P"}:
            raise _invalid(f"network op must be 'R', 'S', or 'P'; got {op!r}.")

        expected = {"op", "ohm"} if op == "R" else {"op", "children"}
        if set(node.keys()) != expected:
            raise _invalid(
                f"{op} nodes must contain exactly {sorted(expected)!r}; got {tuple(node.keys())!r}."
            )

        if op == "R":
            return ("R", _component_value(node["ohm"])), 1

        children = node["children"]
        if isinstance(children, (str, bytes, bytearray)) or not isinstance(children, Sequence):
            raise _invalid(f"{op}.children must be a list or tuple of child trees.")
        if len(children) < 2:
            raise _invalid(f"{op}.children must contain at least two child trees.")

        parsed: list[_FrozenNode] = []
        module_count = 0
        for child in children:
            frozen, count = _parse_tree(child, active)
            module_count += count
            if module_count > MAX_MODULES:
                raise _invalid(f"a network may contain at most {MAX_MODULES} modules; got more.")
            parsed.append(frozen)
        return _canonical_node(op, parsed), module_count
    finally:
        active.remove(identity)


def _node_from(tree: Any) -> _FrozenNode:
    node, count = _parse_tree(tree)
    if count < 1 or count > MAX_MODULES:
        raise _invalid(f"a network must contain between 1 and {MAX_MODULES} modules; got {count}.")
    return node


def _thaw(node: _FrozenNode) -> dict[str, Any]:
    """Return a fresh JSON-friendly copy of a frozen node."""

    if node[0] == "R":
        return {"op": "R", "ohm": node[1]}
    return {"op": node[0], "children": [_thaw(child) for child in node[1]]}


def _tree_id(node: _FrozenNode) -> str:
    if node[0] == "R":
        return f"R{node[1]}"
    return f"{node[0]}({','.join(_tree_id(child) for child in node[1])})"


def _module_values(node: _FrozenNode) -> tuple[int, ...]:
    if node[0] == "R":
        return (node[1],)
    values: list[int] = []
    for child in node[1]:
        values.extend(_module_values(child))
    return tuple(sorted(values))


def _equivalent_node(node: _FrozenNode) -> Fraction:
    if node[0] == "R":
        return Fraction(node[1], 1)
    values = tuple(_equivalent_node(child) for child in node[1])
    if node[0] == "S":
        return sum(values, Fraction(0, 1))
    reciprocal_sum = sum((Fraction(1, value) for value in values), Fraction(0, 1))
    return Fraction(1, 1) / reciprocal_sum


@dataclass(frozen=True, slots=True)
class NetworkRecipe:
    """One physical series/parallel arrangement.

    ``_node`` is private and deeply immutable.  The ``tree`` property returns
    a fresh JSON-friendly copy, so a caller can edit that copy without
    changing this record or any cached catalogue entry.
    """

    id: str
    _node: _FrozenNode = field(repr=False)
    module_count: int = 0
    equivalent_ohm: Fraction = Fraction(0, 1)
    components: tuple[int, ...] = ()

    @property
    def tree(self) -> dict[str, Any]:
        return _thaw(self._node)

    @property
    def canonical_tree(self) -> dict[str, Any]:
        return self.tree

    @property
    def recipe_id(self) -> str:
        return self.id

    @property
    def equivalent_resistance(self) -> Fraction:
        return self.equivalent_ohm

    @property
    def resistance_ohm(self) -> Fraction:
        return self.equivalent_ohm

    @property
    def module_values(self) -> tuple[int, ...]:
        return self.components

    @property
    def component_counts(self) -> dict[int, int]:
        """Return a fresh value-to-count mapping for one network."""

        return dict(Counter(self.components))

    @property
    def component_values(self) -> tuple[int, ...]:
        return self.components

    def as_dict(self) -> dict[str, Any]:
        """Serialize metadata while retaining exact resistance as a string."""

        return {
            "id": self.id,
            "tree": self.tree,
            "module_count": self.module_count,
            "components": list(self.components),
            "equivalent_ohm": str(self.equivalent_ohm),
        }

    def __getitem__(self, key: str) -> Any:
        """Small mapping convenience for integration code consuming records."""

        if key == "tree":
            return self.tree
        if key in {"equivalent", "equivalent_ohm", "equivalent_resistance"}:
            return self.equivalent_ohm
        if key in {"modules", "module_count"}:
            return self.module_count
        if key in {"id", "recipe_id"}:
            return self.id
        if key in {"components", "module_values", "component_values"}:
            return self.components
        if key == "component_counts":
            return self.component_counts
        raise KeyError(key)


def _recipe(node: _FrozenNode) -> NetworkRecipe:
    values = _module_values(node)
    return NetworkRecipe(
        id=_tree_id(node),
        _node=node,
        module_count=len(values),
        equivalent_ohm=_equivalent_node(node),
        components=values,
    )


@lru_cache(maxsize=None)
def _nodes_exact(module_count: int) -> tuple[_FrozenNode, ...]:
    """Generate every canonical tree with exactly ``module_count`` leaves."""

    if module_count == 1:
        return tuple(("R", value) for value in COMPONENTS)

    candidates: set[_FrozenNode] = set()
    for left_count in range(1, module_count):
        right_count = module_count - left_count
        for left in _nodes_exact(left_count):
            for right in _nodes_exact(right_count):
                for op in ("S", "P"):
                    candidates.add(_canonical_node(op, (left, right)))
    return tuple(sorted(candidates, key=_sort_key))


def _validate_max_modules(max_modules: Any) -> int:
    if isinstance(max_modules, bool) or not isinstance(max_modules, Integral):
        raise _invalid(f"max_modules must be an integer from 1 to {MAX_MODULES}.")
    value = int(max_modules)
    if value < 1 or value > MAX_MODULES:
        raise _invalid(f"max_modules must be from 1 to {MAX_MODULES}; got {value}.")
    return value


@lru_cache(maxsize=None)
def _recipes_up_to(max_modules: int) -> tuple[NetworkRecipe, ...]:
    return tuple(_recipe(node) for count in range(1, max_modules + 1) for node in _nodes_exact(count))


def canonicalize(tree: Any) -> dict[str, Any]:
    """Return the associative/commutative canonical form of ``tree``.

    The result is a fresh ordinary dictionary with child lists so it can be
    passed directly to ``json.dumps`` or a downstream API.  Every input is
    validated against the six confirmed components and the four-module bound.
    """

    return _thaw(_node_from(tree))


def equivalent_resistance(tree: Any) -> Fraction:
    """Compute exact equivalent resistance as a :class:`fractions.Fraction`."""

    return _equivalent_node(_node_from(tree))


def enumerate_networks(max_modules: int = MAX_MODULES) -> tuple[NetworkRecipe, ...]:
    """Enumerate all canonical physical recipes up to ``max_modules`` leaves.

    The result is ordered by module count and then a deterministic structural
    order.  Physical alternatives are retained even when their exact
    equivalent resistance is equal.
    """

    return _recipes_up_to(_validate_max_modules(max_modules))


def electrical_groups(max_modules: int = MAX_MODULES) -> dict[Fraction, tuple[NetworkRecipe, ...]]:
    """Group canonical recipes by exact equivalent resistance.

    Dictionary insertion order is deterministic: Fraction keys are ascending
    and each tuple retains catalogue order.  A group can contain physically
    different trees; callers must not replace a group with one representative.
    """

    recipes = enumerate_networks(max_modules)
    grouped: dict[Fraction, list[NetworkRecipe]] = {}
    for recipe in recipes:
        grouped.setdefault(recipe.equivalent_ohm, []).append(recipe)
    return {value: tuple(grouped[value]) for value in sorted(grouped)}


def _finite_scalar(value: Any, *, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, Real):
        raise _invalid(f"{name} must be a finite real number; got {value!r}.")
    result = float(value)
    if not math.isfinite(result):
        raise _invalid(f"{name} must be finite; got {value!r}.")
    return result


def stress_division(
    tree: Any,
    terminal_voltage_V: Any = None,
    terminal_current_A: Any = None,
    *,
    terminal_voltage: Any = None,
    terminal_current: Any = None,
) -> dict[str, Any]:
    """Divide terminal voltage/current across each physical resistor leaf.

    Supply either terminal voltage or terminal current; supplying both is
    allowed when they agree with the tree's exact equivalent.  The returned
    ``elements`` list carries a path, actual resistor value, voltage, current,
    and instantaneous resistive power for every physical leaf.
    """

    if terminal_voltage is not None:
        if terminal_voltage_V is not None:
            raise _invalid("provide terminal_voltage_V or terminal_voltage, not both.")
        terminal_voltage_V = terminal_voltage
    if terminal_current is not None:
        if terminal_current_A is not None:
            raise _invalid("provide terminal_current_A or terminal_current, not both.")
        terminal_current_A = terminal_current
    if terminal_voltage_V is None and terminal_current_A is None:
        raise _invalid("provide terminal voltage or terminal current for stress division.")

    node = _node_from(tree)
    equivalent = _equivalent_node(node)
    supplied_voltage = (
        _finite_scalar(terminal_voltage_V, name="terminal_voltage_V")
        if terminal_voltage_V is not None
        else None
    )
    supplied_current = (
        _finite_scalar(terminal_current_A, name="terminal_current_A")
        if terminal_current_A is not None
        else None
    )
    voltage = supplied_voltage if supplied_voltage is not None else supplied_current * float(equivalent)
    current = supplied_current if supplied_current is not None else supplied_voltage / float(equivalent)
    if supplied_voltage is not None and supplied_current is not None:
        expected = supplied_current * float(equivalent)
        if not math.isclose(supplied_voltage, expected, rel_tol=1e-9, abs_tol=1e-12):
            raise _invalid(
                f"terminal voltage/current disagree for equivalent {equivalent} ohm: "
                f"expected {expected!r} V, got {supplied_voltage!r} V."
            )

    elements: list[dict[str, Any]] = []

    def visit(current_node: _FrozenNode, node_voltage: float, node_current: float, path: tuple[int, ...]) -> None:
        if current_node[0] == "R":
            elements.append(
                {
                    "path": list(path),
                    "ohm": current_node[1],
                    "voltage_V": node_voltage,
                    "current_A": node_current,
                    "power_W": node_voltage * node_current,
                }
            )
            return
        if current_node[0] == "S":
            for index, child in enumerate(current_node[1]):
                child_current = node_current
                child_voltage = child_current * float(_equivalent_node(child))
                visit(child, child_voltage, child_current, path + (index,))
        else:
            for index, child in enumerate(current_node[1]):
                child_voltage = node_voltage
                child_current = child_voltage / float(_equivalent_node(child))
                visit(child, child_voltage, child_current, path + (index,))

    visit(node, voltage, current, ())
    return {
        "tree": _thaw(node),
        "equivalent_ohm": equivalent,
        "terminal_voltage_V": voltage,
        "terminal_current_A": current,
        "elements": elements,
        "per_element": elements,
    }


# Friendly aliases for integration code that uses either noun.
per_element_stress = stress_division
element_stress = stress_division


def _validate_stages(stages: Any) -> int:
    if isinstance(stages, bool) or not isinstance(stages, Integral):
        raise _invalid(f"stages must be a positive integer; got {stages!r}.")
    result = int(stages)
    if result < 1:
        raise _invalid(f"stages must be a positive integer; got {result}.")
    return result


def _inventory_counts(inventory: Any) -> dict[int, int | None] | None:
    if inventory is None:
        return None
    if isinstance(inventory, Mapping):
        source = inventory.items()
    elif isinstance(inventory, Sequence) and not isinstance(inventory, (str, bytes, bytearray)):
        # A sequence is a convenient explicit stock list, e.g. [30, 30, 520].
        counts = Counter(_component_value(value, where="inventory component") for value in inventory)
        return {value: int(counts.get(value, 0)) for value in COMPONENTS}
    else:
        raise _invalid("inventory must be None, a component-count mapping, or a component stock sequence.")

    result: dict[int, int | None] = {}
    for raw_component, raw_count in source:
        component = _component_value(raw_component, where="inventory component")
        if component in result:
            raise _invalid(f"inventory contains duplicate entries for {component} ohm.")
        if raw_count is None:
            result[component] = None
            continue
        if isinstance(raw_count, bool) or not isinstance(raw_count, Integral):
            raise _invalid(f"inventory count for {component} ohm must be a nonnegative integer or None.")
        count = int(raw_count)
        if count < 0:
            raise _invalid(f"inventory count for {component} ohm must be nonnegative.")
        result[component] = count
    return result


def combined_bom(
    front: Any,
    tail: Any,
    stages: int,
    inventory: Mapping[Any, Any] | Sequence[Any] | None = None,
) -> dict[str, Any]:
    """Build the uniform-stage bill of materials for front and tail trees.

    ``required_count`` is bounded and exact from the supplied trees and stage
    count.  If inventory is omitted, availability remains ``None`` and each
    row is marked ``UNKNOWN``; no stock is assumed.  A mapping provides known
    counts for its listed components (an omitted component is known absent),
    while a ``None`` mapping value explicitly keeps that component unknown.
    """

    stage_count = _validate_stages(stages)
    front_node = _node_from(front)
    tail_node = _node_from(tail)
    front_recipe = _recipe(front_node)
    tail_recipe = _recipe(tail_node)
    required_per_stage = Counter(_module_values(front_node) + _module_values(tail_node))
    required = {component: count * stage_count for component, count in sorted(required_per_stage.items())}
    available = _inventory_counts(inventory)

    rows: list[dict[str, Any]] = []
    for component, required_count in required.items():
        if available is None:
            available_count: int | None = None
            shortfall: int | None = None
            status = "UNKNOWN"
            count_status = "REQUIRED_BY_UNIFORM_STAGES_AVAILABLE_QUANTITY_UNKNOWN"
        elif component not in available:
            # A supplied mapping is an explicit stock snapshot: an omitted
            # confirmed component has zero available units.  Callers can use
            # ``{component: None}`` when a listed component remains unknown.
            available_count = 0
            shortfall = required_count
            status = "INSUFFICIENT"
            count_status = "REQUIRED_EXCEEDS_AVAILABLE"
        elif available[component] is None:
            available_count = None
            shortfall = None
            status = "UNKNOWN"
            count_status = "REQUIRED_BY_UNIFORM_STAGES_AVAILABLE_QUANTITY_UNKNOWN"
        else:
            available_count = available[component]
            shortfall = max(0, required_count - available_count)
            status = "AVAILABLE" if shortfall == 0 else "INSUFFICIENT"
            count_status = "REQUIRED_AND_AVAILABLE" if status == "AVAILABLE" else "REQUIRED_EXCEEDS_AVAILABLE"
        rows.append(
            {
                "component_ohm": component,
                "required_count": required_count,
                "available_count": available_count,
                "shortfall": shortfall,
                "availability_status": status,
                "count_status": count_status,
            }
        )

    return {
        "front": front_recipe.tree,
        "tail": tail_recipe.tree,
        "front_recipe_id": front_recipe.id,
        "tail_recipe_id": tail_recipe.id,
        "front_equivalent_ohm": front_recipe.equivalent_ohm,
        "tail_equivalent_ohm": tail_recipe.equivalent_ohm,
        "stages": stage_count,
        "uniform_stages": True,
        "bill_of_materials": rows,
        "bom": rows,
        "inventory_supplied": inventory is not None,
    }


__all__ = [
    "COMPONENTS",
    "COMPONENT_VALUES",
    "MAX_MODULES",
    "NetworkRecipe",
    "NetworkValidationError",
    "canonicalize",
    "equivalent_resistance",
    "enumerate_networks",
    "electrical_groups",
    "combined_bom",
    "stress_division",
    "per_element_stress",
    "element_stress",
]
