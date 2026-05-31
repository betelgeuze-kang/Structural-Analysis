# 중·대형 건축물 도면 데이터 — 운영 가이드 / Medium–Large Building Drawing Data Operator Guide

## 목적 / Purpose

상용화용 한국 공공·공모 구조/도면 소스의 **중형(mid_rise·10–30층대)** 및 **대형(high_rise·30층+)** 다양성을 확보합니다. 자동 다운로드는 하지 않으며, 운영자가 공식 포털에서 수동으로 받은 파일만 `collected/artifacts/`에 첨부합니다.

## 수동 다운로드 / Manual download

| 출처 | 포털 | 비고 |
|------|------|------|
| 나라장터 (g2b) | https://www.g2b.go.kr/ | 설계용역·시공 공고 첨부 (PDF/ZIP/MGT). 입찰공고번호는 시드에 넣지 말고, 운영자가 확인한 URL만 기록·첨부 |
| LH | https://www.lh.or.kr/ | 설계공모·입찰 게시판 기초자료 |
| buildingSMART Korea Awards | https://event.buildingsmart.or.kr/Awards/ | 연도별 구조 IFC (예: `/Awards/2024`) |

## 파일 배치 / Where to place files

```
implementation/phase1/open_data/korea/collected/artifacts/<source_id>/
  <source_id>.mgt    # MGT attach targets
  <source_id>.ifc    # IFC attach targets
  …                  # PDF/ZIP 등
```

선택: `curated/` 에 기준 파일을 두고 `local_path`로 연결할 수 있습니다 (기존 native baseline 패턴).

## 벤치마크 브리지 (개발·검증용, 공모 원본 아님)

실제 공모 MGT를 아직 첨부하지 않았을 때, 저장소 벤치마크(`midas_generator_33.optimized.mgt`)로 파이프라인을 검증할 수 있습니다:

```bash
python3 scripts/install_korea_benchmark_mgt_bridge.py --also-curated
python3 scripts/run_korean_medium_large_ingest_pipeline.py --run-roundtrip-parse
```

영수증의 `attach_provenance`가 `repo_benchmark_bridge`이면 벤치마크 복사본입니다. `operator_attached`이면 운영자가 넣은 실제 첨부 파일입니다.

## 명령 / Commands

```bash
# 카탈로그 재생성 (기본 시드 + medium/large 확장 시드 병합)
python3 scripts/generate_korean_source_catalog.py

# 중·대형 소스 표 + ingest 상태
python3 scripts/report_medium_large_korean_sources.py

# 수집 + MGT 헤더 경량 검증 (*VERSION / *UNIT, >500 bytes)
python3 scripts/run_korean_medium_large_ingest_pipeline.py
```

JSON 리포트 예:

```bash
python3 scripts/report_medium_large_korean_sources.py \
  --output-json implementation/phase1/open_data/korea/korean_medium_large_report.json
```

## 초고층 벤치마크 (별도 경로) / Super-tall benchmark (separate path)

국내 공모 카탈로그와 별도로, 메가스트럭처 카탈로그의 **Canton Tower reduced-order SHM** 등 초고층·메가스케일 벤치마크는 다음을 참고하세요.

- [implementation/phase1/open_data/megastructure/README.md](../implementation/phase1/open_data/megastructure/README.md)
- [implementation/phase1/open_data/megastructure/mega_structure_catalog.json](../implementation/phase1/open_data/megastructure/mega_structure_catalog.json)

## 정책 / Policy

- `collect_korean_public_structures.py`는 **로컬 복사만** 수행합니다 (HTTP 자동 다운로드 없음).
- placeholder MGT(~283B)는 `mgt_header_ok=false`로 정직하게 보고됩니다.
- 전체 roundtrip/IFC ingest는 첨부·검증 후 기존 파이프라인을 사용합니다.
