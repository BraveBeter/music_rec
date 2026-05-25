<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
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

function syncProfileForm() {
  profile.age = auth.user?.age ?? null
  profile.gender = auth.user?.gender ?? null
  profile.country = auth.user?.country ?? ''
}

watch(() => auth.user, syncProfileForm, { immediate: true, deep: true })

onMounted(async () => {
  if (auth.isLoggedIn) {
    try {
      await auth.loadProfile()
    } catch (e) {
      console.error('Failed to load profile:', e)
    }

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
    setTimeout(() => {
      saved.value = false
    }, 2000)
  } catch (e) {
    console.error('Failed to save profile:', e)
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="profile-page page-shell">
    <header class="page-hero animate-fade-in">
      <div class="profile-hero-copy">
        <div class="profile-avatar">
          {{ auth.user?.username?.charAt(0).toUpperCase() }}
        </div>
        <div class="page-hero-copy">
          <span class="page-kicker">Profile</span>
          <h1 class="page-title">{{ auth.user?.username }}</h1>
          <p class="page-subtitle">
            {{ auth.user?.role === 'admin' ? '管理员账号' : '普通用户账号' }}，可在此维护个人资料并查看使用概况。
          </p>
        </div>
      </div>

      <div class="page-actions">
        <span class="pill-tag">{{ auth.user?.role === 'admin' ? 'Admin' : 'Listener' }}</span>
      </div>
    </header>

    <div class="profile-layout animate-slide-up">
      <section class="content-panel profile-panel">
        <div class="section-top">
          <div>
            <h2 class="section-heading">个人资料</h2>
            <p class="section-copy">只调整展示层，不改变保存行为和字段结构。</p>
          </div>
        </div>

        <form class="profile-form" @submit.prevent="saveProfile">
          <label class="form-group">
            <span>年龄</span>
            <input id="profile-age" v-model.number="profile.age" type="number" min="10" max="120" placeholder="年龄" />
          </label>

          <label class="form-group">
            <span>性别</span>
            <select id="profile-gender" v-model="profile.gender">
              <option :value="null">未指定</option>
              <option :value="1">男</option>
              <option :value="2">女</option>
            </select>
          </label>

          <label class="form-group">
            <span>国家 / 地区</span>
            <input id="profile-country" v-model="profile.country" type="text" placeholder="例如 China" />
          </label>

          <button type="submit" class="btn-primary profile-submit" :disabled="saving">
            {{ saving ? '保存中' : saved ? '已保存' : '保存修改' }}
          </button>
        </form>
      </section>

      <section class="stats-panel">
        <router-link to="/history" class="stat-card">
          <span class="stat-kicker">History</span>
          <strong class="stat-value">{{ stats.play_count ?? '--' }}</strong>
          <span class="stat-label">播放次数</span>
        </router-link>

        <router-link to="/favorites" class="stat-card">
          <span class="stat-kicker">Favorites</span>
          <strong class="stat-value">{{ stats.favorites_count ?? '--' }}</strong>
          <span class="stat-label">收藏歌曲</span>
        </router-link>

        <div class="stat-card">
          <span class="stat-kicker">Days</span>
          <strong class="stat-value">{{ stats.days_registered ?? '--' }}</strong>
          <span class="stat-label">注册天数</span>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.profile-hero-copy {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-width: 0;
}

.profile-avatar {
  width: 84px;
  height: 84px;
  border-radius: 50%;
  background: linear-gradient(180deg, #2a2a2a 0%, #171717 100%);
  color: var(--color-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.8rem;
  font-weight: 700;
  flex-shrink: 0;
  box-shadow: var(--shadow-heavy);
}

.profile-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.9fr);
  gap: 1rem;
}

.profile-panel {
  padding: 1.25rem;
}

.profile-form {
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
  letter-spacing: 0.04em;
}

.profile-submit {
  width: 100%;
  margin-top: 0.25rem;
}

.stats-panel {
  display: grid;
  gap: 1rem;
}

.stat-card {
  padding: 1.25rem;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(37, 37, 37, 0.98), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-heavy);
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast);
}

.stat-card:hover {
  transform: translateY(-1px);
  background: linear-gradient(180deg, rgba(45, 45, 45, 1), rgba(31, 31, 31, 1));
}

.stat-kicker {
  color: var(--color-text-secondary);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.stat-value {
  color: var(--color-text-base);
  font-family: var(--font-title);
  font-size: 2rem;
  font-weight: 700;
  line-height: 1;
}

.stat-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
}

@media (max-width: 960px) {
  .profile-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 768px) {
  .profile-hero-copy {
    align-items: flex-start;
  }

  .profile-avatar {
    width: 72px;
    height: 72px;
    font-size: 1.5rem;
  }
}
</style>
