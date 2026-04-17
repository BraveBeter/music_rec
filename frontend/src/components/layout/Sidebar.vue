<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
import { useRoute } from 'vue-router'
import { computed } from 'vue'

const auth = useAuthStore()
const route = useRoute()

const navItems = computed(() => [
  { path: '/', label: '首页', icon: '🏠' },
  { path: '/discover', label: '发现', icon: '🔍' },
  ...(auth.isLoggedIn
    ? [
        { path: '/favorites', label: '我的收藏', icon: '❤️' },
        { path: '/history', label: '播放历史', icon: '🕐' },
        { path: '/profile', label: '个人中心', icon: '👤' },
      ]
    : []),
])

function isActive(path: string) {
  return route.path === path
}
</script>

<template>
  <aside class="sidebar glass">
    <div class="sidebar-header">
      <div class="logo">
        <span class="logo-icon">🎵</span>
        <span class="logo-text gradient-text">MusicRec</span>
      </div>
    </div>

    <nav class="sidebar-nav">
      <router-link
        v-for="item in navItems"
        :key="item.path"
        :to="item.path"
        :class="['nav-item', { active: isActive(item.path) }]"
      >
        <span class="nav-icon">{{ item.icon }}</span>
        <span class="nav-label">{{ item.label }}</span>
      </router-link>
    </nav>

    <div class="sidebar-footer">
      <template v-if="auth.isLoggedIn">
        <div class="user-info">
          <div class="user-avatar">{{ auth.user?.username?.charAt(0).toUpperCase() }}</div>
          <span class="user-name">{{ auth.user?.username }}</span>
        </div>
        <button class="btn-secondary btn-sm" @click="auth.logout()">退出</button>
      </template>
      <template v-else>
        <router-link to="/login" class="btn-primary btn-sm" style="width: 100%; text-align: center;">登录</router-link>
      </template>
    </div>
  </aside>
</template>

<style scoped>
.sidebar {
  position: fixed;
  left: 0;
  top: 0;
  bottom: var(--player-height);
  width: var(--sidebar-width);
  display: flex;
  flex-direction: column;
  z-index: 100;
  border-right: 1px solid var(--color-border);
}

.sidebar-header {
  padding: var(--spacing-lg) var(--spacing-lg) var(--spacing-md);
}

.logo {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.logo-icon {
  font-size: 1.5rem;
}

.logo-text {
  font-size: var(--font-size-xl);
  font-weight: 700;
}

.sidebar-nav {
  flex: 1;
  padding: var(--spacing-sm) var(--spacing-sm);
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  transition: all var(--transition-fast);
  text-decoration: none;
}

.nav-item:hover {
  background: var(--color-bg-card-hover);
  color: var(--color-text-primary);
}

.nav-item.active {
  background: rgba(99, 102, 241, 0.15);
  color: var(--color-accent-primary);
}

.nav-icon {
  font-size: 1.2rem;
  width: 24px;
  text-align: center;
}

.sidebar-footer {
  padding: var(--spacing-md) var(--spacing-lg);
  border-top: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.user-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.user-avatar {
  width: 32px;
  height: 32px;
  border-radius: var(--radius-full);
  background: var(--color-accent-gradient);
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 700;
  font-size: var(--font-size-sm);
  color: white;
}

.user-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  color: var(--color-text-primary);
}

.btn-sm {
  padding: 0.4rem 0.75rem;
  font-size: var(--font-size-xs);
}

@media (max-width: 768px) {
  .sidebar {
    display: none;
  }
}
</style>
