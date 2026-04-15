import { defineStore } from 'pinia'
import { ref } from 'vue'
import { login as apiLogin } from '@/api/admin'

export const useAuthStore = defineStore('auth', () => {
  const token = ref(localStorage.getItem('admin_token') || '')
  const username = ref(localStorage.getItem('admin_username') || '')

  async function login(user: string, password: string) {
    const { data } = await apiLogin(user, password)
    token.value = data.access_token
    username.value = data.username
    localStorage.setItem('admin_token', data.access_token)
    localStorage.setItem('admin_username', data.username)
  }

  function logout() {
    token.value = ''
    username.value = ''
    localStorage.removeItem('admin_token')
    localStorage.removeItem('admin_username')
  }

  const isAuthenticated = () => !!token.value

  return { token, username, login, logout, isAuthenticated }
})
