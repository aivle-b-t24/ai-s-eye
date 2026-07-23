import React from 'react';

export default function SettingsView({ apiBaseUrl, setPage }) {
  return (
    <section className="setting-view">
      <div className="setting-header">
        <h2>⚙️ 대시보드 환경설정</h2>
        <button className="back-btn" onClick={() => setPage("store-001")}>
          ← [점주] 매장 1 대시보드로 돌아가기
        </button>
      </div>

      <div className="panel setting-panel">
        <h3>시스템 및 폴링 매개변수</h3>
        <div className="setting-group">
          <label>API Base URL</label>
          <input type="text" value={apiBaseUrl} readOnly />
        </div>
        <div className="setting-group">
          <label>실시간 폴링 정책</label>
          <input type="text" value="매장 화면 진입 시 /state 단일 Polling (2초) | 본사/설정 진입 시 Polling 중지" readOnly />
        </div>
      </div>
    </section>
  );
}
