// Shared definition of the Workbench v2 information architecture.
//
// The commercial layout puts the model -> analysis -> results -> compare flow at
// the centre, and treats evidence / benchmarks / review as a verification layer
// that follows it. The nav and the page render from this single list so they
// never drift apart.

export type SectionGroup = 'model' | 'verification' | 'decision'

export interface WorkbenchSectionDef {
  id: string
  label: string
  group: SectionGroup
}

export const workbenchSections: WorkbenchSectionDef[] = [
  { id: 'wb2-sec-project', label: 'Project', group: 'model' },
  { id: 'wb2-sec-model', label: 'Model Health', group: 'model' },
  { id: 'wb2-sec-analysis', label: 'Analysis', group: 'model' },
  { id: 'wb2-sec-run', label: 'Run Monitor', group: 'model' },
  { id: 'wb2-sec-results', label: 'Results', group: 'model' },
  { id: 'wb2-sec-compare', label: 'Compare', group: 'model' },
  { id: 'wb2-sec-evidence', label: 'Evidence', group: 'verification' },
  { id: 'wb2-sec-benchmarks', label: 'Benchmarks', group: 'verification' },
  { id: 'wb2-sec-review', label: 'Review', group: 'decision' },
  { id: 'wb2-sec-export', label: 'Export', group: 'decision' },
]

export const sectionGroupLabel: Record<SectionGroup, string> = {
  model: 'Model → Analysis → Results',
  verification: 'Verification layer',
  decision: 'Decision',
}
