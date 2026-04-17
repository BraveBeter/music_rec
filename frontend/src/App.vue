<script setup lang="ts">
import Sidebar from '@/components/layout/Sidebar.vue'
import PlayerBar from '@/components/player/PlayerBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useFavoritesStore } from '@/stores/favorites'
import { useArtistFavoritesStore } from '@/stores/artists'
import { onMounted } from 'vue'

const auth = useAuthStore()
const favStore = useFavoritesStore()
const artistFavStore = useArtistFavoritesStore()

onMounted(() => {
  // Restore favorites if user was already logged in (e.g. page refresh)
  if (auth.isLoggedIn) {
    if (!favStore.loaded) favStore.loadFavorites()
    if (!artistFavStore.loaded) artistFavStore.loadFavorites()
  }
})
</script>

<template>
  <div class="app-layout">
    <Sidebar />
    <main class="main-content">
      <router-view v-slot="{ Component }">
        <transition name="page" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
    <PlayerBar />
  </div>
</template>

<style scoped>
.page-enter-active,
.page-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}

.page-enter-from {
  opacity: 0;
  transform: translateY(8px);
}

.page-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
