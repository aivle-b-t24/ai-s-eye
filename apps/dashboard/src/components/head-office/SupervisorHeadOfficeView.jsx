import React from 'react';

export default function SupervisorHeadOfficeView({ storesData }) {
  const store1 = storesData['store-001'] ?? {};
  const store2 = storesData['store-002'] ?? {};

  const store1State = store1.state;
  const store1Eta = store1.eta;

  const store2State = store2.state;
  const store2Eta = store2.eta;

  return (
    <section className="head-office-view">
      <div className="panel-heading-large">
        <p className="eyebrow">Supervisor Control Mode</p>
        <h2>슈퍼바이저 가맹점 통합 관제 대시보드</h2>
        <p className="subtitle">
          전 가맹점의 실시간 수용 인원 및 대기열 상태를 본사에서 즉시 체크하고 관리합니다.
        </p>
      </div>

      <section
        className="alert-banner live-sync-banner"
        style={{
          background:
            'linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(6, 182, 212, 0.12))',
          border: '1px solid rgba(16, 185, 129, 0.4)',
          borderRadius: '12px',
          padding: '16px 20px',
          marginBottom: '24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxShadow: '0 4px 12px rgba(0, 0, 0, 0.05)',
        }}
      >
        <div>
          <h4
            style={{
              margin: 0,
              fontSize: '15px',
              color: '#10b981',
              fontWeight: '700',
            }}
          >
            전 가맹점 - 본사 실시간 관제 연동 가동 중 (Live Synced)
          </h4>

          <p
            style={{
              margin: '2px 0 0 0',
              fontSize: '13px',
              color: '#64748b',
            }}
          >
            매장 실시간 화면과 본사 화면이 100% 실시간 연동되어 가맹점 현황을 즉시 체크할 수 있습니다.
          </p>
        </div>

        <span
          className="status-tag active"
          style={{ fontSize: '12px', padding: '6px 12px' }}
        >
          본사-매장 실시간 동기화 완료
        </span>
      </section>

      <div className="head-office-grid">
        <article className="panel store-compare-card">
          <div className="card-header">
            <h3>매장 1 (동명점)</h3>
            <span className="status available">실시간 연동 중</span>
          </div>

          <div className="card-metrics">
            <div className="metric-row">
              <span>현재 실시간 인원</span>
              <strong style={{ color: '#2563eb' }}>
                {store1State?.visible_person_count ?? 0}명
              </strong>
            </div>

            <div className="metric-row">
              <span>대기 인원 / ETA</span>
              <strong style={{ color: '#2563eb' }}>
                {store1State?.queue_count_estimate ?? 0}명 (
                {store1Eta?.estimated_wait_minutes ?? 0}분)
              </strong>
            </div>

            <div className="metric-row">
              <span>AI 비전 카메라 피드</span>
              <strong>
                {store1State?.quality_status === 'normal'
                  ? '정상 (Cam 01)'
                  : '점검 필요 (Cam 01)'}
              </strong>
            </div>
          </div>
        </article>

        <article className="panel store-compare-card">
          <div className="card-header">
            <h3>매장 2 (수완점)</h3>
            <span className="status available">실시간 연동 중</span>
          </div>

          <div className="card-metrics">
            <div className="metric-row">
              <span>현재 실시간 인원</span>
              <strong style={{ color: '#2563eb' }}>
                {store2State?.visible_person_count ?? 0}명
              </strong>
            </div>

            <div className="metric-row">
              <span>대기 인원 / ETA</span>
              <strong style={{ color: '#2563eb' }}>
                {store2State?.queue_count_estimate ?? 0}명 (
                {store2Eta?.estimated_wait_minutes ?? 0}분)
              </strong>
            </div>

            <div className="metric-row">
              <span>AI 비전 카메라 피드</span>
              <strong>
                {store2State?.quality_status === 'normal'
                  ? '정상 (Cam 02)'
                  : '점검 필요 (Cam 02)'}
              </strong>
            </div>
          </div>
        </article>
      </div>

      <div className="head-office-details">
        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Supervisor Real-time Check</p>
              <h2>매장별 실시간 관제 및 특이사항 즉시 체크</h2>
            </div>
          </div>

          <div className="policy-list">
            <div className="policy-item">
              <strong>매장 1 (동명점) 실시간 연동 중</strong>
              <p>
                실시간 관제 인원{' '}
                <strong>{store1State?.visible_person_count ?? 0}명</strong>
                {' '}(대기열 {store1State?.queue_count_estimate ?? 0}명, ETA{' '}
                {store1Eta?.estimated_wait_minutes ?? 0}분) 본사 모니터링 수신 중.
              </p>
            </div>

            <div className="policy-item">
              <strong>매장 2 (수완점) 실시간 연동 중</strong>
              <p>
                실시간 관제 인원{' '}
                <strong>{store2State?.visible_person_count ?? 0}명</strong>
                {' '}(대기열 {store2State?.queue_count_estimate ?? 0}명, ETA{' '}
                {store2Eta?.estimated_wait_minutes ?? 0}분) 본사 모니터링 수신 중.
              </p>
            </div>
          </div>
        </article>

        <article className="panel">
          <div className="panel-heading">
            <div>
              <p className="eyebrow">Actions & Status</p>
              <h2>본사 통합 체크 및 조치 사항</h2>
            </div>
          </div>

          <div className="policy-list">
            <div className="policy-item">
              <strong>동명점 & 수완점 실시간 동기화 완료</strong>
              <p>
                매장 실시간 관제 화면과 본사 대시보드가 실시간 연동되어 수용 인원 및 대기열 변동이 바로 체크됩니다.
              </p>
            </div>

            <div className="policy-item">
              <strong>가맹점 종합 평가</strong>
              <p>
                모든 가맹점의 AI 카메라 피드 및 감지 데이터가 안정적으로 통합 수집 중입니다.
              </p>
            </div>
          </div>
        </article>
      </div>
    </section>
  );
}