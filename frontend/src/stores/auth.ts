/** Auth store - manages JWT tokens and user state */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/auth'
import type { User } from '@/types'
import router from '@/router'

export const useAuthStore = defineStore('auth', () => {
  const accessToken = ref<string | null>(localStorage.getItem('access_token'))
  const user = ref<User | null>(null)

  const isLoggedIn = computed(() => !!accessToken.value)
  const isAdmin = computed(() => user.value?.role === 'admin')

  // Restore user info from localStorage
  const savedUser = localStorage.getItem('user_info')
  if (savedUser) {
    try {
      user.value = JSON.parse(savedUser)
    } catch { /* ignore */ }
  }

  function setAuth(token: string, userInfo: Partial<User>) {
    accessToken.value = token
    user.value = {
      user_id: userInfo.user_id!,
      username: userInfo.username!,
      role: userInfo.role || 'user',
      age: userInfo.age ?? null,
      gender: userInfo.gender ?? null,
      country: userInfo.country ?? null,
      created_at: userInfo.created_at || new Date().toISOString(),
    }
    localStorage.setItem('access_token', token)
    localStorage.setItem('user_info', JSON.stringify(user.value))
  }

  async function login(username: string, password: string) {
    const { data } = await authApi.login({ username, password })
    setAuth(data.access_token, {
      user_id: data.user_id,
      username: data.username,
      role: data.role,
    })
    // Load favorites after login
    const { useFavoritesStore } = await import('@/stores/favorites')
    useFavoritesStore().loadFavorites()
    return data
  }

  async function register(username: string, password: string, profile?: { age?: number; gender?: number; country?: string }) {
    const { data } = await authApi.register({ username, password, ...profile })
    setAuth(data.access_token, {
      user_id: data.user_id,
      username: data.username,
      role: data.role,
    })
    return data
  }

  async function refreshToken(): Promise<boolean> {
    try {
      const { data } = await authApi.refresh()
      accessToken.value = data.access_token
      localStorage.setItem('access_token', data.access_token)
      return true
    } catch {
      return false
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch { /* ignore */ }
    accessToken.value = null
    user.value = null
    localStorage.removeItem('access_token')
    localStorage.removeItem('user_info')
    // Reset favorites on logout
    const { useFavoritesStore } = await import('@/stores/favorites')
    useFavoritesStore().reset()
    router.push('/login')
  }

  return { accessToken, user, isLoggedIn, isAdmin, login, register, refreshToken, logout, setAuth }
})
