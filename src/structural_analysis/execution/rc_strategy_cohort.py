"""Portable original strategy graphs plus explicitly bound CLI cost records.

This owns byte integrity and metadata accounting, not physical-result authority.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
import re
from types import MappingProxyType

from structural_analysis.api.frame3d_direct_control_request import (
    strict_json_object_bytes,
)
from structural_analysis.benchmark.rc_control_design import _bytes, _sha
from structural_analysis.benchmark.rc_control_process_costs import (
    compare_rc_control_process_costs,
)
from structural_analysis.benchmark.rc_control_strategy_costs import (
    compare_rc_control_strategy_costs,
)
from structural_analysis.execution.rc_search_http import (
    RcSearchArtifactBundle,
    _document,
    _path,
    _META_MAX,
    _TOTAL_MAX,
)

SCHEMA = "rc-control-strategy-cohort-artifact.v1"
PROCESS_SCHEMA = "rc-control-strategy-cohort-artifact.v2"


def _processes(raw):
    value = strict_json_object_bytes(raw, maximum_bytes=_META_MAX)
    if set(value) != {"processes"}:
        raise ValueError("exact process observations document required")
    return value["processes"]


STRATEGIES = ("price_order", "learned_order")


def _ref(path, raw):
    return {"path": path, "byte_length": len(raw), "sha256": _sha(raw)}


@dataclass(frozen=True, init=False)
class RcStrategyCohortBundle:
    report_hash: str
    artifacts: Mapping[str, bytes]

    @classmethod
    def from_reader(
        cls, reader: Callable[[str, int], bytes], *, expected_report_hash: str
    ):
        files: dict[str, bytes] = {}
        total = 0

        def read(path, maximum, ref=None):
            nonlocal total
            if not _path(path):
                raise ValueError("cohort artifact path invalid")
            raw = files.get(path)
            if raw is None:
                raw = reader(path, min(maximum, _TOTAL_MAX - total))
                if (
                    type(raw) is not bytes
                    or len(raw) > maximum
                    or total + len(raw) > _TOTAL_MAX
                ):
                    raise ValueError("cohort byte budget exceeded")
                files[path] = raw
                total += len(raw)
            if ref is not None and (
                type(ref) is not dict
                or type(ref.get("byte_length")) is not int
                or ref != _ref(path, raw)
            ):
                raise ValueError("cohort original byte binding mismatch")
            return raw

        manifest = _document(read("cohort.json", _META_MAX), "report_hash")
        with_processes = manifest.get("schema_version") == PROCESS_SCHEMA
        if (
            set(manifest)
            != {
                "schema_version",
                "source_revision",
                "source_revision_is_attestation",
                "pairs",
                "cost_accounting",
                "independent_physical_validation",
                "report_hash",
            }
            | (
                {"process_observations", "process_cost_accounting"}
                if with_processes
                else set()
            )
            or manifest["report_hash"] != expected_report_hash
            or manifest.get("schema_version") not in (SCHEMA, PROCESS_SCHEMA)
            or not re.fullmatch(r"[a-f0-9]{40}", str(manifest.get("source_revision")))
            or manifest.get("source_revision_is_attestation") is not False
            or manifest.get("independent_physical_validation") is not False
            or type(manifest.get("pairs")) is not list
            or not 1 <= len(manifest["pairs"]) <= 64
        ):
            raise ValueError("pinned bounded cohort manifest required")
        pairs = []
        for ordinal, pair in enumerate(manifest["pairs"]):
            if type(pair) is not dict or set(pair) != set(STRATEGIES):
                raise ValueError("cohort must retain both strategies")
            values = {}
            for strategy in STRATEGIES:
                record = pair[strategy]
                if type(record) is not dict or set(record) != {
                    "report",
                    "report_hash",
                    "runtime",
                }:
                    raise ValueError("explicit cohort report/runtime bindings required")
                prefix = f"pairs/{ordinal}/{strategy}/"
                raw = read(prefix + "result.json", _META_MAX, record["report"])
                report = _document(raw, "report_hash")
                if (
                    report.get("schema_version")
                    != "experimental-rc-control-candidate-strategy.v1"
                    or report.get("strategy") != strategy
                ):
                    raise ValueError(
                        "cohort child must be the declared standalone strategy"
                    )
                child = RcSearchArtifactBundle.from_reader(
                    lambda path, maximum: read(prefix + path, maximum),
                    expected_report_hash=record["report_hash"],
                )
                runtime_raw = read(
                    prefix + "strategy-runtime.json", _META_MAX, record["runtime"]
                )
                values[strategy] = {
                    "report": report,
                    "plan": _document(child.artifacts["plan.json"], "plan_hash"),
                    "runtime": strict_json_object_bytes(
                        runtime_raw, maximum_bytes=_META_MAX
                    ),
                }
            pairs.append(values)
        if _bytes(manifest.get("cost_accounting")) != _bytes(
            compare_rc_control_strategy_costs(pairs)
        ):
            raise ValueError("cohort cost accounting mismatch")
        if with_processes:
            raw = read(
                "process-observations.json", _META_MAX, manifest["process_observations"]
            )
            if _bytes(manifest["process_cost_accounting"]) != _bytes(
                compare_rc_control_process_costs(pairs, _processes(raw))
            ):
                raise ValueError("cohort process cost accounting mismatch")
        instance = object.__new__(cls)
        object.__setattr__(instance, "report_hash", manifest["report_hash"])
        object.__setattr__(instance, "artifacts", MappingProxyType(files))
        return instance

    def write_directory(self, destination: Path):
        """Write into a new directory; publish the root manifest last."""
        root = Path(destination)
        root.mkdir(parents=True, exist_ok=False)
        for relative, raw in self.artifacts.items():
            if relative == "cohort.json":
                continue
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as stream:
                stream.write(raw)
        with (root / "cohort.json").open("xb") as stream:
            stream.write(self.artifacts["cohort.json"])


def create_rc_strategy_cohort(
    pairs, *, source_revision: str, process_observations: bytes | None = None
):
    """Package pairs of {strategy: (validated study bundle, original runtime bytes)}.

    Nested original bytes are preserved. Runtime inputs become explicitly bound
    here; digests do not upgrade their measurement provenance or attest authorship.
    """
    if (
        not re.fullmatch(r"[a-f0-9]{40}", str(source_revision))
        or type(pairs) is not tuple
        or not 1 <= len(pairs) <= 64
    ):
        raise ValueError("bounded tuple of pairs and full source revision required")
    files, references, values = {}, [], []
    total = 0
    for ordinal, pair in enumerate(pairs):
        if type(pair) is not dict or set(pair) != set(STRATEGIES):
            raise ValueError("cohort must retain both strategies")
        refs, value = {}, {}
        for strategy in STRATEGIES:
            study, runtime_raw = pair[strategy]
            if (
                type(study) is not RcSearchArtifactBundle
                or type(runtime_raw) is not bytes
            ):
                raise ValueError(
                    "validated study bundle and original runtime bytes required"
                )
            total += sum(map(len, study.artifacts.values())) + len(runtime_raw)
            if len(runtime_raw) > _META_MAX or total > _TOTAL_MAX:
                raise ValueError("cohort byte budget exceeded")
            prefix = f"pairs/{ordinal}/{strategy}/"
            files.update({prefix + path: raw for path, raw in study.artifacts.items()})
            files[prefix + "strategy-runtime.json"] = runtime_raw
            refs[strategy] = {
                "report": _ref(prefix + "result.json", study.artifacts["result.json"]),
                "report_hash": study.report_hash,
                "runtime": _ref(prefix + "strategy-runtime.json", runtime_raw),
            }
            value[strategy] = {
                "report": _document(study.artifacts["result.json"], "report_hash"),
                "plan": _document(study.artifacts["plan.json"], "plan_hash"),
                "runtime": strict_json_object_bytes(
                    runtime_raw, maximum_bytes=_META_MAX
                ),
            }
        references.append(refs)
        values.append(value)
    manifest = {
        "schema_version": SCHEMA,
        "source_revision": source_revision,
        "source_revision_is_attestation": False,
        "pairs": references,
        "cost_accounting": compare_rc_control_strategy_costs(values),
        "independent_physical_validation": False,
    }
    if process_observations is not None:
        if (
            type(process_observations) is not bytes
            or len(process_observations) > _META_MAX
        ):
            raise ValueError("bounded original process observation bytes required")
        manifest.update(
            schema_version=PROCESS_SCHEMA,
            process_observations=_ref(
                "process-observations.json", process_observations
            ),
            process_cost_accounting=compare_rc_control_process_costs(
                values, _processes(process_observations)
            ),
        )
        files["process-observations.json"] = process_observations
    manifest["report_hash"] = _sha(_bytes(manifest))
    files["cohort.json"] = _bytes(manifest)
    return RcStrategyCohortBundle.from_reader(
        lambda path, maximum: files[path], expected_report_hash=manifest["report_hash"]
    )
