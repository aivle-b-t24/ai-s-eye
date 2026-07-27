import React from 'react';

export default function RoleBanner({ page, apiBaseUrl, isUsingMock, error, loading }) {
  return (
    <>
      <div className="role-banner-container">
        {page.startsWith("store") ? (
          <span className="role-tag store-role"> 점주 전용 실시간 관제 모드 ({page === 'store-001' ? '동명점' : '수완점'})</span>
        ) : page === "head-office" ? (
          <span className="role-tag supervisor-role"> 슈퍼바이저 본사 관제 모드</span>
        ) : (
          <span className="role-tag setting-role"> 시스템 환경설정</span>
        )}

        {(page === "store-001" || page === "store-002") && (
          <span className="polling-status"> 실시간 State Polling 가동 중 (2s) •  본사 실시간 연동 중</span>
        )}
        {page === "head-office" && (
          <span className="polling-status"> 매장-본사 실시간 연동 완료 (즉시 동기화 체크 가능)</span>
        )}
        {page === "setting" && (
          <span className="polling-status stopped">⏹️ Polling 중지됨 (네트워크 자원 절약)</span>
        )}
      </div>



      {error && !isUsingMock && (
        <section className="notice error-notice">
          <strong> API 오류 발생:</strong> {error}
        </section>
      )}

      {loading && (
        <section className="notice loading-notice">
           화면 및 실시간 State 동기화 진행 중...
        </section>
      )}
    </>
  );
}
