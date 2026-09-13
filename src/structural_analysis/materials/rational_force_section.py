"""Section contract selecting rational accumulation through original frame assembly."""

from structural_analysis.engine_v2.contracts._canonical import canonical_hash
from structural_analysis.materials.retained_fiber_strain import RetainedFiberRCSection
from structural_analysis.solvers.nonlinear.rational_accumulation import PROFILE


class RationalForceSection(RetainedFiberRCSection):
    force_accumulation = PROFILE

    @property
    def contract_hash(self):
        return canonical_hash(
            {
                "base_section_contract_hash": super().contract_hash,
                "force_accumulation": PROFILE,
            }
        )


def rational_force_section(section):
    if type(section) is not RetainedFiberRCSection:
        raise ValueError("rational forces require the retained-strain section")
    return RationalForceSection(
        fibers=section.fibers,
        steel=section.steel,
        concrete=section.concrete,
        section_id=section.section_id,
    )
