"""Execute predeclared grouped runtime folds from complete retained 99-label data."""
import argparse
import hashlib
import json
from pathlib import Path
import re
from time import perf_counter_ns

from run_grouped_rc_history_coverage import cases_with_history_coverage
from structural_analysis.benchmark.rc_control_design import _bytes, _save
from structural_analysis.benchmark.rc_control_learning import RCControlSeedPolicy
from structural_analysis.benchmark.rc_control_runtime_selection import run_rc_control_runtime_selection

INVENTORY_SHA256 = 'f850f7e65670bf4d6254039da2aca35269cbd1840b645d82308c2402017849f0'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
    parser.add_argument('--output-directory', required=True, type=Path)
    parser.add_argument('--source-revision', required=True)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()
    started = perf_counter_ns()
    if not re.fullmatch('[0-9a-f]{40}', args.source_revision):
        raise ValueError('exact source revision required')
    raw = (args.bundle / 'inventory.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != INVENTORY_SHA256:
        raise ValueError('original label packet inventory mismatch')
    index = {row['path']: row for row in json.loads(raw)['files']}

    def original(name):
        raw = (args.bundle / name).read_bytes()
        if len(raw) != index[name]['byte_length'] or hashlib.sha256(raw).hexdigest() != index[name]['sha256']:
            raise ValueError(f'original label input changed: {name}')
        return json.loads(raw)

    plan = original('study/coverage-plan.json')
    labels = original('study/labels/learning-study.json')
    samples = original('study/labels/training-samples.json')
    policy = RCControlSeedPolicy(_bytes(original('study/labels/policy.json')).decode())
    if len(samples) != 99 or not all(r['labels_eligible'] for r in labels['generation']):
        raise ValueError('all 99 original labels required')
    if not labels['evaluation_deferred'] or labels['evaluation_work']['known_work']['core_calls']:
        raise ValueError('reserved evaluations must remain unexecuted')
    cases = cases_with_history_coverage(extended_line_search=True)
    actual = [{'case_id': c.case_id, 'split': c.split, 'model': c.model.canonical_payload(),
               'request': c.request.to_dict()} for c in cases]
    if actual != plan['cases']:
        raise ValueError('regenerated cases differ from original source declarations')
    if args.preflight_only:
        print(json.dumps({'cases': len(cases), 'training_samples': len(samples), 'solver_calls': 0}))
        return
    root = args.output_directory.resolve()
    root.mkdir(parents=True, exist_ok=False)
    _save(root, 'training-source.json', _bytes({
        'source_revision': args.source_revision,
        'label_source_revision': plan['source_revision'], 'label_plan_hash': plan['plan_hash'],
        'original_inventory_sha256': INVENTORY_SHA256,
        'learning_report_hash': labels['report_hash'],
        'original_generation_work': labels['generation_work'],
        'original_label_study_wall_ns': labels['whole_study_wall_ns'],
        'ridge_grid': [1e4, 1e6], 'repetitions': 3,
        'maximum_fits': 19, 'maximum_core_calls': 4104,
        'range_eligibility_is_runtime_proposal': False,
        'original_range_summary_failure_affects_labels': False,
    }))
    result = run_rc_control_runtime_selection(
        cases, samples, policy, source_revision=args.source_revision,
        output_directory=root / 'selection', ridge_grid=(1e4, 1e6), repetitions=3,
        maximum_fits=19, maximum_core_calls=4104,
        arithmetic_profile='retained-twofold-refinement.v1',
        withholding_strategy='connected_training_groups',
        proposal_abstention_strategy='secant', static_model_abstention=True,
    )
    _save(root, 'campaign-outcome.json', _bytes({
        'selection_result_hash': result['result_hash'],
        'selected_strategy': result['selected_strategy'],
        'parent_wall_ns_before_outcome_write': perf_counter_ns() - started,
        'timing_scope': 'input verification and preparation through selection; imports, final outcome write and later audits excluded',
        'label_study_wall_ns_separate': labels['whole_study_wall_ns'],
        'net_savings_proved': False, 'reserved_evaluation_executed': False,
    }))
    print(json.dumps({'selected_strategy': result['selected_strategy'], 'root': str(root)}))


if __name__ == '__main__':
    main()
