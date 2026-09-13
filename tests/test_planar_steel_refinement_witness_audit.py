"""Synthetic integrity checks; these fixtures provide no structural evidence."""

from copy import deepcopy
import hashlib
import json

import pytest

from scripts.audit_planar_steel_refinement_witness import read_checked, steel_points


@pytest.fixture
def accepted_step():
    states, members = [], []
    for member_index in range(6):
        mid = f"E{member_index}"
        sections, integration = [], []
        for _ in range(3):
            fibers = [
                {"plastic_strain": 0.0, "accumulated_plastic_strain": 0.0}
                for _ in range(4)
            ]
            state = {"fiber_states": fibers}
            integration.append(deepcopy(state))
            sections.append(
                {
                    "trial_state": deepcopy(state),
                    "generalized_strain": {"axial_strain": 0.0},
                    "fiber_responses": [
                        {
                            "trial_state": deepcopy(fiber),
                            "total_strain": 0.0,
                            "stress_mpa": 0.0,
                            "yielded": False,
                        }
                        for fiber in fibers
                    ],
                }
            )
        element = {
            "element_id": mid,
            "basic_beam_state": {"integration_point_states": integration},
        }
        states.append(element)
        members.append(
            {
                "member_id": mid,
                "element_response": {
                    "trial_state": deepcopy(element),
                    "fiber_beam_response": {
                        "integration_point_xi": [-0.7, 0, 0.7],
                        "section_responses": sections,
                    },
                },
            }
        )
    return {
        "committed": True,
        "accepted_checkpoint": {"element_states": states},
        "trial_assembly": {"member_assemblies": members},
    }


def test_hash_rejection_precedes_json_decode(tmp_path):
    path = tmp_path / "changed.json"
    path.write_bytes(b"not JSON")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_checked(path, "0" * 64)


def test_identity_change_rejected_even_when_json_meaning_is_equal(tmp_path):
    path = tmp_path / "path.json"
    raw = json.dumps({"status": "ready"}).encode()
    digest = hashlib.sha256(raw).hexdigest()
    path.write_bytes(raw)
    assert read_checked(path, digest) == {"status": "ready"}
    path.write_bytes(raw + b"\n")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        read_checked(path, digest)


def test_valid_synthetic_state_has_unique_points(accepted_step):
    assert len(steel_points(accepted_step, 2)) == 36


def test_uncommitted_trial_is_rejected(accepted_step):
    accepted_step["committed"] = False
    with pytest.raises(ValueError, match="uncommitted"):
        steel_points(accepted_step, 2)


def test_mismatched_steel_response_is_rejected(accepted_step):
    response = accepted_step["trial_assembly"]["member_assemblies"][0][
        "element_response"
    ]["fiber_beam_response"]["section_responses"][0]["fiber_responses"][2]
    response["trial_state"]["plastic_strain"] = 0.3
    with pytest.raises(ValueError, match="steel state binding mismatch"):
        steel_points(accepted_step, 2)


def test_duplicate_member_observation_is_rejected(accepted_step):
    members = accepted_step["trial_assembly"]["member_assemblies"]
    members.append(deepcopy(members[0]))
    with pytest.raises(ValueError, match="duplicate steel observation"):
        steel_points(accepted_step, 2)
