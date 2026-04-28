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
  <div class="auth-page page-shell">
    <div class="auth-layout animate-fade-in">
      <section class="auth-intro">
        <span class="page-kicker">MusicRec</span>
        <h1 class="auth-title">登录后继续你的听歌流。</h1>
        <p class="auth-copy">
          推荐、收藏和播放记录都会回到同一个近黑界面里，交互保持不变，只让浏览更沉浸。
        </p>
        <div class="auth-tags">
          <span class="pill-tag">Daily Mix</span>
          <span class="pill-tag pill-tag--accent">Play Ready</span>
        </div>
      </section>

      <section class="auth-card glass">
        <div class="auth-header">
          <span class="page-kicker">Sign In</span>
          <h2 class="auth-form-title">登录 MusicRec</h2>
          <p class="auth-subtitle">输入账号后即可继续浏览和播放。</p>
        </div>

        <form class="auth-form" @submit.prevent="handleLogin">
          <label class="form-group">
            <span>用户名</span>
            <input
              id="login-username"
              v-model="form.username"
              type="text"
              placeholder="请输入用户名"
              autocomplete="username"
            />
          </label>

          <label class="form-group">
            <span>密码</span>
            <input
              id="login-password"
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              autocomplete="current-password"
            />
          </label>

          <div v-if="error" class="error-msg">{{ error }}</div>

          <button type="submit" class="btn-primary auth-submit" :disabled="loading">
            {{ loading ? '登录中' : '登录' }}
          </button>
        </form>

        <div class="auth-footer">
          还没有账号？
          <router-link to="/register">立即注册</router-link>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.auth-page {
  min-height: calc(100vh - var(--player-height) - 3rem);
  display: flex;
  align-items: center;
}

.auth-layout {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(360px, 420px);
  gap: 1.25rem;
  align-items: stretch;
}

.auth-intro,
.auth-card {
  padding: 1.75rem;
  border-radius: 24px;
  box-shadow: var(--shadow-heavy);
}

.auth-intro {
  background:
    linear-gradient(180deg, rgba(45, 45, 45, 0.92), rgba(24, 24, 24, 0.98));
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 1rem;
}

.auth-title {
  font-family: var(--font-title);
  font-size: clamp(1.9rem, 3vw, 3.2rem);
  font-weight: 700;
  line-height: 0.95;
}

.auth-copy {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  max-width: 38ch;
}

.auth-tags {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.auth-header {
  margin-bottom: 1.25rem;
}

.auth-form-title {
  font-family: var(--font-title);
  font-size: 1.5rem;
  font-weight: 700;
  margin-top: 0.35rem;
}

.auth-subtitle {
  margin-top: 0.35rem;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.auth-form {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.4rem;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-weight: 700;
}

.error-msg {
  border-radius: 14px;
  padding: 0.75rem 0.875rem;
  background: rgba(243, 114, 127, 0.12);
  color: var(--color-text-negative);
  font-size: var(--font-size-xs);
}

.auth-submit {
  width: 100%;
  margin-top: 0.25rem;
}

.auth-footer {
  margin-top: 1rem;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

.auth-footer a {
  color: var(--color-text-base);
  font-weight: 700;
}

@media (max-width: 960px) {
  .auth-layout {
    grid-template-columns: 1fr;
  }

  .auth-intro {
    min-height: 220px;
  }
}
</style>
