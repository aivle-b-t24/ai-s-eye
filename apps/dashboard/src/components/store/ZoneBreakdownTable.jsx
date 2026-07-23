import React from 'react';

export default function ZoneBreakdownTable({ zoneCounts }) {
  return (
    <article className="panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Zone Breakdown</p>
          <h2>구역별 실시간 인원 현황</h2>
        </div>
        <span className="live-badge">● LIVE TRACKING</span>
      </div>

      <div className="panel-body">
        <table className="zone-table">
          <thead>
            <tr>
              <th>구역 구분</th>
              <th>좌석 (Seating)</th>
              <th>통로/이동 (Aisle)</th>
              <th>특수 구역</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <th>1층 (1F)</th>
              <td><span className="count-pill">{zoneCounts?.seating_1f ?? 0}명</span></td>
              <td><span className="count-pill">{zoneCounts?.aisle_1f ?? 0}명</span></td>
              <td>카운터: <strong>{zoneCounts?.counter_1f ?? 0}명</strong></td>
            </tr>
            <tr>
              <th>2층 (2F)</th>
              <td><span className="count-pill">{zoneCounts?.seating_2f ?? 0}명</span></td>
              <td><span className="count-pill">{zoneCounts?.aisle_2f ?? 0}명</span></td>
              <td>직원: <strong>{zoneCounts?.staff_1f ?? 0}명</strong></td>
            </tr>
            <tr>
              <th>외부 (Outdoor)</th>
              <td colSpan="2" className="text-muted">대기열 구역 인원</td>
              <td>외부대기: <strong className="accent-text">{zoneCounts?.waiting_out ?? 0}명</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </article>
  );
}
