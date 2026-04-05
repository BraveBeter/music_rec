<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const form = reactive({
  username: '',
  password: '',
})
const loading = ref(false)
const error = ref('')

async function handleLogin() {
  if (!form.username || !form.password) {
    error.value = '请输入用户名和密码'
    return
  }
  loading.value = true
  error.value = ''
  try {
    await auth.login(form.username, form.password)
    const redirect = (route.query.redirect as string) || '/'
    router.push(redirect)
  } catch (e: any) {
    error.value = e.response?.data?.msg || '登录失败，请检查用户名和密码'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-container animate-fade-in">
      <div class="auth-card glass">
        <div class="auth-header">
          <span class="auth-logo">🎵</span>
          <h1 class="gradient-text">登录 MusicRec</h1>
          <p class="auth-subtitle">发现属于你的音乐世界</p>
        </div>

        <form @submit.prevent="handleLogin" class="auth-form">
          <div class="form-group">
            <label for="login-username">用户名</label>
            <input
              id="login-username"
              v-model="form.username"
              type="text"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </div>

          <div class="form-group">
            <label for="login-password">密码</label>
            <input
              id="login-password"
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
            />
          </div>

          <div v-if="error" class="error-msg">{{ error }}</div>

          <button type="submit" class="btn-primary auth-submit" :disabled="loading">
            {{ loading ? '登录中...' : '登录' }}
          </button>
        </form>

        <div class="auth-footer">
          还没有账号？ <router-link to="/register">立即注册</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: calc(100vh - var(--player-height));
  padding: var(--spacing-xl);
}

.auth-container {
  width: 100%;
  max-width: 420px;
}

.auth-card {
  padding: var(--spacing-2xl);
  border-radius: var(--radius-xl);
}

.auth-header {
  text-align: center;
  margin-bottom: var(--spacing-2xl);
}

.auth-logo {
  font-size: 3rem;
  display: block;
  margin-bottom: var(--spacing-md);
}

.auth-header h1 {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  margin-bottom: var(--spacing-xs);
}

.auth-subtitle {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-lg);
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xs);
}

.form-group label {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-secondary);
}

.form-group input {
  padding: 0.75rem var(--spacing-md);
  font-size: var(--font-size-base);
}

.error-msg {
  color: var(--color-error);
  font-size: var(--font-size-sm);
  text-align: center;
  padding: var(--spacing-sm);
  background: rgba(239, 68, 68, 0.1);
  border-radius: var(--radius-sm);
}

.auth-submit {
  width: 100%;
  padding: 0.85rem;
  font-size: var(--font-size-base);
  margin-top: var(--spacing-sm);
}

.auth-submit:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.auth-footer {
  text-align: center;
  margin-top: var(--spacing-lg);
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}
</style>
