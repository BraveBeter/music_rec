/** Auth API calls */
import apiClient from './client'
import type { TokenResponse } from '@/types'

export const authApi = {
  register(data: { username: string; password: string; age?: number; gender?: number; country?: string }) {
    return apiClient.post<TokenResponse>('/auth/register', data)
  },

  login(data: { username: string; password: string }) {
    return apiClient.post<TokenResponse>('/auth/login', data)
  },

  refresh() {
    return apiClient.post<{ access_token: string }>('/auth/refresh')
  },

  logout() {
    return apiClient.post('/auth/logout')
  },
}
