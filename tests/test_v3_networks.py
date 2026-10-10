from dataclasses import FrozenInstanceError
from fractions import Fraction

import pytest

from powernext_v3.networks import (
    COMPONENTS,
    NetworkValidationError,
    canonicalize,
    combined_bom,
    electrical_groups,
    enumerate_networks,
    equivalent_resistance,
    stress_division,
)


def resistor(value):
    return {"op": "R", "ohm": value}


def test_canonical_associative_commutative_tree_and_exact_fraction():
    tree = {
        "op": "S",
        "children": [
            resistor(46),
            {"op": "S", "children": [resistor(180), resistor(30)]},
        ],
    }
    assert canonicalize(tree) == {
        "op": "S",
        "children": [resistor(30), resistor(46), resistor(180)],
    }
    assert equivalent_resistance({"op": "P", "children": [resistor(520), resistor(180)]}) == Fraction(936, 7)


def test_catalogue_counts_and_deterministic_records():
    expected = {1: 6, 2: 48, 3: 412, 4: 4192}
    first = None
    for bound, count in expected.items():
        records = enumerate_networks(bound)
        assert len(records) == count
        assert len({record.id for record in records}) == count
        assert all(record.module_count <= bound for record in records)
        if first is None:
            first = [(record.id, record.tree, record.equivalent_ohm) for record in records]
        else:
            assert [(record.id, record.tree, record.equivalent_ohm) for record in records[:6]] == first

    # The exact count-3 delta is the requested 364 canonical trees.
    assert len(enumerate_networks(3)) - len(enumerate_networks(2)) == 364


def test_electrical_groups_keep_physical_alternatives():
    groups = electrical_groups(3)
    assert sum(len(records) for records in groups.values()) == 412
    assert len(groups) == 407
    duplicate_groups = [records for records in groups.values() if len(records) > 1]
    assert duplicate_groups
    assert any(len({record.id for record in records}) > 1 for records in duplicate_groups)
    assert all(isinstance(value, Fraction) for value in groups)


def test_network_recipe_is_frozen_and_tree_property_is_a_copy():
    record = enumerate_networks(1)[0]
    with pytest.raises(FrozenInstanceError):
        record.id = "changed"
    tree = record.tree
    tree["ohm"] = 5000
    assert record.tree["ohm"] != 5000


@pytest.mark.parametrize(
    "bad",
    [
        resistor(True),
        resistor(31),
        resistor(float("nan")),
        resistor(float("inf")),
        {"op": "R", "ohm": 30, "part": "arbitrary"},
        {"op": "X", "ohm": 30},
        {"op": "S", "children": [resistor(30)]},
        {"op": "S", "children": [resistor(30)] * 5},
    ],
)
def test_invalid_trees_are_rejected(bad):
    with pytest.raises((ValueError, NetworkValidationError)):
        canonicalize(bad)


def test_cycle_and_bounds_are_rejected():
    cycle = {"op": "S", "children": []}
    cycle["children"].append(cycle)
    with pytest.raises(ValueError, match="at least two|cycle"):
        canonicalize(cycle)
    with pytest.raises(ValueError):
        enumerate_networks(5)
    with pytest.raises(ValueError):
        enumerate_networks(True)


def test_combined_bom_multiplies_uniform_front_and_tail_by_stages():
    front = {"op": "S", "children": [resistor(30), resistor(46)]}
    tail = {"op": "P", "children": [resistor(180), resistor(520)]}
    report = combined_bom(front, tail, 3)
    assert report["uniform_stages"] is True
    assert report["front_recipe_id"] == "S(R30,R46)"
    assert report["tail_recipe_id"] == "P(R180,R520)"
    assert [(row["component_ohm"], row["required_count"]) for row in report["bill_of_materials"]] == [
        (30, 3),
        (46, 3),
        (180, 3),
        (520, 3),
    ]
    assert all(row["available_count"] is None and row["availability_status"] == "UNKNOWN" for row in report["bom"])

    known = combined_bom(resistor(30), resistor(30), 2, inventory={30: 1})
    row = known["bill_of_materials"][0]
    assert row["required_count"] == 4
    assert row["available_count"] == 1
    assert row["shortfall"] == 3
    assert row["availability_status"] == "INSUFFICIENT"


def test_stress_division_reports_each_physical_element():
    tree = {"op": "P", "children": [resistor(180), resistor(520)]}
    result = stress_division(tree, terminal_voltage_V=700)
    assert result["terminal_current_A"] == pytest.approx(float(Fraction(700, 1) / Fraction(936, 7)))
    assert [item["ohm"] for item in result["elements"]] == [180, 520]
    assert all(item["voltage_V"] == pytest.approx(700) for item in result["elements"])
    assert [item["current_A"] for item in result["elements"]] == pytest.approx([700 / 180, 700 / 520])
    with pytest.raises(ValueError, match="disagree"):
        stress_division(tree, terminal_voltage_V=700, terminal_current_A=1)

