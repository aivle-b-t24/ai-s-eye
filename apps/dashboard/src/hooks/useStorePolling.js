import { useState, useEffect, useCallback } from 'react'
import { STORES, DEFAULT_STORE_DATA } from '../constants/auth'
import {
  fetchStoreState,
  fetchStoreEta,
  fetchStoreMenus,
  fetchStorePolicies,
  fetchStoreSettings,
} from '../api/storeApi'

function isStoreId(value) {
  return typeof value === 'string' && value.startsWith('store-')
}

/**
 * @param {{ enabled: boolean, storeId?: string | null, isHeadOffice?: boolean }} options
 */
export function useStorePolling({ enabled, storeId, isHeadOffice = false }) {
  const [storesData, setStoresData] = useState(DEFAULT_STORE_DATA)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const loadStateOnly = useCallback(async (targetStoreId, isInitial = false) => {
    if (isInitial) setLoading(true)

    try {
      const [stateData, etaData] = await Promise.all([
        fetchStoreState(targetStoreId),
        fetchStoreEta(targetStoreId),
      ])

      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? DEFAULT_STORE_DATA[targetStoreId]),
          state: stateData,
          eta: etaData ?? prev[targetStoreId]?.eta ?? null,
        },
      }))
      setError('')
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

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
        loadStateOnly(STORES.DONGMYEONG, false)
        loadStateOnly(STORES.SUWAN, false)
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
