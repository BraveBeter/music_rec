<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import ArtistCard from '@/components/common/ArtistCard.vue'
import { favoritesApi } from '@/api/tracks'
import { artistsApi, type ArtistItem } from '@/api/artists'
import type { Track } from '@/types'

const activeTab = ref<'tracks' | 'artists'>('tracks')
const trackFavorites = ref<Track[]>([])
const artistFavorites = ref<ArtistItem[]>([])
const loading = ref(true)

async function loadTrackFavorites() {
  try {
    const { data } = await favoritesApi.list()
    trackFavorites.value = data
  } catch (e) {
    console.error('Failed to load track favorites:', e)
  }
}

async function loadArtistFavorites() {
  try {
    const { data } = await artistsApi.favorites()
    artistFavorites.value = data.items
  } catch (e) {
    console.error('Failed to load artist favorites:', e)
  }
}

onMounted(async () => {
  await Promise.all([loadTrackFavorites(), loadArtistFavorites()])
  loading.value = false
})
</script>

<template>
  <div class="favorites-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">❤️ 我的收藏</h1>
    </header>

    <!-- Tabs -->
    <div class="tabs">
      <button
        :class="['tab-btn', { active: activeTab === 'tracks' }]"
        @click="activeTab = 'tracks'"
      >
        歌曲 ({{ trackFavorites.length }})
      </button>
      <button
        :class="['tab-btn', { active: activeTab === 'artists' }]"
        @click="activeTab = 'artists'"
      >
        歌手 ({{ artistFavorites.length }})
      </button>
    </div>

    <div v-if="loading" class="loading-state">
      <div v-for="i in 5" :key="i" class="skeleton" style="width: 100%; height: 56px; margin-bottom: 4px;"></div>
    </div>

    <!-- Track favorites tab -->
    <template v-else-if="activeTab === 'tracks'">
      <div v-if="trackFavorites.length" class="track-list">
        <TrackCard
          v-for="track in trackFavorites"
          :key="track.track_id"
          :track="track"
          :tracks="trackFavorites"
        />
      </div>
      <div v-else class="empty-state">
        <p>还没有收藏任何歌曲</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>
    </template>

    <!-- Artist favorites tab -->
    <template v-else>
      <div v-if="artistFavorites.length" class="artist-list">
        <ArtistCard
          v-for="artist in artistFavorites"
          :key="artist.artist_name"
          :artist="artist"
          :show-favorite="true"
        />
      </div>
      <div v-else class="empty-state">
        <p>还没有收藏任何歌手</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>
    </template>
  </div>
</template>

<style scoped>
.favorites-page {
  max-width: 900px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--spacing-lg);
}

.page-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  margin-bottom: var(--spacing-xs);
}

.tabs {
  display: flex;
  gap: var(--spacing-sm);
  margin-bottom: var(--spacing-xl);
  border-bottom: 1px solid var(--color-border);
  padding-bottom: var(--spacing-sm);
}

.tab-btn {
  padding: var(--spacing-sm) var(--spacing-lg);
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: var(--font-size-sm);
  font-weight: 500;
  cursor: pointer;
  border-radius: var(--radius-md) var(--radius-md) 0 0;
  transition: all var(--transition-fast);
  position: relative;
}

.tab-btn:hover {
  color: var(--color-text-primary);
}

.tab-btn.active {
  color: var(--color-accent-primary);
}

.tab-btn.active::after {
  content: '';
  position: absolute;
  bottom: -5px;
  left: 0;
  right: 0;
  height: 2px;
  background: var(--color-accent-primary);
  border-radius: 2px;
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.artist-list {
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
