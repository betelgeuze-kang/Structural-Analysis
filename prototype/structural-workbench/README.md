# Structural Analysis Workbench GUI Prototype

업로드된 화면을 기준으로 구현한 dependency-free 정적 프론트엔드 프로토타입입니다.

## 실행

```bash
python3 -m http.server 4173 --directory prototype/structural-workbench
```

브라우저에서 `http://localhost:4173`을 엽니다.

## 포함된 상호작용

- 반응형 사이드바와 우측 정보 탭
- PASS / REVIEW / FAIL 검토자 결정
- 해석 실행 및 잔차 로그 진행 시뮬레이션
- IFC/MGT/OpenSees/JSON 가져오기 모달
- 결과 모드별 히트맵 변경
- JSON/HTML 리포트 내보내기
- 재현 CLI 복사
- 모바일/태블릿 레이아웃

## 검증

- JavaScript syntax check
- HTML/CSS 구조 검사
- jsdom DOM interaction smoke

이 버전은 UI/interaction prototype이며 실제 구조해석 API는 아직 연결하지 않았습니다. 화면에 표시되는 수렴·정확도·GPU 값은 레이아웃 검증용 예시 데이터입니다.
