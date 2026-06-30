// Minimal internationalization for Workbench v2.
//
// Two languages only: English (en) and Korean (ko). Each key maps to the
// English and Korean label. The provider returns the appropriate string based on
// the active locale.

export type Locale = 'en' | 'ko'

const labels: Record<string, Record<Locale, string>> = {
  // Shell
  'shell.title': { en: 'Workbench v2', ko: '워크벤치 v2' },
  'shell.eyebrow': { en: 'Structural Optimization Workbench', ko: '구조 최적화 워크벤치' },
  'shell.claim_prefix': { en: 'Claim boundary: ', ko: '주장 범위: ' },
  'shell.provider': { en: 'Provider', ko: '데이터 소스' },
  'shell.demo': { en: 'Demo', ko: '데모' },
  'shell.live': { en: 'Live', ko: '라이브' },
  'shell.skip': { en: 'Skip to workbench', ko: '워크벤치로 건너뛰기' },
  'shell.source': { en: 'Source', ko: '소스' },
  // Nav groups
  'nav.model': { en: 'Model → Analysis → Results', ko: '모델 → 해석 → 결과' },
  'nav.verification': { en: 'Verification layer', ko: '검증 레이어' },
  'nav.decision': { en: 'Decision', ko: '의사결정' },
  // Nav sections
  'nav.project': { en: 'Project', ko: '프로젝트' },
  'nav.model_health': { en: 'Model Health', ko: '모델 건전성' },
  'nav.analysis': { en: 'Analysis', ko: '해석' },
  'nav.run_monitor': { en: 'Run Monitor', ko: '실행 모니터' },
  'nav.results': { en: 'Results', ko: '결과' },
  'nav.compare': { en: 'Compare', ko: '비교' },
  'nav.evidence': { en: 'Evidence', ko: '증거' },
  'nav.benchmarks': { en: 'Benchmarks', ko: '벤치마크' },
  'nav.review': { en: 'Review', ko: '리뷰' },
  'nav.export': { en: 'Export', ko: '내보내기' },
  // Result/review
  'result.converged': { en: 'Converged', ko: '수렴 완료' },
  'result.failed': { en: 'Did not converge', ko: '수렴 실패' },
  'result.unavailable': { en: 'Convergence unavailable', ko: '수렴 정보 없음' },
  'review.title': { en: 'Review decision', ko: '리뷰 결정' },
  'review.auto_verdict': { en: 'Automated verdict', ko: '자동 판정' },
  'review.draft_heading': { en: 'Reviewer draft (not an automated verdict)', ko: '리뷰어 초안 (자동 판정 아님)' },
  'review.unreviewed': { en: 'Unreviewed', ko: '미검토' },
  'review.pass': { en: 'Pass (reviewer)', ko: '합격 (리뷰어)' },
  'review.needs_review': { en: 'Needs review', ko: '검토 필요' },
  'review.fail': { en: 'Fail (reviewer)', ko: '불합격 (리뷰어)' },
  'review.decision': { en: 'Decision', ko: '결정' },
  'review.reviewer': { en: 'Reviewer', ko: '리뷰어' },
  'review.comment': { en: 'Comment', ko: '코멘트' },
  'review.local_only': { en: 'Stored in this browser only (localStorage) and included in the export. No server save.', ko: '이 브라우저에만 저장(localStorage)되며 내보내기에 포함됩니다. 서버 저장 없음.' },
  // Export
  'export.title': { en: 'Export', ko: '내보내기' },
  'export.button': { en: 'Export bundle (JSON)', ko: '번들 내보내기 (JSON)' },
  'export.preparing': { en: 'Preparing…', ko: '준비 중…' },
  // Run monitor
  'run.title': { en: 'Run Monitor', ko: '실행 모니터' },
  'run.idle': { en: 'Idle', ko: '대기' },
  'run.running': { en: 'Running', ko: '실행 중' },
  'run.converged': { en: 'Converged', ko: '수렴 완료' },
  'run.failed': { en: 'Did not converge', ko: '수렴 실패' },
  'run.validating': { en: 'Validating', ko: '검증 중' },
  // Compare
  'compare.title': { en: 'Compare', ko: '비교' },
  'compare.empty': { en: 'No comparison rows selected. Add benchmark cases from the Benchmarks section.', ko: '비교 행이 선택되지 않았습니다. 벤치마크 섹션에서 추가하세요.' },
  'compare.clear': { en: 'Clear comparison', ko: '비교 초기화' },
  // Benchmark
  'bench.title': { en: 'Public benchmark case browser', ko: '공개 벤치마크 케이스 브라우저' },
  // Evidence
  'evidence.title': { en: 'Read-only evidence', ko: '읽기 전용 증거' },
  // General
  'unavailable': { en: 'Unavailable', ko: '사용 불가' },
  'copy': { en: 'Copy', ko: '복사' },
  'copied': { en: 'Copied ✓', ko: '복사됨 ✓' },
}

export function t(key: string, locale: Locale): string {
  const entry = labels[key]
  if (!entry) return key
  return entry[locale] ?? entry.en ?? key
}

const STORAGE_KEY = 'wb2-locale'

export function loadLocale(): Locale {
  try {
    const stored = typeof localStorage !== 'undefined' ? localStorage.getItem(STORAGE_KEY) : null
    if (stored === 'ko' || stored === 'en') return stored
  } catch { /* ignore */ }
  return 'en'
}

export function saveLocale(locale: Locale): void {
  try {
    if (typeof localStorage !== 'undefined') localStorage.setItem(STORAGE_KEY, locale)
  } catch { /* ignore */ }
}
