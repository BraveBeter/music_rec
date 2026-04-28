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
  <div class="favorites-page page-shell">
    <header class="page-hero animate-fade-in">
      <div class="page-hero-copy">
        <span class="page-kicker">Your Library</span>
        <h1 class="page-title">我的收藏</h1>
        <p class="page-subtitle">集中查看已保存的歌曲和歌手，视觉更统一，但数据和操作逻辑不变。</p>
      </div>

      <div class="page-actions">
        <span class="pill-tag">{{ trackFavorites.length }} Tracks</span>
        <span class="pill-tag">{{ artistFavorites.length }} Artists</span>
      </div>
    </header>

    <section class="section-block animate-slide-up">
      <div class="tab-bar">
        <button
          :class="['tab-btn', { active: activeTab === 'tracks' }]"
          @click="activeTab = 'tracks'"
        >
          歌曲
          <span class="tab-count">{{ trackFavorites.length }}</span>
        </button>
        <button
          :class="['tab-btn', { active: activeTab === 'artists' }]"
          @click="activeTab = 'artists'"
        >
          歌手
          <span class="tab-count">{{ artistFavorites.length }}</span>
        </button>
      </div>

      <div v-if="loading" class="row-list">
        <div v-for="i in 5" :key="i" class="skeleton skeleton-row"></div>
      </div>

      <template v-else-if="activeTab === 'tracks'">
        <div v-if="trackFavorites.length" class="row-list">
          <TrackCard
            v-for="track in trackFavorites"
            :key="track.track_id"
            :track="track"
            :tracks="trackFavorites"
          />
        </div>
        <div v-else class="empty-state">
          <p>还没有收藏任何歌曲。</p>
          <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
        </div>
      </template>

      <template v-else>
        <div v-if="artistFavorites.length" class="artist-grid">
          <ArtistCard
            v-for="artist in artistFavorites"
            :key="artist.artist_name"
            :artist="artist"
            :show-favorite="true"
          />
        </div>
        <div v-else class="empty-state">
          <p>还没有收藏任何歌手。</p>
          <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.tab-bar {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.03);
  box-shadow: var(--shadow-medium);
  margin-bottom: 1rem;
}

.tab-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  min-height: 40px;
  padding: 0 1rem;
  border-radius: 999px;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  transition:
    background-color var(--transition-fast),
    color var(--transition-fast);
}

.tab-btn.active {
  background: var(--color-bg-surface-strong);
  color: var(--color-text-base);
}

.tab-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 24px;
  height: 24px;
  padding: 0 0.4rem;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.06);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: normal;
}

.artist-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 0.875rem;
}

.skeleton-row {
  width: 100%;
  height: 78px;
}

@media (max-width: 768px) {
  .artist-grid {
    grid-template-columns: 1fr;
  }
}
</style>
