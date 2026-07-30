import { useState, useEffect, useCallback } from 'react'
import { STORES, DEFAULT_STORE_DATA } from '../constants/auth'
import {
  fetchStoreState,
  fetchStoreEta,
  fetchStoreMenus,
  fetchStorePolicies,
} from '../api/storeApi'

export function useStorePolling(authMode, page, isDedicatedHeadOffice) {
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
      const [menuData, policyData, etaData] = await Promise.all([
        fetchStoreMenus(targetStoreId),
        fetchStorePolicies(targetStoreId),
        fetchStoreEta(targetStoreId),
      ])
      setStoresData((prev) => ({
        ...prev,
        [targetStoreId]: {
          ...(prev[targetStoreId] ?? DEFAULT_STORE_DATA[targetStoreId]),
          menus: menuData?.menus ?? [],
          policies: policyData?.policies ?? [],
          eta: etaData ?? null,
        },
      }))
    } catch {
      // API Error handler
    }
  }, [])

  // ⏱ Smart Polling: Pauses automatically when tab is hidden (document.hidden) to save battery/network
  useEffect(() => {
    let timerId = null

    const startTimer = () => {
      if (timerId) clearInterval(timerId)
      if (!document.hidden && authMode === 'dashboard') {
        if (page === STORES.DONGMYEONG || page === STORES.SUWAN) {
          timerId = setInterval(() => {
            loadStateOnly(page, false)
          }, 2000)
        }
      }
    }

    const handleVisibilityChange = () => {
      if (document.hidden) {
        if (timerId) {
          clearInterval(timerId)
          timerId = null
        }
      } else {
        if (
          authMode === 'dashboard' &&
          (page === STORES.DONGMYEONG || page === STORES.SUWAN)
        ) {
          loadStateOnly(page, false)
          startTimer()
        }
      }
    }

    if (authMode === 'dashboard') {
      if (page === STORES.DONGMYEONG || page === STORES.SUWAN) {
        loadStaticData(page)
        loadStateOnly(page, true)
        startTimer()
      } else if (page === STORES.HEAD_OFFICE && !isDedicatedHeadOffice) {
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
    authMode,
    page,
    isDedicatedHeadOffice,
    loadStateOnly,
    loadStaticData,
  ])

  const activeDashboard =
    storesData[page] ??
    DEFAULT_STORE_DATA[page] ??
    DEFAULT_STORE_DATA[STORES.DONGMYEONG]

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
