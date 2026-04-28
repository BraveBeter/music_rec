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
  <div class="auth-page page-shell">
    <div class="auth-layout animate-fade-in">
      <section class="auth-intro">
        <span class="page-kicker">Create Account</span>
        <h1 class="auth-title">把偏好、收藏和推荐留在同一个账号里。</h1>
        <p class="auth-copy">
          注册后即可获得个性化推荐，并用更一致的播放器界面持续浏览、收藏和回放喜欢的音乐。
        </p>
        <div class="auth-tags">
          <span class="pill-tag">Library</span>
          <span class="pill-tag">Profile</span>
          <span class="pill-tag pill-tag--accent">Recommendations</span>
        </div>
      </section>

      <section class="auth-card glass">
        <div class="auth-header">
          <span class="page-kicker">Sign Up</span>
          <h2 class="auth-form-title">注册 MusicRec</h2>
          <p class="auth-subtitle">创建账号后即可进入首页开始个性化浏览。</p>
        </div>

        <form class="auth-form" @submit.prevent="handleRegister">
          <label class="form-group">
            <span>用户名 *</span>
            <input id="reg-username" v-model="form.username" type="text" placeholder="请输入用户名" />
          </label>

          <label class="form-group">
            <span>密码 *</span>
            <input id="reg-password" v-model="form.password" type="password" placeholder="至少 6 个字符" />
          </label>

          <label class="form-group">
            <span>确认密码 *</span>
            <input id="reg-confirm" v-model="form.confirmPassword" type="password" placeholder="再次输入密码" />
          </label>

          <div class="form-row">
            <label class="form-group">
              <span>年龄</span>
              <input id="reg-age" v-model.number="form.age" type="number" min="10" max="120" placeholder="年龄" />
            </label>

            <label class="form-group">
              <span>性别</span>
              <select id="reg-gender" v-model="form.gender">
                <option :value="null">不指定</option>
                <option :value="1">男</option>
                <option :value="2">女</option>
              </select>
            </label>
          </div>

          <label class="form-group">
            <span>国家 / 地区</span>
            <input id="reg-country" v-model="form.country" type="text" placeholder="例如 China" />
          </label>

          <div v-if="error" class="error-msg">{{ error }}</div>

          <button type="submit" class="btn-primary auth-submit" :disabled="loading">
            {{ loading ? '注册中' : '立即注册' }}
          </button>
        </form>

        <div class="auth-footer">
          已有账号？
          <router-link to="/login">去登录</router-link>
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
  grid-template-columns: minmax(0, 1.05fr) minmax(360px, 460px);
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
  font-size: clamp(1.85rem, 2.8vw, 3rem);
  font-weight: 700;
  line-height: 0.98;
}

.auth-copy {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  line-height: 1.6;
  max-width: 42ch;
}

.auth-tags {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.auth-header {
  margin-bottom: 1.1rem;
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

.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.875rem;
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

@media (max-width: 640px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}
</style>
