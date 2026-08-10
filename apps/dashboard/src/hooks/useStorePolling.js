import { useState, useEffect, useCallback, useRef } from 'react'
import { STORES, DEFAULT_STORE_DATA } from '../constants/auth'
import {
  fetchStoreState,
  fetchStoreEta,
  fetchStoreOccupancy,
  fetchStoreMenus,
  fetchStorePolicies,
  fetchStoreSettings,
} from '../api/storeApi'

function isStoreId(value) {
  return typeof value === 'string' && value.startsWith('store-')
}

// 디지털 트윈이 세는 기준과 동일하게, 직원이 아닌 에이전트를 '현재 고객'으로 카운트한다.
function countCustomers(frame) {
  const agents = frame?.agents ?? []
  return agents.filter((agent) => agent?.role !== 'staff').length
}

function frameKeyOf(frame) {
  if (!frame) return null
  return `${frame.frame_id ?? frame.captured_at}:${frame.published_at ?? ''}`
}

/**
 * @param {{ enabled: boolean, storeId?: string | null, isHeadOffice?: boolean }} options
 */
export function useStorePolling({ enabled, storeId, isHeadOffice = false }) {
  const [storesData, setStoresData] = useState(DEFAULT_STORE_DATA)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  // 매장별 마지막으로 반영한 프레임 키. 프레임이 그대로면 KPI를 갱신하지 않고 유지한다.
  const lastFrameKeyRef = useRef({})

  const applyStoreState = useCallback((targetStoreId, stateData, etaData) => {
    setStoresData((prev) => ({
      ...prev,
      [targetStoreId]: {
        ...(prev[targetStoreId] ?? DEFAULT_STORE_DATA[targetStoreId]),
        state: stateData,
        eta: etaData ?? prev[targetStoreId]?.eta ?? null,
      },
    }))
  }, [])

  // 매장 화면: 디지털 트윈과 같은 occupancy 프레임에 맞춰, 프레임이 바뀔 때만 KPI(현재 고객·대기·예상)를 갱신한다.
  // → 대기 주문/예상 대기시간이 폴링마다 확확 바뀌지 않고, 트윈과 숫자가 어긋나지 않는다.
  const loadStateOnly = useCallback(async (targetStoreId, isInitial = false) => {
    if (isInitial) setLoading(true)

    try {
      const occupancy = await fetchStoreOccupancy(targetStoreId)
      const frameKey = frameKeyOf(occupancy)

      // 새 프레임이 아니면(같은 분석 이미지) 값 유지 → 급변 방지, 트윈 갱신 주기와 동기화
      if (!isInitial && frameKey && lastFrameKeyRef.current[targetStoreId] === frameKey) {
        setError('')
        return
      }

      // 대기/예상도 트윈과 동일한 프레임의 값으로 조회(frame_id 지정) → 셋 다 같은 프레임
      const [stateData, etaData] = await Promise.all([
        fetchStoreState(targetStoreId),
        fetchStoreEta(targetStoreId, occupancy?.frame_id ?? null),
      ])

      // '현재 고객' 수를 트윈과 동일한 occupancy 소스(비직원 에이전트)로 통일
      const mergedState =
        stateData && occupancy
          ? { ...stateData, visible_person_count: countCustomers(occupancy) }
          : stateData

      if (frameKey) lastFrameKeyRef.current[targetStoreId] = frameKey

      applyStoreState(targetStoreId, mergedState, etaData)
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [applyStoreState])

  // 본사 화면: 트윈이 없어 프레임 동기화가 불필요 → 상태·ETA를 그대로 조회한다.
  const loadHqStateOnly = useCallback(async (targetStoreId) => {
    try {
      const [stateData, etaData] = await Promise.all([
        fetchStoreState(targetStoreId),
        fetchStoreEta(targetStoreId),
      ])
      applyStoreState(targetStoreId, stateData, etaData)
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [applyStoreState])

  const loadStaticData = useCallback(async (targetStoreId) => {
    try {
      const [menuData, policyData, etaData, settingsData] = await Promise.all([
        fetchStoreMenus(targetStoreId),
        fetchStorePolicies(targetStoreId),
        fetchStoreEta(targetStoreId),
        fetchStoreSettings(targetStoreId),
      ])
      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? DEFAULT_STORE_DATA[targetStoreId]),
          menus: menuData?.menus ?? [],
          policies: policyData?.policies ?? [],
          eta: etaData ?? null,
          settings: settingsData ?? prev[targetStoreId]?.settings ?? null,
        },
      }))
    } catch {
      // API Error handler
    }
  }, [])

  // ⏱ Smart Polling: Pauses automatically when tab is hidden (document.hidden)
  useEffect(() => {
    let timerId = null
    const targetStoreId = storeId

    const startTimer = () => {
      if (timerId) clearInterval(timerId)
      if (!document.hidden && enabled && isStoreId(targetStoreId)) {
        timerId = setInterval(() => {
          loadStateOnly(targetStoreId, false)
        }, 6000)
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (timerId) {
          clearInterval(timerId)
          timerId = null
        }
      } else if (enabled && isStoreId(targetStoreId)) {
        loadStateOnly(targetStoreId, false)
        startTimer()
      }
    }

    if (enabled) {
      if (isStoreId(targetStoreId)) {
        loadStaticData(targetStoreId)
        loadStateOnly(targetStoreId, true)
        startTimer()
      } else if (isHeadOffice) {
        loadHqStateOnly(STORES.DONGMYEONG)
        loadHqStateOnly(STORES.SUWAN)
      }
    }

    document.addEventListener('visibilitychange', handleVisibilityChange)

    return () => {
      if (timerId) clearInterval(timerId)
      document.removeEventListener('visibilitychange', handleVisibilityChange)
    }
  }, [
    enabled,
    storeId,
    isHeadOffice,
    loadStateOnly,
    loadHqStateOnly,
    loadStaticData,
  ])

  const resolvedStoreId = isStoreId(storeId) ? storeId : STORES.DONGMYEONG
  const activeDashboard =
    storesData[resolvedStoreId]
    ?? DEFAULT_STORE_DATA[resolvedStoreId]
    ?? DEFAULT_STORE_DATA[STORES.DONGMYEONG]

  const soldOutCount =
    activeDashboard?.menus?.filter((menu) => !menu.available).length ?? 0

  return {
    storesData,
    activeDashboard,
    soldOutCount,
    error,
    loading,
    loadStateOnly,
    loadStaticData,
  }
}
