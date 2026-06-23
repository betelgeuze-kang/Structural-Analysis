(() => {
  const qs = (selector, root = document) => root.querySelector(selector)
  const qsa = (selector, root = document) => [...root.querySelectorAll(selector)]
  const toast = qs('#toast')
  let toastTimer
  let running = false

  function showToast(message) {
    toast.textContent = message
    toast.classList.add('show')
    clearTimeout(toastTimer)
    toastTimer = setTimeout(() => toast.classList.remove('show'), 2300)
  }

  function download(name, type, content) {
    const blob = new Blob([content], { type })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = name
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  function openImport() {
    qs('#import-modal').hidden = false
  }

  function closeImport() {
    qs('#import-modal').hidden = true
  }

  function appendLog(event, detail, residual = '-', tolerance = '-', status = 'INFO', source = 'SAW Core') {
    const now = new Date().toLocaleTimeString('ko-KR', { hour12: false })
    const row = document.createElement('tr')
    row.innerHTML = `<td>${now}</td><td>${event}</td><td>${detail}</td><td>${residual}</td><td>${tolerance}</td><td class="${status === 'PASS' || status === 'SUCCESS' ? 'success' : ''}">${status}</td><td>${source}</td>`
    qs('#log-body').appendChild(row)
    row.scrollIntoView({ block: 'nearest' })
  }

  async function runAnalysis() {
    if (running) return
    running = true
    const button = qs('[data-action="run-analysis"]')
    const original = button.innerHTML
    button.innerHTML = '<span>◌</span>해석 실행 중'
    button.disabled = true
    const fill = qs('#progress-fill')
    const label = qs('#progress-label')
    fill.style.width = '0%'
    label.textContent = '해석 준비 0%'
    appendLog('해석 재실행', 'GPU 8대 기준 full validation lane 시작', '-', '-', 'INFO', 'SAW Solver')

    const steps = [
      [15, 'Canonical model 검증'],
      [38, '전역 접선 조립'],
      [61, 'Newton–Krylov 반복'],
      [82, '기준해 비교'],
      [100, '잔차 감사 완료'],
    ]

    for (const [progress, text] of steps) {
      await new Promise(resolve => setTimeout(resolve, 550))
      fill.style.width = `${progress}%`
      label.textContent = `${text} ${progress}%`
      appendLog('실행 진행', text, progress > 60 ? '2.36e-06' : '-', '1.0e-05', progress === 100 ? 'PASS' : 'INFO', 'SAW Solver')
    }

    button.innerHTML = original
    button.disabled = false
    label.textContent = 'Hard Pass 52 / 52 (100%)'
    running = false
    showToast('해석과 잔차 감사가 완료되었습니다.')
  }

  function exportReport(kind) {
    const review = qs('.decision.active')?.dataset.decision ?? 'PASS'
    const report = {
      schema_version: 'structural-workbench-prototype.v1',
      project: 'L3_Pilot_Project_A',
      case: 'Case_52',
      solver: 'SAW Solver v3.2 (GPU)',
      dof: 3246912,
      convergence: { status: 'PASS', tolerance: 1e-5, residual_l2: 1.28e-6 },
      comparison: { drift_rms_pct: 2.32, base_shear_pct: 1.87, top_displacement_pct: 2.15, member_force_p95_pct: 3.28 },
      reviewer_decision: review,
      reviewer_comment: qs('#review-comment').value,
      generated_at: new Date().toISOString(),
    }

    if (kind === 'html') {
      download('structural-analysis-report.html', 'text/html', `<!doctype html><meta charset="utf-8"><title>Structural Analysis Report</title><pre>${JSON.stringify(report, null, 2)}</pre>`)
    } else if (kind === 'json') {
      download('structural-analysis-report.json', 'application/json', JSON.stringify(report, null, 2))
    } else if (kind === 'zip') {
      download('reproduce-bundle.txt', 'text/plain', `Prototype reproduce bundle\n\n${JSON.stringify(report, null, 2)}`)
    } else {
      window.print()
    }
    showToast(`${kind.toUpperCase()} 내보내기를 시작했습니다.`)
  }

  qsa('[data-page]').forEach(button => button.addEventListener('click', () => {
    qsa('[data-page]').forEach(item => item.classList.remove('active'))
    button.classList.add('active')
    showToast(`${button.textContent.trim()} 화면은 프로토타입 연결 상태입니다.`)
  }))

  qsa('.tab').forEach(tab => tab.addEventListener('click', () => {
    qsa('.tab').forEach(item => item.classList.remove('active'))
    qsa('.tab-content').forEach(item => item.classList.remove('active'))
    tab.classList.add('active')
    qs(`#tab-${tab.dataset.tab}`).classList.add('active')
  }))

  qsa('.decision').forEach(button => button.addEventListener('click', () => {
    qsa('.decision').forEach(item => item.classList.remove('active'))
    button.classList.add('active')
  }))

  qs('#review-comment').addEventListener('input', event => {
    qs('#comment-count').textContent = event.currentTarget.value.length
  })

  qs('#result-mode').addEventListener('change', event => {
    const mode = event.currentTarget.value
    const floors = qs('#heat-floors')
    floors.style.filter = mode === 'stress' ? 'hue-rotate(-35deg) saturate(1.25)' : mode === 'mode' ? 'hue-rotate(65deg)' : 'none'
    showToast(`결과 표시가 ${event.currentTarget.selectedOptions[0].textContent}로 변경되었습니다.`)
  })

  qsa('[data-export]').forEach(button => button.addEventListener('click', () => exportReport(button.dataset.export)))
  qsa('[data-action]').forEach(button => button.addEventListener('click', event => {
    const action = event.currentTarget.dataset.action
    if (action === 'toggle-sidebar') qs('#sidebar').classList.toggle('open')
    if (action === 'open-import') openImport()
    if (action === 'close-import') closeImport()
    if (action === 'confirm-import') {
      const file = qs('#file-input').files[0]
      closeImport()
      appendLog('모델 가져오기', file ? `${file.name} 파싱 완료` : '데모 IFC 모델 로드', '-', '-', 'SUCCESS', 'Importer')
      showToast(file ? `${file.name} 가져오기가 완료되었습니다.` : '데모 모델을 불러왔습니다.')
    }
    if (action === 'validate') showToast('모델 health check: 12개 규칙 PASS')
    if (action === 'run-analysis') runAnalysis()
    if (action === 'download-report') exportReport('html')
    if (action === 'save-review') showToast(`${qs('.decision.active').dataset.decision} 검토 결과를 저장했습니다.`)
    if (action === 'copy-cli') {
      navigator.clipboard?.writeText(qs('.cli-card pre').textContent)
      showToast('재현 명령을 복사했습니다.')
    }
  }))

  qs('#import-modal').addEventListener('click', event => {
    if (event.target === qs('#import-modal')) closeImport()
  })

  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') closeImport()
  })
})()
