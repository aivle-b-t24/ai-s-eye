import React from 'react';

export default function PolicyListPanel({ policies, isExpanded, onToggleExpand }) {
  const INITIAL_COUNT = 3;

  const displayPolicies = isExpanded ? policies : policies?.slice(0, INITIAL_COUNT);
  const hasMore = (policies?.length ?? 0) > INITIAL_COUNT;

  return (
    <article className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Notice & Policy</p>
          <h2>매장 안내 및 정책</h2>
        </div>
      </div>

      <div className="policy-list">
        {!policies || policies.length === 0 ? (
          <div className="empty-message">등록된 매장 정책이 없습니다.</div>
        ) : (
          displayPolicies.map((policy) => (
            <div className="policy-item" key={policy.policy_id}>
              <strong>{policy.title}</strong>
              <p>{policy.content}</p>
            </div>
          ))
        )}
      </div>

      {hasMore && (
        <div style={{ textAlign: 'center', marginTop: '16px', paddingTop: '12px', paddingBottom: '14px', marginBottom: '4px', borderTop: '1px solid rgba(255, 255, 255, 0.08)' }}>
          <button

            type="button"
            onClick={onToggleExpand}
            style={{
              background: 'rgba(255, 255, 255, 0.05)',
              border: '1px solid rgba(255, 255, 255, 0.18)',
              borderRadius: '20px',
              padding: '7px 20px',
              color: '#ffffff',
              fontSize: '13px',
              fontWeight: '600',
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              transition: 'all 0.2s ease'
            }}
          >
            {isExpanded ? '접기 ▲' : '더보기 ▼'}
          </button>
        </div>
      )}
    </article>
  );
}


