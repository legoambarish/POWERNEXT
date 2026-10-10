"""Separate, immutable parameter domains; research ratings are not CPRI ratings."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Profile:
    domain_id: str
    profile_id: str
    label: str
    stage_capacitance_F: float
    stage_charge_max_V: float
    stage_energy_max_J: float
    total_energy_max_J: float
    stages_min: int = 2
    stages_max: int = 15
    summed_charge_max_V: float = 3_000_000.0
    basic_load_capacitance_F: float = 480e-12
    hardware_verified: bool = False
    research_only: bool = False
    constraint_basis: str = "SUPPLIED_CPRI_PARAMETER_SHEET_AND_EXPLICIT_CLARIFICATIONS"

    def as_dict(self):
        return asdict(self)


PROFILES = {
    "cpri_0p5uf": Profile(
        "cpri_0p5uf", "CPRI_0p5uF_NETWORKS_v3", "CPRI parameter profile — 0.5 µF/stage",
        .5e-6, 200_000., 10_000., 150_000.,
    ),
    "research_3uf": Profile(
        "research_3uf", "RESEARCH_3uF_NETWORKS_v3", "Research comparison — 3 µF/stage (not CPRI hardware)",
        3e-6, 200_000., 60_000., 900_000., research_only=True,
        constraint_basis="HYPOTHETICAL_200kV_15_STAGE_DOMAIN_ENERGY_DERIVED_FROM_3uF_NOT_EQUIPMENT_APPROVAL",
    ),
}


def get_profile(domain_id="cpri_0p5uf"):
    if not isinstance(domain_id, str) or domain_id not in PROFILES:
        raise ValueError("Unknown simulation domain; choose cpri_0p5uf or research_3uf")
    return PROFILES[domain_id]

