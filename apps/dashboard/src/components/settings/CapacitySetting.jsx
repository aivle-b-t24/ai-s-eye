import React, { useState, useEffect } from 'react'
import { fetchStoreSettings, saveStoreSettings } from '../../api/storeApi'

// 매장 수용 인원 설정. 저장한 값은 혼잡도(현재 인원 ÷ 수용 인원) 계산에 쓰인다.
// 레이아웃은 ROI·장면 편집기와 같은 roi-settings 서브에디터 패턴을 따른다.
export default function CapacitySetting({ storeId }) {
  const [capacity, setCapacity] = useState('')
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState(null)

  useEffect(() => {
    let active = true
    setLoading(true)
    fetchStoreSettings(storeId)
      .then((data) => {
        if (active && data) setCapacity(String(data.max_capacity))
      })
      .finally(() => {
        if (active) setLoading(false)
      })
    return () => {
      active = false
    }
  }, [storeId])

  const handleSave = async () => {
    const value = Number(capacity)
    if (!Number.isInteger(value) || value < 1 || value > 1000) {
      setStatus({ kind: 'error', message: '1~1000 사이 정수를 입력해 주세요.' })
      return
    }
    setSaving(true)
    setStatus(null)
    try {
      const saved = await saveStoreSettings(storeId, value)
      setCapacity(String(saved.max_capacity))
      setStatus({ kind: 'success', message: '저장되었습니다. 혼잡도에 반영됩니다.' })
    } catch (err) {
      setStatus({ kind: 'error', message: err.message })
    } finally {
      setSaving(false)
    }
  }

  return (
    <section
      className="roi-settings capacity-settings"
      aria-labelledby="capacity-settings-title"
    >
      <div className="roi-settings-heading">
        <div>
          <p className="roi-eyebrow">OPERATIONS SETUP</p>
          <h3 id="capacity-settings-title">수용 인원 설정</h3>
          <p>{storeId} · 혼잡도 기준</p>
        </div>
        <button
          type="button"
          className="roi-primary-btn"
          onClick={handleSave}
          disabled={loading || saving}
        >
          {saving ? '저장 중…' : '저장'}
        </button>
      </div>

      <p className="capacity-desc">
        혼잡도 = 현재 인원 ÷ 수용 인원. 매장 최대 수용 인원을 입력하고 저장하세요.
      </p>

      <div className="setting-group capacity-input">
        <label htmlFor="max-capacity">최대 수용 인원 (명)</label>
        <input
          id="max-capacity"
          type="number"
          min="1"
          max="1000"
          value={capacity}
          placeholder={loading ? '불러오는 중…' : '예: 30'}
          onChange={(event) => setCapacity(event.target.value)}
          disabled={loading || saving}
        />
      </div>

      {status && (
        <p className={`roi-status roi-status-${status.kind}`} role="status">
          {status.message}
        </p>
      )}
    </section>
  )
}
