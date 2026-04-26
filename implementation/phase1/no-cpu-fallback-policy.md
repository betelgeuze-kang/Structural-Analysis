# No CPU Fallback Policy (Hard Rule)

이 프로젝트의 실행 정책은 아래를 기본값으로 강제한다.

1. **CPU fallback 기본 금지**
- 가속기(`cuda/hip`)가 사용 가능한 환경에서 CPU로 내려가는 동작은 허용하지 않는다.
- 검증 리포트에는 `cpu_fallback_used`를 반드시 기록한다.

2. **CPU 사용은 "필수 상황" + "명시적 opt-in"일 때만 허용**
- 가속기가 전혀 없는 환경에서는 CPU가 필수일 수 있다.
- 이 경우에도 CLI에서 `--allow-cpu-required`를 명시해야만 CPU 실행을 허용한다.
- 명시적 opt-in이 없으면 `ERR_ACCELERATOR_REQUIRED`로 즉시 실패한다.

3. **Gate 조건**
- `cpu_fallback_used == false`
- 모델 정확도 gate는 `max_val_mae_pct <= 5`, `track <= 5`, `tunnel <= 5`

적용 대상(핵심):
- `train_tgnn_baseline.py`
- `run_phased_multidomain_modules.py`
- `zero_copy_real_probe.py`
- `run_p0_core_gap_pipeline.py` (probe 단계 opt-in 전달)
- `run_phase1_topk_pipeline.py` (strict probe 기본 opt-in 전달)
