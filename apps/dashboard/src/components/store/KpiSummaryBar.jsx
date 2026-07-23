import React from 'react';

export default function KpiSummaryBar({ dashboard, soldOutCount }) {
  return (
    <section className="kpi-summary-bar" aria-label="점주용 핵심 지표 요약">
      <article className="kpi-card">
        <span className="kpi-label">매장 총 인원</span>
        <strong className="kpi-value highlight-number">
          {dashboard?.state?.visible_person_count ?? 0}
          <small>명</small>
        </strong>
        <span className="kpi-subtext">실시간 객체 감지</span>
      </article>

      <article className="kpi-card">
        <span className="kpi-label">대기 인원</span>
        <strong className="kpi-value">
          {dashboard?.state?.queue_count_estimate ?? 0}
          <small>명</small>
        </strong>
        <span className="kpi-subtext">외부/웨이팅 존</span>
      </article>

      <article className="kpi-card accent-kpi">
        <span className="kpi-label">예상 대기시간</span>
        <strong className="kpi-value">
          {dashboard?.eta?.estimated_wait_minutes ?? 0}
          <small>분</small>
        </strong>
        <span className="kpi-subtext">AI ETA 산출</span>
      </article>

      <article className="kpi-card">
        <span className="kpi-label">품절 메뉴</span>
        <strong className="kpi-value warning-text">
          {soldOutCount}
          <small>개</small>
        </strong>
        <span className="kpi-subtext">전체 {dashboard?.menus?.length ?? 0}개 메뉴 중</span>
      </article>

      <article className="kpi-card">
        <span className="kpi-label">AI 카메라 상태</span>
        <strong className="kpi-value status-text">
          {dashboard?.state?.quality_status === "normal" ? "🟢 정상" : "🟡 점검필요"}
        </strong>
        <span className="kpi-subtext">스트림 화질 및 비전 분석</span>
      </article>
    </section>
  );
}
