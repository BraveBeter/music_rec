<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import GenreTabs from '@/components/common/GenreTabs.vue'
import { tracksApi } from '@/api/tracks'
import type { Track, GenreTracksResponse } from '@/types'

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
const selectedGenre = ref('')

async function loadGenreRanking() {
  genreRankingLoading.value = true
  try {
    const { data } = await tracksApi.genreRanking(10)
    genreRanking.value = data
    if (data.genres.length > 0 && !selectedGenre.value) {
      selectedGenre.value = data.genres[0].genre
    }
  } catch (e) {
    console.error('Failed to load genre ranking:', e)
  } finally {
    genreRankingLoading.value = false
  }
}

const rankingTracks = ref<Track[]>([])
watch(selectedGenre, () => {
  if (!genreRanking.value) return
  const found = genreRanking.value.genres.find(g => g.genre === selectedGenre.value)
  rankingTracks.value = found ? found.tracks : []
})

// --- Init ---
onMounted(async () => {
  loadTracks()
  const [, rankRes] = await Promise.all([
    loadGenreRandom(),
    loadGenreRanking(),
  ])
  // trigger initial ranking display
  if (genreRanking.value?.genres.length) {
    selectedGenre.value = genreRanking.value.genres[0].genre
  }
})
</script>

<template>
  <div class="discover-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">发现音乐</h1>
      <p class="page-subtitle">探索海量曲库，找到你喜欢的音乐</p>
    </header>

    <!-- Section 1: Search -->
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
          <TrackCard
            v-for="track in tracks"
            :key="track.track_id"
            :track="track"
            :tracks="tracks"
          />
        </div>
        <div v-if="tracks.length === 0 && !loading" class="empty-state">
          <p>没有找到匹配的歌曲</p>
        </div>
        <div class="pagination" v-if="total > pageSize">
          <button class="btn-secondary" @click="prevPage" :disabled="page <= 1">← 上一页</button>
          <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
          <button class="btn-secondary" @click="nextPage" :disabled="page * pageSize >= total">下一页 →</button>
        </div>
      </div>
    </section>

    <!-- Section 2: Genre Random -->
    <section class="section animate-slide-up" style="animation-delay: 100ms">
      <div class="section-header">
        <h2 class="section-title">🎵 类型推荐</h2>
        <button class="btn-refresh" @click="loadGenreRandom" :disabled="genreRandomLoading" title="换一批">
          ↻
        </button>
      </div>

      <div v-if="genreRandomLoading" class="loading-skeletons">
        <div v-for="i in 3" :key="i" class="skeleton skeleton-row" />
      </div>

      <div v-else-if="genreRandom?.genres.length" class="genre-sections">
        <div v-for="g in genreRandom.genres" :key="g.genre" class="genre-section">
          <h3 class="genre-label">{{ g.genre }}</h3>
          <div class="genre-tracks-scroll">
            <TrackCard
              v-for="track in g.tracks"
              :key="track.track_id"
              :track="track"
              :tracks="g.tracks"
              class="genre-track-card"
            />
          </div>
        </div>
      </div>
    </section>

    <!-- Section 3: Genre Ranking -->
    <section class="section animate-slide-up" style="animation-delay: 200ms">
      <div class="section-header">
        <h2 class="section-title">🔥 类型热榜</h2>
      </div>

      <div v-if="genreRankingLoading" class="loading-skeletons">
        <div v-for="i in 5" :key="i" class="skeleton skeleton-row" />
      </div>

      <template v-else-if="genreRanking?.genres.length">
        <GenreTabs
          :genres="genreRanking.genres.map(g => g.genre)"
          v-model="selectedGenre"
        />
        <div class="track-list">
          <div
            v-for="(track, index) in rankingTracks"
            :key="track.track_id"
            class="track-list-item"
          >
            <span class="rank-number" :class="{ 'top-3': index < 3 }">{{ index + 1 }}</span>
            <TrackCard :track="track" :tracks="rankingTracks" />
          </div>
        </div>
      </template>
    </section>
  </div>
</template>

<style scoped>
.discover-page {
  max-width: 1200px;
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
  background: none;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-full);
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  font-size: 1.2rem;
  color: var(--color-text-secondary);
  transition: all var(--transition-fast);
}

.btn-refresh:hover:not(:disabled) {
  border-color: var(--color-accent-primary);
  color: var(--color-accent-primary);
}

.btn-refresh:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Search */
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

.search-icon {
  font-size: 1.2rem;
}

.search-input {
  flex: 1;
  background: none;
  border: none;
  font-size: var(--font-size-base);
  padding: 0;
  outline: none;
}

.results-section.loading {
  opacity: 0.5;
  pointer-events: none;
}

.results-header {
  margin: var(--spacing-md) 0;
}

.results-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
}

/* Genre sections */
.genre-sections {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-xl);
}

.genre-section {
  background: var(--color-bg-card);
  border-radius: var(--radius-lg);
  padding: var(--spacing-lg);
  border: 1px solid var(--color-border);
}

.genre-label {
  font-size: var(--font-size-base);
  font-weight: 600;
  margin-bottom: var(--spacing-md);
  color: var(--color-accent-primary);
}

.genre-tracks-scroll {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

/* Track list */
.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.track-list-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.rank-number {
  width: 28px;
  text-align: center;
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.rank-number.top-3 {
  color: var(--color-accent-primary);
  font-size: var(--font-size-lg);
}

/* Pagination */
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

/* Loading */
.loading-skeletons {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-md);
}

.skeleton-row {
  height: 64px;
  border-radius: var(--radius-md);
}

/* Empty state */
.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--color-text-muted);
  font-size: var(--font-size-lg);
}
</style>
