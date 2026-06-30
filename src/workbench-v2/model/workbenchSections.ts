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
  i18nKey: string
  group: SectionGroup
}

export const workbenchSections: WorkbenchSectionDef[] = [
  { id: 'wb2-sec-project', label: 'Project', i18nKey: 'project', group: 'model' },
  { id: 'wb2-sec-model', label: 'Model Health', i18nKey: 'model_health', group: 'model' },
  { id: 'wb2-sec-analysis', label: 'Analysis', i18nKey: 'analysis', group: 'model' },
  { id: 'wb2-sec-run', label: 'Run Monitor', i18nKey: 'run_monitor', group: 'model' },
  { id: 'wb2-sec-results', label: 'Results', i18nKey: 'results', group: 'model' },
  { id: 'wb2-sec-compare', label: 'Compare', i18nKey: 'compare', group: 'model' },
  { id: 'wb2-sec-evidence', label: 'Evidence', i18nKey: 'evidence', group: 'verification' },
  { id: 'wb2-sec-benchmarks', label: 'Benchmarks', i18nKey: 'benchmarks', group: 'verification' },
  { id: 'wb2-sec-review', label: 'Review', i18nKey: 'review', group: 'decision' },
  { id: 'wb2-sec-export', label: 'Export', i18nKey: 'export', group: 'decision' },
]

export const sectionGroupLabel: Record<SectionGroup, string> = {
  model: 'Model → Analysis → Results',
  verification: 'Verification layer',
  decision: 'Decision',
}
