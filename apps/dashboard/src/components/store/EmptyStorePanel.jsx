import React from 'react';

export default function EmptyStorePanel({ storeId }) {
  return (
    <section className="panel empty-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Store Manager View</p>
          <h2>🏢 매장 2 관제 화면 ({storeId})</h2>
        </div>
        <span className="sold-out-badge">데이터 미등록 매장</span>
      </div>

      <div className="empty-message-box">
        <div className="empty-icon">📭</div>
        <h3>매장 2 수집 데이터가 존재하지 않습니다.</h3>
        <p>현재 <code>{storeId}</code> 매장의 AI 카메라 및 API 스트림이 연결되어 있지 않습니다.</p>
        <span className="empty-hint">네트워크 탭(F12)을 확인하면 <code>/api/stores/{storeId}/state</code> 단일 요청 후 폴링 중임을 확인할 수 있습니다.</span>
      </div>
    </section>
  );
}
