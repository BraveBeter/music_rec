<script setup lang="ts">
import { ref, onMounted, watch, computed } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { tracksApi } from '@/api/tracks'
import { usePlayerStore } from '@/stores/player'
import type { Track, GenreTracksResponse } from '@/types'

const player = usePlayerStore()

// --- Search Section ---
const searchQuery = ref('')
const tracks = ref<Track[]>([])
const page = ref(1)
const total = ref(0)
const pageSize = 20
const loading = ref(false)

async function loadTracks() {
  loading.value = true
  try {
    const { data } = await tracksApi.list({
      query: searchQuery.value || undefined,
      page: page.value,
      page_size: pageSize,
    })
    tracks.value = data.items
    total.value = data.total
  } catch (e) {
    console.error('Failed to load tracks:', e)
  } finally {
    loading.value = false
  }
}

let searchTimeout: ReturnType<typeof setTimeout>
function onSearchInput() {
  clearTimeout(searchTimeout)
  searchTimeout = setTimeout(() => {
    page.value = 1
    loadTracks()
  }, 400)
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

// --- Genre Random Section ---
const genreRandom = ref<GenreTracksResponse | null>(null)
const genreRandomLoading = ref(false)

async function loadGenreRandom() {
  genreRandomLoading.value = true
  try {
    const { data } = await tracksApi.genreRandom(5)
    genreRandom.value = data
  } catch (e) {
    console.error('Failed to load genre random:', e)
  } finally {
    genreRandomLoading.value = false
  }
}

// --- Genre Ranking Section ---
const genreRanking = ref<GenreTracksResponse | null>(null)
const genreRankingLoading = ref(false)

async function loadGenreRanking() {
  genreRankingLoading.value = true
  try {
    const { data } = await tracksApi.genreRanking(5)
    genreRanking.value = data
  } catch (e) {
    console.error('Failed to load genre ranking:', e)
  } finally {
    genreRankingLoading.value = false
  }
}

// Compute the max tracks per genre row for ranking grid
const rankingMaxRows = computed(() => {
  if (!genreRanking.value) return 0
  return Math.max(...genreRanking.value.genres.map(g => g.tracks.length), 0)
})

// --- Init ---
onMounted(async () => {
  loadTracks()
  await Promise.all([loadGenreRandom(), loadGenreRanking()])
})

// Cover fallback
const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%231a1a2e" width="100" height="100"/><text x="50" y="55" text-anchor="middle" fill="%236366f1" font-size="40">♪</text></svg>'
</script>

<template>
  <div class="discover-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">发现音乐</h1>
      <p class="page-subtitle">探索海量曲库，找到你喜欢的音乐</p>
    </header>

    <!-- Search -->
    <section class="section animate-slide-up">
      <div class="search-bar">
        <span class="search-icon">🔍</span>
        <input
          v-model="searchQuery"
          @input="onSearchInput"
          type="text"
          placeholder="搜索歌曲、歌手或专辑..."
          class="search-input"
        />
      </div>
      <div v-if="searchQuery" class="results-section" :class="{ loading }">
        <div class="results-header">
          <span class="results-count" v-if="total">共 {{ total }} 首歌曲</span>
        </div>
        <div class="track-list">
          <TrackCard v-for="track in tracks" :key="track.track_id" :track="track" :tracks="tracks" />
        </div>
        <div v-if="tracks.length === 0 && !loading" class="empty-state"><p>没有找到匹配的歌曲</p></div>
        <div class="pagination" v-if="total > pageSize">
          <button class="btn-secondary" @click="prevPage" :disabled="page <= 1">← 上一页</button>
          <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
          <button class="btn-secondary" @click="nextPage" :disabled="page * pageSize >= total">下一页 →</button>
        </div>
      </div>
    </section>

    <!-- Genre Random Grid -->
    <section class="section animate-slide-up" style="animation-delay: 100ms">
      <div class="section-header">
        <h2 class="section-title">🎵 类型推荐</h2>
        <button class="btn-refresh" @click="loadGenreRandom" :disabled="genreRandomLoading" title="换一批">
          <span class="refresh-icon" :class="{ spinning: genreRandomLoading }">↻</span>
        </button>
      </div>

      <div v-if="genreRandomLoading" class="grid-skeleton">
        <div v-for="i in 4" :key="i" class="skeleton-col">
          <div class="skeleton skeleton-header" />
          <div v-for="j in 5" :key="j" class="skeleton skeleton-cell" />
        </div>
      </div>

      <div v-else-if="genreRandom?.genres.length" class="genre-grid-wrapper">
        <div class="genre-grid">
          <div v-for="g in genreRandom.genres" :key="g.genre" class="genre-col">
            <div class="genre-col-header">
              <span class="genre-dot" />
              <span class="genre-col-title">{{ g.genre }}</span>
            </div>
            <div class="genre-col-tracks">
              <div
                v-for="track in g.tracks"
                :key="track.track_id"
                class="genre-track-cell"
                @click="player.play(track, g.tracks)"
              >
                <img :src="track.cover_url || coverFallback" :alt="track.title" class="cell-cover" />
                <div class="cell-info">
                  <div class="cell-title">{{ track.title }}</div>
                  <div class="cell-artist">{{ track.artist_name || 'Unknown' }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Genre Ranking Grid -->
    <section class="section animate-slide-up" style="animation-delay: 200ms">
      <div class="section-header">
        <h2 class="section-title">🔥 类型热榜</h2>
      </div>

      <div v-if="genreRankingLoading" class="grid-skeleton">
        <div v-for="i in 4" :key="i" class="skeleton-col">
          <div class="skeleton skeleton-header" />
          <div v-for="j in 5" :key="j" class="skeleton skeleton-cell" />
        </div>
      </div>

      <div v-else-if="genreRanking?.genres.length" class="genre-grid-wrapper">
        <div class="genre-grid">
          <div v-for="g in genreRanking.genres" :key="g.genre" class="genre-col">
            <div class="genre-col-header ranking-header">
              <span class="genre-dot hot" />
              <span class="genre-col-title">{{ g.genre }}</span>
            </div>
            <div class="genre-col-tracks">
              <div
                v-for="(track, idx) in g.tracks"
                :key="track.track_id"
                class="genre-track-cell ranking-cell"
                @click="player.play(track, g.tracks)"
              >
                <span class="rank-badge" :class="{ gold: idx === 0, silver: idx === 1, bronze: idx === 2 }">{{ idx + 1 }}</span>
                <img :src="track.cover_url || coverFallback" :alt="track.title" class="cell-cover" />
                <div class="cell-info">
                  <div class="cell-title">{{ track.title }}</div>
                  <div class="cell-artist">{{ track.artist_name || 'Unknown' }}</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.discover-page {
  max-width: 1400px;
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

.section {
  margin-bottom: var(--spacing-2xl);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
}

.btn-refresh {
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all var(--transition-fast);
}

.btn-refresh:hover:not(:disabled) {
  border-color: var(--color-accent-primary);
  background: rgba(99, 102, 241, 0.1);
}

.btn-refresh:disabled { opacity: 0.5; cursor: not-allowed; }

.refresh-icon {
  font-size: 1.2rem;
  color: var(--color-text-secondary);
  display: inline-block;
  transition: transform 0.4s ease;
}

.refresh-icon.spinning {
  animation: spin 0.8s linear infinite;
}

/* ── Search ── */
.search-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md) var(--spacing-lg);
  transition: border-color var(--transition-fast);
}

.search-bar:focus-within {
  border-color: var(--color-accent-primary);
  box-shadow: 0 0 0 3px var(--color-accent-glow);
}

.search-icon { font-size: 1.2rem; }

.search-input {
  flex: 1;
  background: none;
  border: none;
  font-size: var(--font-size-base);
  padding: 0;
  outline: none;
}

.results-section.loading { opacity: 0.5; pointer-events: none; }
.results-header { margin: var(--spacing-md) 0; }
.results-count { font-size: var(--font-size-sm); color: var(--color-text-muted); }

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

.page-info { font-size: var(--font-size-sm); color: var(--color-text-muted); }
.empty-state { text-align: center; padding: var(--spacing-2xl); color: var(--color-text-muted); }

/* ── Genre Grid — the core layout ── */
.genre-grid-wrapper {
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: thin;
  padding-bottom: 4px;
}

.genre-grid {
  display: flex;
  gap: 1px;
  min-width: max-content;
  background: var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.genre-col {
  min-width: 240px;
  flex: 1;
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
}

.genre-col-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 14px 16px;
  background: rgba(99, 102, 241, 0.06);
  border-bottom: 1px solid var(--color-border);
  position: sticky;
  top: 0;
  z-index: 2;
}

.genre-col-header.ranking-header {
  background: rgba(236, 72, 153, 0.06);
}

.genre-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--color-accent-primary);
  box-shadow: 0 0 6px var(--color-accent-glow);
  flex-shrink: 0;
}

.genre-dot.hot {
  background: #ec4899;
  box-shadow: 0 0 6px rgba(236, 72, 153, 0.4);
}

.genre-col-title {
  font-size: 0.85rem;
  font-weight: 600;
  letter-spacing: 0.02em;
  color: var(--color-text-primary);
}

.genre-col-tracks {
  display: flex;
  flex-direction: column;
}

/* ── Track cell in grid ── */
.genre-track-cell {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 14px;
  cursor: pointer;
  transition: background var(--transition-fast);
  border-bottom: 1px solid rgba(255, 255, 255, 0.03);
  min-height: 52px;
}

.genre-track-cell:last-child {
  border-bottom: none;
}

.genre-track-cell:hover {
  background: var(--color-bg-card-hover);
}

.cell-cover {
  width: 36px;
  height: 36px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
}

.cell-info {
  flex: 1;
  min-width: 0;
}

.cell-title {
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-primary);
  line-height: 1.3;
}

.cell-artist {
  font-size: 0.68rem;
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}

/* ── Ranking badge ── */
.genre-track-cell.ranking-cell {
  gap: 8px;
}

.rank-badge {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 0.65rem;
  font-weight: 700;
  flex-shrink: 0;
  background: rgba(255, 255, 255, 0.06);
  color: var(--color-text-muted);
}

.rank-badge.gold {
  background: linear-gradient(135deg, #fbbf24, #f59e0b);
  color: #1a1a2e;
  box-shadow: 0 0 8px rgba(251, 191, 36, 0.3);
}

.rank-badge.silver {
  background: linear-gradient(135deg, #d1d5db, #9ca3af);
  color: #1a1a2e;
}

.rank-badge.bronze {
  background: linear-gradient(135deg, #f97316, #ea580c);
  color: #1a1a2e;
}

/* ── Skeleton loading ── */
.grid-skeleton {
  display: flex;
  gap: 1px;
  background: var(--color-border);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.skeleton-col {
  flex: 1;
  min-width: 200px;
  background: var(--color-bg-secondary);
  display: flex;
  flex-direction: column;
}

.skeleton-header {
  height: 44px;
  border-radius: 0;
}

.skeleton-cell {
  height: 52px;
  border-radius: 0;
  margin: 0;
}

@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}

/* ── Responsive ── */
@media (max-width: 900px) {
  .genre-col {
    min-width: 200px;
  }
}
</style>
