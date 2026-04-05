<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()
const router = useRouter()

const form = reactive({
  username: '',
  password: '',
  confirmPassword: '',
  age: null as number | null,
  gender: null as number | null,
  country: '',
})
const loading = ref(false)
const error = ref('')

async function handleRegister() {
  if (!form.username || !form.password) {
    error.value = '请填写必填字段'
    return
  }
  if (form.password.length < 6) {
    error.value = '密码至少6个字符'
    return
  }
  if (form.password !== form.confirmPassword) {
    error.value = '两次密码不一致'
    return
  }

  loading.value = true
  error.value = ''
  try {
    await auth.register(form.username, form.password, {
      age: form.age || undefined,
      gender: form.gender ?? undefined,
      country: form.country || undefined,
    })
    router.push('/')
  } catch (e: any) {
    error.value = e.response?.data?.msg || '注册失败'
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
          <h1 class="gradient-text">注册 MusicRec</h1>
          <p class="auth-subtitle">创建账号，开启个性化音乐之旅</p>
        </div>

        <form @submit.prevent="handleRegister" class="auth-form">
          <div class="form-group">
            <label for="reg-username">用户名 *</label>
            <input id="reg-username" v-model="form.username" type="text" placeholder="请输入用户名" />
          </div>

          <div class="form-group">
            <label for="reg-password">密码 *</label>
            <input id="reg-password" v-model="form.password" type="password" placeholder="至少6个字符" />
          </div>

          <div class="form-group">
            <label for="reg-confirm">确认密码 *</label>
            <input id="reg-confirm" v-model="form.confirmPassword" type="password" placeholder="再次输入密码" />
          </div>

          <div class="form-row">
            <div class="form-group">
              <label for="reg-age">年龄</label>
              <input id="reg-age" v-model.number="form.age" type="number" placeholder="年龄" min="10" max="120" />
            </div>
            <div class="form-group">
              <label for="reg-gender">性别</label>
              <select id="reg-gender" v-model="form.gender">
                <option :value="null">不指定</option>
                <option :value="1">男</option>
                <option :value="2">女</option>
              </select>
            </div>
          </div>

          <div class="form-group">
            <label for="reg-country">国家/地区</label>
            <input id="reg-country" v-model="form.country" type="text" placeholder="例如: China" />
          </div>

          <div v-if="error" class="error-msg">{{ error }}</div>

          <button type="submit" class="btn-primary auth-submit" :disabled="loading">
            {{ loading ? '注册中...' : '立即注册' }}
          </button>
        </form>

        <div class="auth-footer">
          已有账号？ <router-link to="/login">去登录</router-link>
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
  margin-bottom: var(--spacing-xl);
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
  gap: var(--spacing-md);
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

.form-group input,
.form-group select {
  padding: 0.65rem var(--spacing-md);
  font-size: var(--font-size-sm);
}

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--spacing-md);
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
