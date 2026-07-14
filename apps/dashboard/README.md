# 대시보드

매장 인원, 대기 인원, 예상 대기시간과 메뉴 상태를 보여주는 React 화면입니다.

프로젝트 루트에서 `docker compose up --build -d`를 실행하면 API, PostgreSQL과 함께 시작됩니다.

- 화면: http://localhost:5173
- API 문서: http://localhost:8000/docs

화면 코드는 `src/App.jsx`, 스타일은 `src/App.css`에서 시작하면 됩니다. API 주소는 `VITE_API_BASE_URL` 환경변수로 변경할 수 있습니다.
