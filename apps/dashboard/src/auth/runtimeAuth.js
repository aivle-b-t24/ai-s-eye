const requestedAuthMode = String(
  import.meta.env.VITE_AUTH_MODE ?? 'firebase',
).toLowerCase()

export const IS_LOCAL_AUTH_MODE = (
  import.meta.env.DEV
  && requestedAuthMode === 'local'
)
