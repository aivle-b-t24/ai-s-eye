import { firebaseAuth } from '../firebase'

async function authorizationHeaders(headers, forceRefresh = false) {
  const user = firebaseAuth.currentUser
  if (!user) {
    throw new Error('로그인이 필요합니다.')
  }

  const token = await user.getIdToken(forceRefresh)
  const result = new Headers(headers)
  result.set('Authorization', `Bearer ${token}`)
  return result
}

export async function authenticatedFetch(input, init = {}) {
  const request = async (forceRefresh = false) => fetch(input, {
    ...init,
    headers: await authorizationHeaders(init.headers, forceRefresh),
  })

  let response = await request(false)
  if (response.status === 401 && firebaseAuth.currentUser) {
    response = await request(true)
  }
  return response
}

export async function currentIdToken() {
  const user = firebaseAuth.currentUser
  if (!user) throw new Error('로그인이 필요합니다.')
  return user.getIdToken()
}
