import React from 'react';

export default function SupervisorHeadOfficeView({ dashboard, mockData }) {
  return (
    <section className="head-office-view">
      <div className="panel-heading-large">
        <p className="eyebrow">Supervisor Control Mode</p>
        <h2>👔 슈퍼바이저 가맹점 비교 대시보드</h2>
        <p className="subtitle">전 가맹점의 실시간 수용 인원 비교 및 반복 문제를 통합 관리합니다.</p>
      </div>

      {/* 슈퍼바이저 전용 2개 매장 핵심 지표 비교 카드 (실시간 state 동적 바인딩) */}
      <div className="head-office-grid">
        <article className="panel store-compare-card">
          <div className="card-header">
            <h3>🏢 매장 1 (강남점)</h3>
            <span className="status available">정상 가동 중</span>
          </div>
          <div className="card-metrics">
            <div className="metric-row">
              <span>현재 실시간 인원</span>
              <strong>{dashboard?.state?.visible_person_count ?? 0}명</strong>
            </div>
            <div className="metric-row">
              <span>대기 인원 / ETA</span>
              <strong>{dashboard?.state?.queue_count_estimate ?? 0}명 ({dashboard?.eta?.estimated_wait_minutes ?? 0}분)</strong>
            </div>
            <div className="metric-row">
              <span>AI 카메라 상태</span>
              <strong>{dashboard?.state?.quality_status === "normal" ? "🟢 정상 (Cam 01)" : "🟡 점검 필요 (Cam 01)"}</strong>
            </div>
          </div>
        </article>

        <article className="panel store-compare-card muted-card">
          <div className="card-header">
            <h3>🏢 매장 2 (홍대점)</h3>
            <span className="status sold-out">데이터 미연결</span>
          </div>
          <div className="card-metrics">
            <div className="metric-row">
              <span>현재 실시간 인원</span>
              <strong>데이터 없음 (-명)</strong>
            </div>
            <div className="metric-row">
              <span>대기 인원 / ETA</span>
              <strong>데이터 없음 (-분)</strong>
            </div>
            <div className="metric-row">
              <span>AI 카메라 상태</span>
              <strong>🔴 네트워크 장비 미연결</strong>
            </div>
          </div>
        </article>
      </div>

      {/* 슈퍼바이저 매장별 특이사항 & 조치 필요 항목 */}
      <div className="head-office-details">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Supervisor Alerts</p>
              <h2>매장별 특이사항 및 반복 문제</h2>
            </div>
          </div>
          <div className="policy-list">
            <div className="policy-item">
              <strong>🏢 매장 1 (강남점)</strong>
              <p>1층 카운터 대기열 {dashboard?.state?.queue_count_estimate ?? 0}명 수용 중. 실시간 모니터링 가동.</p>
            </div>
            <div className="policy-item">
              <strong>🏢 매장 2 (홍대점)</strong>
              <p>카메라 네트워크 셋톱박스 재부팅 필요. 수집 주기 이탈 발생.</p>
            </div>
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Actions Required</p>
              <h2>확인 및 조치 필요 항목</h2>
            </div>
          </div>
          <div className="policy-list">
            <div className="policy-item">
              <strong>🔴 홍대점 셋톱박스 점검</strong>
              <p><code>store-002</code> 실시간 스트림 API 엔드포인트를 현장 재설정해야 합니다.</p>
            </div>
            <div className="policy-item">
              <strong>🟢 전체 가맹점 총평</strong>
              <p>현재 원격 긴급 조치가 요구되는 재해/장애 특이사항은 없습니다.</p>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}
