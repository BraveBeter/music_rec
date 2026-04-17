<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import TrackCard from '@/components/common/TrackCard.vue'
import { artistsApi } from '@/api/artists'
import { useArtistFavoritesStore } from '@/stores/artists'
import { useAuthStore } from '@/stores/auth'
import type { Track } from '@/types'

const route = useRoute()
const artistFav = useArtistFavoritesStore()
const auth = useAuthStore()

const artistName = decodeURIComponent(route.params.name as string)
const tracks = ref<Track[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20
const loading = ref(false)

async function loadTracks() {
  loading.value = true
  try {
    const { data } = await artistsApi.tracks(artistName, page.value, pageSize)
    tracks.value = data.items
    total.value = data.total
  } catch (e) {
    console.error('Failed to load artist tracks:', e)
  } finally {
    loading.value = false
  }
}

async function toggleFavorite() {
  if (!auth.isLoggedIn) return
  await artistFav.toggleFavorite(artistName)
}

function nextPage() {
  if (page.value * pageSize < total.value) {
    page.value++
    loadTracks()
  }
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadTracks()
  }
}

onMounted(() => {
  loadTracks()
  if (auth.isLoggedIn && !artistFav.loaded) {
    artistFav.loadFavorites()
  }
})
</script>

<template>
  <div class="artist-page">
    <header class="artist-header animate-fade-in">
      <div class="artist-avatar">
        <img
          v-if="tracks.length > 0 && tracks[0].cover_url"
          :src="tracks[0].cover_url"
          :alt="artistName"
        />
        <span v-else class="avatar-placeholder">🎤</span>
      </div>
      <div class="artist-meta">
        <h1 class="artist-name gradient-text">{{ artistName }}</h1>
        <p class="artist-stats">{{ total }} 首歌曲</p>
      </div>
      <button
        v-if="auth.isLoggedIn"
        :class="['btn-fav', { active: artistFav.isFavorited(artistName) }]"
        @click="toggleFavorite"
      >
        {{ artistFav.isFavorited(artistName) ? '❤️ 已收藏' : '🤍 收藏歌手' }}
      </button>
    </header>

    <section class="section animate-slide-up">
      <div v-if="loading" class="loading-state">
        <div v-for="i in 6" :key="i" class="skeleton skeleton-row" />
      </div>

      <template v-else>
        <div v-if="tracks.length === 0" class="empty-state">
          <p>该歌手暂无曲目</p>
        </div>
        <template v-else>
          <div class="track-list">
            <TrackCard
              v-for="track in tracks"
              :key="track.track_id"
              :track="track"
              :tracks="tracks"
            />
          </div>

          <div class="pagination" v-if="total > pageSize">
            <button class="btn-secondary" @click="prevPage" :disabled="page <= 1">← 上一页</button>
            <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
            <button class="btn-secondary" @click="nextPage" :disabled="page * pageSize >= total">下一页 →</button>
          </div>
        </template>
      </template>
    </section>
  </div>
</template>

<style scoped>
.artist-page {
  max-width: 900px;
  margin: 0 auto;
}

.artist-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  margin-bottom: var(--spacing-2xl);
  padding: var(--spacing-xl);
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
}

.artist-avatar {
  width: 80px;
  height: 80px;
  border-radius: var(--radius-full);
  overflow: hidden;
  flex-shrink: 0;
  background: var(--color-bg-secondary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.artist-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.avatar-placeholder {
  font-size: 2rem;
}

.artist-meta {
  flex: 1;
}

.artist-name {
  font-size: var(--font-size-2xl);
  font-weight: 700;
  margin-bottom: var(--spacing-xs);
}

.artist-stats {
  color: var(--color-text-muted);
  font-size: var(--font-size-sm);
}

.btn-fav {
  padding: var(--spacing-sm) var(--spacing-lg);
  border-radius: var(--radius-full);
  border: 1px solid var(--color-border);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  font-size: var(--font-size-sm);
  transition: all var(--transition-fast);
  white-space: nowrap;
}

.btn-fav:hover {
  border-color: var(--color-accent-primary);
}

.btn-fav.active {
  border-color: #ef4444;
  color: #ef4444;
  background: rgba(239, 68, 68, 0.1);
}

.section {
  margin-bottom: var(--spacing-2xl);
}

.loading-state {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.skeleton-row {
  height: 64px;
  border-radius: var(--radius-md);
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: var(--spacing-lg);
  margin-top: var(--spacing-xl);
}

.page-info {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--color-text-muted);
}
</style>
