import { check, type RcObject } from './rcJobSchema'

const nat = (v: unknown): v is number => Number.isSafeInteger(v) && Number(v) >= 0

/** Validate recorded sequential children; this does not attest their clocks. */
export function validateRcTrainingIntervals(training: RcObject): void {
  let labelWall = 0, labelCpu = 0
  for (const [index, invocation] of training.label_invocations.entries()) {
    check(invocation.status === 'returned' && invocation.phase === ['analysis', 'verification'][index % 2]
      && nat(invocation.wall_ns) && nat(invocation.process_cpu_ns), 'search_training_interval_invalid')
    labelWall += invocation.wall_ns
    labelCpu += invocation.process_cpu_ns
    check(nat(labelWall) && nat(labelCpu), 'search_training_interval_invalid')
  }
  // Sequential label calls and the later fit are children of these totals.
  // Validate containment without charging the same interval twice.
  check(labelWall <= training.label_generation_wall_ns
    && training.label_generation_wall_ns + training.fit.wall_ns <= training.wall_ns
    && labelCpu + training.fit.cpu_ns <= training.cpu_ns, 'search_training_interval_invalid')
}
