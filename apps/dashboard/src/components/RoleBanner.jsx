import React from 'react';

export default function RoleBanner({ page, apiBaseUrl, isUsingMock, error, loading }) {
  return (
    <>
      <div className="role-banner-container">
        {page.startsWith("store") ? (
          <span className="role-tag store-role">👤 점주 전용 실시간 관제 모드 ({page})</span>
        ) : page === "head-office" ? (
          <span className="role-tag supervisor-role">👔 슈퍼바이저 전용 비교 분석 모드</span>
        ) : (
          <span className="role-tag setting-role">⚙️ 시스템 환경설정</span>
        )}

        {(page === "store-001" || page === "store-002") && (
          <span className="polling-status">🟢 실시간 State Polling 가동 중 (2s)</span>
        )}
        {(page === "head-office" || page === "setting") && (
          <span className="polling-status stopped">⏹️ Polling 중지됨 (네트워크 자원 절약)</span>
        )}
      </div>

      {isUsingMock && (
        <section className="notice mock-notice">
          <strong>💡 [개발용 임시 데이터 가동 중]</strong> 백엔드 API({apiBaseUrl}) 미연결 상태이므로 정의된 샘플 데이터로 화면을 표시합니다. (F12 네트워크 탭에 <code>/state</code> 단일 요청 기록)
        </section>
      )}

      {error && !isUsingMock && (
        <section className="notice error-notice">
          <strong>❌ API 오류 발생:</strong> {error}
        </section>
      )}

      {loading && (
        <section className="notice loading-notice">
          🔄 화면 및 실시간 State 동기화 진행 중...
        </section>
      )}
    </>
  );
}
