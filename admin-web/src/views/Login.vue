<template>
  <div class="login-wrapper">
    <div class="login-card">
      <h1>MusicRec Admin</h1>
      <p>管理员登录</p>
      <form @submit.prevent="handleLogin">
        <input v-model="username" type="text" placeholder="用户名" required />
        <input v-model="password" type="password" placeholder="密码" required />
        <button type="submit" :disabled="loading">{{ loading ? '登录中...' : '登录' }}</button>
        <p v-if="error" class="error">{{ error }}</p>
      </form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const auth = useAuthStore()

const username = ref('')
const password = ref('')
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  loading.value = true
  error.value = ''
  try {
    await auth.login(username.value, password.value)
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.detail || '登录失败'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-wrapper {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #1a1a2e;
}
.login-card {
  background: #16213e;
  border-radius: 12px;
  padding: 2.5rem;
  width: 360px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
}
h1 {
  color: #e94560;
  margin: 0 0 0.5rem;
  font-size: 1.5rem;
}
p {
  color: #a0a0b0;
  margin: 0 0 1.5rem;
  font-size: 0.9rem;
}
input {
  display: block;
  width: 100%;
  padding: 0.75rem;
  margin-bottom: 1rem;
  border: 1px solid #2a2a4a;
  border-radius: 8px;
  background: #0f3460;
  color: #e0e0e0;
  font-size: 0.95rem;
  box-sizing: border-box;
}
input:focus {
  outline: none;
  border-color: #e94560;
}
button {
  width: 100%;
  padding: 0.75rem;
  background: #e94560;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 1rem;
  cursor: pointer;
  transition: background 0.2s;
}
button:hover { background: #c73652; }
button:disabled { opacity: 0.6; cursor: not-allowed; }
.error { color: #ff6b6b; margin-top: 0.5rem; font-size: 0.85rem; }
</style>
