<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue'
import { useAuthStore } from '@/stores/auth'
import apiClient from '@/api/client'
import { usersApi } from '@/api/tracks'

const auth = useAuthStore()

const profile = reactive({
  age: auth.user?.age ?? null,
  gender: auth.user?.gender ?? null,
  country: auth.user?.country ?? '',
})
const saving = ref(false)
const saved = ref(false)

const stats = reactive({
  play_count: null as number | null,
  favorites_count: null as number | null,
  days_registered: null as number | null,
})

onMounted(async () => {
  if (auth.isLoggedIn) {
    try {
      const { data } = await usersApi.stats()
      stats.play_count = data.play_count
      stats.favorites_count = data.favorites_count
      stats.days_registered = data.days_registered
    } catch (e) {
      console.error('Failed to load stats:', e)
    }
  }
})

async function saveProfile() {
  saving.value = true
  saved.value = false
  try {
    const { data } = await apiClient.put('/users/me/profile', {
      age: profile.age,
      gender: profile.gender,
      country: profile.country || null,
    })
    auth.setAuth(auth.accessToken!, data)
    saved.value = true
    setTimeout(() => { saved.value = false }, 2000)
  } catch (e) {
    console.error('Failed to save profile:', e)
  } finally {
    saving.value = false
  }
}

const genderLabels: Record<number, string> = { 0: '未指定', 1: '男', 2: '女' }
</script>

<template>
  <div class="profile-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">👤 个人中心</h1>
    </header>

    <div class="profile-card glass animate-slide-up">
      <div class="profile-avatar">
        {{ auth.user?.username?.charAt(0).toUpperCase() }}
      </div>
      <h2 class="profile-username">{{ auth.user?.username }}</h2>
      <span class="profile-role">{{ auth.user?.role === 'admin' ? '管理员' : '普通用户' }}</span>

      <form @submit.prevent="saveProfile" class="profile-form">
        <div class="form-group">
          <label for="profile-age">年龄</label>
          <input id="profile-age" v-model.number="profile.age" type="number" min="10" max="120" placeholder="年龄" />
        </div>

        <div class="form-group">
          <label for="profile-gender">性别</label>
          <select id="profile-gender" v-model="profile.gender">
            <option :value="null">未指定</option>
            <option :value="1">男</option>
            <option :value="2">女</option>
          </select>
        </div>

        <div class="form-group">
          <label for="profile-country">国家/地区</label>
          <input id="profile-country" v-model="profile.country" type="text" placeholder="例如: China" />
        </div>

        <button type="submit" class="btn-primary" :disabled="saving" style="width: 100%;">
          {{ saving ? '保存中...' : saved ? '✓ 已保存' : '保存修改' }}
        </button>
      </form>
    </div>

    <div class="profile-stats animate-slide-up" style="animation-delay: 100ms;">
      <div class="stat-card card">
        <div class="stat-value gradient-text">{{ stats.play_count ?? '--' }}</div>
        <div class="stat-label">播放次数</div>
      </div>
      <div class="stat-card card">
        <div class="stat-value gradient-text">{{ stats.favorites_count ?? '--' }}</div>
        <div class="stat-label">收藏歌曲</div>
      </div>
      <div class="stat-card card">
        <div class="stat-value gradient-text">{{ stats.days_registered ?? '--' }}</div>
        <div class="stat-label">注册天数</div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.profile-page {
  max-width: 600px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--spacing-xl);
}

.page-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
}

.profile-card {
  padding: var(--spacing-2xl);
  border-radius: var(--radius-xl);
  text-align: center;
  margin-bottom: var(--spacing-xl);
}

.profile-avatar {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-full);
  background: var(--color-accent-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-3xl);
  font-weight: 700;
  color: white;
  margin: 0 auto var(--spacing-md);
}

.profile-username {
  font-size: var(--font-size-xl);
  font-weight: 600;
  margin-bottom: var(--spacing-xs);
}

.profile-role {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  background: var(--color-bg-card);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
}

.profile-form {
  margin-top: var(--spacing-xl);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
  text-align: left;
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
}

.profile-stats {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--spacing-md);
}

.stat-card {
  text-align: center;
  padding: var(--spacing-lg);
}

.stat-value {
  font-size: var(--font-size-2xl);
  font-weight: 700;
}

.stat-label {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  margin-top: var(--spacing-xs);
}
</style>
