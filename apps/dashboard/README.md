# 대시보드

매장 인원, 대기 인원, 예상 대기시간과 메뉴 상태를 보여주는 React 화면입니다.

프로젝트 루트에서 `docker compose up --build -d`를 실행하면 API, PostgreSQL과 함께 시작됩니다.

- 화면: http://localhost:5173
- API 문서: http://localhost:8000/docs

공통 화면 코드는 `src/App.jsx`, 스타일은 `src/App.css`에서 시작하면 됩니다.
슈퍼바이저 화면은 `src/components/head-office`에서 관리하며, 같은 폴더의
`DESIGN.md`에 본사 화면 전용 디자인 규칙을 정리했습니다.

연결 주소는 다음 환경변수로 변경할 수 있습니다.

- `VITE_API_BASE_URL`: 매장 상태와 기간별 집계 API
- `VITE_AICC_BASE_URL`: 슈퍼바이저 AI 운영 인사이트 API
- `VITE_ENABLE_CAMERA_TWIN_V2`: `true`이면 점주 화면의 구역 현황 지도 대신
  카메라 시점 디지털 트윈을 표시합니다. `false`이면 기존 지도로 즉시 돌아갑니다.
