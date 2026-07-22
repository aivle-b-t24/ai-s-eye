import React from 'react';

export default function PolicyListPanel({ policies }) {
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
          policies.map((policy) => (
            <div className="policy-item" key={policy.policy_id}>
              <strong>{policy.title}</strong>
              <p>{policy.content}</p>
            </div>
          ))
        )}
      </div>
    </article>
  );
}
