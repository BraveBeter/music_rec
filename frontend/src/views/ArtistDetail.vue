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
  <div class="artist-page page-shell">
    <header class="artist-hero page-hero animate-fade-in">
      <div class="artist-summary">
        <div class="artist-avatar">
          <img
            v-if="tracks.length > 0 && tracks[0].cover_url"
            :src="tracks[0].cover_url"
            :alt="artistName"
          />
          <span v-else class="artist-avatar-fallback">A</span>
        </div>

        <div class="page-hero-copy">
          <span class="page-kicker">Artist Spotlight</span>
          <h1 class="page-title">{{ artistName }}</h1>
          <p class="page-subtitle">共收录 {{ total }} 首歌曲，可直接从下方列表接入播放器。</p>
        </div>
      </div>

      <div class="page-actions">
        <span class="pill-tag">{{ total }} Tracks</span>
        <button
          v-if="auth.isLoggedIn"
          :class="['artist-fav-btn', { active: artistFav.isFavorited(artistName) }]"
          @click="toggleFavorite"
        >
          {{ artistFav.isFavorited(artistName) ? '已收藏' : '收藏歌手' }}
        </button>
      </div>
    </header>

    <section class="section-block animate-slide-up">
      <div class="section-top">
        <div>
          <h2 class="section-heading">热门曲目</h2>
          <p class="section-copy">不改变数据逻辑，只重排信息层级，便于快速开播。</p>
        </div>
      </div>

      <div v-if="loading" class="row-list">
        <div v-for="i in 6" :key="i" class="skeleton skeleton-row"></div>
      </div>

      <template v-else>
        <div v-if="tracks.length" class="row-list">
          <TrackCard
            v-for="track in tracks"
            :key="track.track_id"
            :track="track"
            :tracks="tracks"
          />
        </div>

        <div v-else class="empty-state">
          <p>该歌手暂无曲目。</p>
        </div>

        <div class="pagination" v-if="total > pageSize">
          <button class="btn-secondary" :disabled="page <= 1" @click="prevPage">上一页</button>
          <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
          <button class="btn-secondary" :disabled="page * pageSize >= total" @click="nextPage">下一页</button>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.artist-hero {
  align-items: center;
}

.artist-summary {
  display: flex;
  align-items: center;
  gap: 1rem;
  min-width: 0;
}

.artist-avatar {
  width: 92px;
  height: 92px;
  border-radius: 50%;
  overflow: hidden;
  background: linear-gradient(180deg, #2a2a2a 0%, #1a1a1a 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  box-shadow: var(--shadow-heavy);
}

.artist-avatar img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.artist-avatar-fallback {
  color: var(--color-accent);
  font-size: 2rem;
  font-weight: 700;
}

.artist-fav-btn {
  min-height: 42px;
  padding: 0 1.2rem;
  border-radius: var(--radius-pill-full);
  background: transparent;
  color: var(--color-text-base);
  font-size: var(--font-size-xs);
  font-weight: 700;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  box-shadow: inset 0 0 0 1px var(--color-border-light);
  transition:
    transform var(--transition-fast),
    color var(--transition-fast),
    box-shadow var(--transition-fast),
    background-color var(--transition-fast);
}

.artist-fav-btn:hover {
  transform: translateY(-1px);
  box-shadow: inset 0 0 0 1px var(--color-accent-border);
}

.artist-fav-btn.active {
  background: var(--color-accent-soft);
  color: var(--color-accent);
  box-shadow: inset 0 0 0 1px rgba(30, 215, 96, 0.25);
}

.skeleton-row {
  width: 100%;
  height: 80px;
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  margin-top: 1rem;
}

.page-info {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

@media (max-width: 768px) {
  .artist-summary {
    align-items: flex-start;
  }

  .artist-avatar {
    width: 76px;
    height: 76px;
  }
}
</style>
