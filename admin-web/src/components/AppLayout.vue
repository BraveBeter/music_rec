<template>
  <div class="app-layout">
    <aside class="sidebar">
      <div class="sidebar-header">
        <h1 class="logo">MusicRec</h1>
        <span class="logo-sub">Admin</span>
      </div>
      <nav class="nav">
        <router-link to="/" class="nav-item" exact-active-class="active">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
          <span>Dashboard</span>
        </router-link>
        <router-link to="/import" class="nav-item" active-class="active">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><ellipse cx="12" cy="5" rx="9" ry="3"/><path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3"/><path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5"/></svg>
          <span>数据导入</span>
        </router-link>
        <router-link to="/training" class="nav-item" active-class="active">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
          <span>模型训练</span>
        </router-link>
        <router-link to="/scheduler" class="nav-item" active-class="active">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          <span>定时任务</span>
        </router-link>
        <router-link to="/models" class="nav-item" active-class="active">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
          <span>模型状态</span>
        </router-link>
      </nav>
      <div class="sidebar-footer">
        <div class="user-info">
          <span class="user-name">{{ auth.username }}</span>
          <button @click="auth.logout()" class="btn-logout">退出登录</button>
        </div>
      </div>
    </aside>
    <main class="main-content">
      <div class="content-wrapper">
        <router-view />
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
</script>

<style scoped>
.app-layout {
  display: flex;
  min-height: 100vh;
  background: #0d0d1a;
}

.sidebar {
  width: 220px;
  min-width: 220px;
  background: #0f0f23;
  border-right: 1px solid #1a1a3e;
  display: flex;
  flex-direction: column;
  position: fixed;
  top: 0;
  left: 0;
  bottom: 0;
  z-index: 100;
}

.sidebar-header {
  padding: 1.25rem 1.25rem 1rem;
  border-bottom: 1px solid #1a1a3e;
}

.logo {
  font-size: 1.2rem;
  font-weight: 700;
  color: #e94560;
  margin: 0;
  display: inline;
}

.logo-sub {
  font-size: 0.75rem;
  color: #a0a0b0;
  margin-left: 0.5rem;
  font-weight: 400;
}

.nav {
  flex: 1;
  padding: 0.75rem 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.65rem 1.25rem;
  color: #a0a0b0;
  text-decoration: none;
  font-size: 0.9rem;
  transition: all 0.15s;
  border-left: 3px solid transparent;
}

.nav-item:hover {
  color: #e0e0e0;
  background: rgba(255,255,255,0.03);
}

.nav-item.active {
  color: #e94560;
  background: rgba(233, 69, 96, 0.08);
  border-left-color: #e94560;
}

.sidebar-footer {
  padding: 1rem 1.25rem;
  border-top: 1px solid #1a1a3e;
}

.user-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.user-name {
  color: #a0a0b0;
  font-size: 0.85rem;
}

.btn-logout {
  background: none;
  border: 1px solid #3a3a5a;
  color: #a0a0b0;
  padding: 0.25rem 0.6rem;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.75rem;
  transition: all 0.15s;
}

.btn-logout:hover {
  border-color: #e94560;
  color: #e94560;
}

.main-content {
  flex: 1;
  margin-left: 220px;
  min-height: 100vh;
  background: #1a1a2e;
}

.content-wrapper {
  max-width: 1200px;
  margin: 0 auto;
  padding: 1.5rem 2rem;
  color: #e0e0e0;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
</style>
