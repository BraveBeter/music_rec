<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { favoritesApi } from '@/api/tracks'
import type { Track } from '@/types'

const favorites = ref<Track[]>([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await favoritesApi.list()
    favorites.value = data
  } catch (e) {
    console.error('Failed to load favorites:', e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="favorites-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">❤️ 我的收藏</h1>
      <p class="page-subtitle">你收藏的所有歌曲</p>
    </header>

    <div v-if="loading" class="loading-state">
      <div v-for="i in 5" :key="i" class="skeleton" style="width: 100%; height: 56px; margin-bottom: 4px;"></div>
    </div>

    <div v-else-if="favorites.length" class="track-list">
      <TrackCard
        v-for="track in favorites"
        :key="track.track_id"
        :track="track"
        :tracks="favorites"
      />
    </div>

    <div v-else class="empty-state">
      <p>还没有收藏任何歌曲</p>
      <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
    </div>
  </div>
</template>

<style scoped>
.favorites-page {
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--spacing-xl);
}

.page-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  margin-bottom: var(--spacing-xs);
}

.page-subtitle {
  color: var(--color-text-muted);
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--color-text-muted);
}

.empty-state p {
  margin-bottom: var(--spacing-lg);
  font-size: var(--font-size-lg);
}
</style>
