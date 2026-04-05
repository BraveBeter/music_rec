/** Axios API client with JWT interceptor and auto-refresh */
import axios from 'axios'
import { useAuthStore } from '@/stores/auth'

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

// Request interceptor: attach access token
apiClient.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.accessToken) {
    config.headers.Authorization = `Bearer ${auth.accessToken}`
  }
  return config
})

// Response interceptor: auto-refresh on 401
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config
    // Prevent infinite loop if an auth endpoint (like /auth/refresh or /auth/logout) fails with 401
    // Using includes to be safe regarding baseURL or absolute URLs
    if (error.response?.status === 401 && !originalRequest._retry && !originalRequest.url?.includes('/auth/')) {
      originalRequest._retry = true
      const auth = useAuthStore()
      const refreshed = await auth.refreshToken()
      if (refreshed) {
        originalRequest.headers.Authorization = `Bearer ${auth.accessToken}`
        return apiClient(originalRequest)
      } else {
        auth.logout()
      }
    }
    return Promise.reject(error)
  }
)

export default apiClient
