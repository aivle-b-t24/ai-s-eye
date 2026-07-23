import React from 'react';

import KpiSummaryBar from './KpiSummaryBar';
import ZoneBreakdownTable from './ZoneBreakdownTable';
import VisionMonitorPanel from './VisionMonitorPanel';
import MenuListPanel from './MenuListPanel';
import PolicyListPanel from './PolicyListPanel';
import EmptyStorePanel from './EmptyStorePanel';

export default function StoreDashboardView({ page, dashboard, soldOutCount }) {
  if (page === 'store-002' && !dashboard?.state) {
    return <EmptyStorePanel storeId="store-002" />;
  }

  return (
    <>
      {dashboard?.state?.quality_status !== "normal" && (
        <section className="alert-banner warning-alert">
          ⚠️ <strong>점주 알림:</strong> AI 카메라 스트림 화질 점검이 필요합니다.
        </section>
      )}

      {(dashboard?.state?.queue_count_estimate ?? 0) >= 20 && (
        <section className="alert-banner queue-alert">
          🚨 <strong>대기 폭주 알림:</strong> 현재 외부 대기 인원이 {dashboard?.state?.queue_count_estimate}명으로 증가했습니다. 카운터 대응을 권장합니다.
        </section>
      )}

      <KpiSummaryBar dashboard={dashboard} soldOutCount={soldOutCount} />

      <section className="dashboard-main-grid">
        <div className="main-left-content">
          <ZoneBreakdownTable zoneCounts={dashboard?.state?.zone_counts} />
          <VisionMonitorPanel storeId={page} />
        </div>

        <div className="main-right-content">
          <MenuListPanel menus={dashboard?.menus} soldOutCount={soldOutCount} />
          <PolicyListPanel policies={dashboard?.policies} />
        </div>
      </section>
    </>
  );
}
