<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const auth = useAuthStore()
const route = useRoute()

const navItems = computed(() => [
  { path: '/', label: '首页', icon: '⌂' },
  { path: '/discover', label: '发现', icon: '◌' },
  ...(auth.isLoggedIn
    ? [
        { path: '/favorites', label: '收藏', icon: '♥' },
        { path: '/profile', label: '我的', icon: '◎' },
      ]
    : []),
])

const sidebarMessage = computed(() =>
  auth.isLoggedIn
    ? '你的收藏、播放记录和推荐会随着账号一起保留。'
    : '登录后可以保存喜欢的歌曲，并持续获得更贴近你的推荐。'
)

function isActive(path: string) {
  return route.path === path
}
</script>

<template>
  <aside class="sidebar">
    <div class="sidebar-shell glass">
      <div class="sidebar-header">
        <div class="brand-mark" aria-hidden="true">
          <span></span>
          <span></span>
          <span></span>
        </div>
        <div class="brand-copy">
          <span class="brand-label">MusicRec</span>
          <strong class="brand-title">Daily listening</strong>
        </div>
      </div>

      <nav class="sidebar-nav" aria-label="主导航">
        <router-link
          v-for="item in navItems"
          :key="item.path"
          :to="item.path"
          :class="['nav-pill', { active: isActive(item.path) }]"
        >
          <span class="nav-icon" aria-hidden="true">{{ item.icon }}</span>
          <span class="nav-label">{{ item.label }}</span>
        </router-link>
      </nav>

      <section class="sidebar-library">
        <span class="sidebar-section">Listen now</span>
        <h2 class="sidebar-headline">沉浸式播放，不打断浏览</h2>
        <p class="sidebar-note">{{ sidebarMessage }}</p>
        <div class="sidebar-tags">
          <span class="pill-tag">For You</span>
          <span class="pill-tag pill-tag--accent">Play</span>
        </div>
      </section>

      <div class="sidebar-footer">
        <template v-if="auth.isLoggedIn">
          <div class="user-summary">
            <div class="user-avatar">
              {{ auth.user?.username?.charAt(0).toUpperCase() }}
            </div>
            <div class="user-meta">
              <strong class="user-name">{{ auth.user?.username }}</strong>
              <span class="user-role">
                {{ auth.user?.role === 'admin' ? 'Admin access' : 'Listener account' }}
              </span>
            </div>
          </div>
          <button class="btn-secondary sidebar-action" @click="auth.logout()">退出</button>
        </template>
        <template v-else>
          <router-link to="/login" class="btn-primary sidebar-action">登录</router-link>
        </template>
      </div>
    </div>

    <nav class="mobile-nav glass" aria-label="移动导航">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="['mobile-nav-item', { active: isActive(item.path) }]"
      >
        <span class="mobile-nav-icon" aria-hidden="true">{{ item.icon }}</span>
        <span class="mobile-nav-label">{{ item.label }}</span>
      </router-link>
      <button
        v-if="auth.isLoggedIn"
        class="mobile-auth-btn"
        type="button"
        aria-label="退出登录"
        @click="auth.logout()"
      >
        退
      </button>
      <router-link v-else to="/login" class="mobile-auth-btn" aria-label="登录">
        登
      </router-link>
    </nav>
  </aside>
</template>

<style scoped>
.sidebar {
  position: relative;
  z-index: 120;
}

.sidebar-shell {
  position: fixed;
  inset: 0 auto var(--player-height) 0;
  width: var(--sidebar-width);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  border-right: 1px solid rgba(255, 255, 255, 0.04);
}

.sidebar-header {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.25rem 0.125rem;
}

.brand-mark {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--color-accent);
  display: grid;
  place-items: center;
  gap: 2px;
  padding: 11px 12px;
  box-shadow: var(--shadow-medium);
}

.brand-mark span {
  display: block;
  width: 100%;
  height: 3px;
  border-radius: var(--radius-pill-full);
  background: #000000;
}

.brand-mark span:nth-child(2) {
  width: 72%;
}

.brand-mark span:nth-child(3) {
  width: 46%;
}

.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 0.18rem;
}

.brand-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.brand-title {
  font-family: var(--font-title);
  font-size: var(--font-size-lg);
  font-weight: 700;
  line-height: 1;
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}

.nav-pill {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-height: 48px;
  padding: 0 1rem;
  border-radius: var(--radius-pill-full);
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 700;
  transition:
    background-color var(--transition-fast),
    color var(--transition-fast),
    transform var(--transition-fast);
}

.nav-pill:hover {
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-base);
  transform: translateX(2px);
}

.nav-pill.active {
  background: var(--color-bg-surface-strong);
  color: var(--color-text-base);
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.04);
}

.nav-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  color: currentColor;
  font-size: 1rem;
}

.sidebar-library {
  padding: 1rem;
  border-radius: 18px;
  background:
    linear-gradient(180deg, rgba(39, 39, 39, 0.98), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-heavy);
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.sidebar-section {
  color: var(--color-text-secondary);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.sidebar-headline {
  font-family: var(--font-title);
  font-size: 1.125rem;
  font-weight: 700;
  line-height: 1.25;
}

.sidebar-note {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  line-height: 1.55;
}

.sidebar-tags {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.sidebar-footer {
  margin-top: auto;
  padding: 1rem;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.03);
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}

.user-summary {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.user-avatar {
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: linear-gradient(180deg, #2a2a2a 0%, #1a1a1a 100%);
  color: var(--color-accent);
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-base);
  font-weight: 700;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.06);
}

.user-meta {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.user-name {
  color: var(--color-text-base);
  font-size: var(--font-size-sm);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.user-role {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.sidebar-action {
  width: 100%;
}

.mobile-nav {
  display: none;
}

@media (max-width: 1024px) {
  .sidebar-shell {
    display: none;
  }

  .mobile-nav {
    position: fixed;
    left: 0.75rem;
    right: 0.75rem;
    bottom: calc(var(--player-height) + 0.75rem);
    display: grid;
    grid-template-columns: repeat(5, minmax(0, 1fr));
    align-items: center;
    gap: 0.375rem;
    min-height: var(--mobile-nav-height);
    padding: 0.5rem;
    border-radius: 999px;
    box-shadow: var(--shadow-heavy);
  }

  .mobile-nav-item,
  .mobile-auth-btn {
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.18rem;
    min-height: 48px;
    border-radius: 999px;
    color: var(--color-text-secondary);
    font-size: var(--font-size-micro);
    font-weight: 700;
  }

  .mobile-nav-item.active,
  .mobile-auth-btn {
    color: var(--color-text-base);
  }

  .mobile-nav-item.active {
    background: rgba(255, 255, 255, 0.06);
  }

  .mobile-nav-icon {
    font-size: 0.95rem;
    line-height: 1;
  }

  .mobile-auth-btn {
    background: var(--color-accent);
    color: #000000;
    flex-direction: row;
    font-size: var(--font-size-xs);
    letter-spacing: 0.12em;
    text-transform: uppercase;
  }
}
</style>
