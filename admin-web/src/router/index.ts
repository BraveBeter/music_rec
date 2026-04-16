import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import Login from '@/views/Login.vue'
import AppLayout from '@/components/AppLayout.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: Login },
    {
      path: '/',
      component: AppLayout,
      meta: { requiresAuth: true },
      children: [
        { path: '', name: 'dashboard', component: () => import('@/views/Dashboard.vue') },
        { path: 'import', name: 'data-import', component: () => import('@/views/DataImport.vue') },
        { path: 'training', name: 'training', component: () => import('@/views/Training.vue') },
        { path: 'scheduler', name: 'scheduler', component: () => import('@/views/Scheduler.vue') },
        { path: 'models', name: 'models', component: () => import('@/views/Models.vue') },
      ],
    },
  ],
})

router.beforeEach((to) => {
  const auth = useAuthStore()
  // Check if any matched route requires auth
  const requiresAuth = to.matched.some(r => r.meta.requiresAuth)
  if (requiresAuth && !auth.isAuthenticated()) {
    return { name: 'login' }
  }
  if (to.name === 'login' && auth.isAuthenticated()) {
    return { name: 'dashboard' }
  }
})

export default router
