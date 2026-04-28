<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { tracksApi } from '@/api/tracks'
import { usePlayerStore } from '@/stores/player'
import type { Track, GenreTracksResponse } from '@/types'

const player = usePlayerStore()

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

onMounted(async () => {
  loadTracks()
  await Promise.all([loadGenreRandom(), loadGenreRanking()])
})

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23121212" width="100" height="100"/><text x="50" y="56" text-anchor="middle" fill="%231ed760" font-size="38">♪</text></svg>'
</script>

<template>
  <div class="discover-page page-shell">
    <header class="page-hero animate-fade-in">
      <div class="page-hero-copy">
        <span class="page-kicker">Browse</span>
        <h1 class="page-title">发现音乐</h1>
        <p class="page-subtitle">
          搜索整座曲库，或从按类型整理的推荐与热榜里直接开始播放。
        </p>
      </div>
      <div class="page-actions">
        <span class="pill-tag">{{ total || tracks.length }} Results</span>
      </div>
    </header>

    <section class="section-block animate-slide-up">
      <div class="content-panel search-panel">
        <label class="search-field">
          <span class="search-icon">⌕</span>
          <input
            v-model="searchQuery"
            type="text"
            class="search-input"
            placeholder="搜索歌曲、歌手或专辑"
            @input="onSearchInput"
          />
        </label>

        <div v-if="searchQuery" class="results-section" :class="{ loading }">
          <div class="section-top search-results-header">
            <div>
              <h2 class="section-heading">搜索结果</h2>
              <p class="section-copy">
                {{ total ? `共找到 ${total} 首歌曲` : '正在尝试匹配相关内容' }}
              </p>
            </div>
          </div>

          <div v-if="tracks.length" class="row-list">
            <TrackCard v-for="track in tracks" :key="track.track_id" :track="track" :tracks="tracks" />
          </div>

          <div v-else-if="!loading" class="empty-state search-empty">
            <p>没有找到匹配的歌曲。</p>
          </div>

          <div class="pagination" v-if="total > pageSize">
            <button class="btn-secondary" :disabled="page <= 1" @click="prevPage">上一页</button>
            <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
            <button class="btn-secondary" :disabled="page * pageSize >= total" @click="nextPage">下一页</button>
          </div>
        </div>
      </div>
    </section>

    <section class="section-block animate-slide-up" style="animation-delay: 100ms">
      <div class="section-top">
        <div>
          <h2 class="section-heading">类型推荐</h2>
          <p class="section-copy">适合漫游和快速试播的随机精选。</p>
        </div>
        <div class="section-actions">
          <span class="pill-tag">Genre Mix</span>
          <button class="btn-secondary refresh-btn" :disabled="genreRandomLoading" @click="loadGenreRandom">
            <span :class="{ spinning: genreRandomLoading }">↻</span>
            换一批
          </button>
        </div>
      </div>

      <div v-if="genreRandomLoading" class="genre-board loading-board">
        <div v-for="i in 4" :key="i" class="genre-column content-panel">
          <div class="skeleton skeleton-column-title"></div>
          <div v-for="j in 5" :key="j" class="skeleton skeleton-column-track"></div>
        </div>
      </div>

      <div v-else-if="genreRandom?.genres.length" class="genre-board">
        <article v-for="g in genreRandom.genres" :key="g.genre" class="genre-column">
          <div class="genre-column-header">
            <span class="genre-bullet"></span>
            <strong class="genre-title">{{ g.genre }}</strong>
          </div>

          <div class="genre-track-list">
            <button
              v-for="track in g.tracks"
              :key="track.track_id"
              class="genre-track"
              type="button"
              @click="player.play(track, g.tracks)"
            >
              <img :src="track.cover_url || coverFallback" :alt="track.title" class="genre-track-cover" />
              <div class="genre-track-copy">
                <strong class="genre-track-title">{{ track.title }}</strong>
                <router-link
                  v-if="track.artist_name"
                  :to="`/artist/${encodeURIComponent(track.artist_name)}`"
                  class="genre-track-artist"
                  @click.stop
                >
                  {{ track.artist_name }}
                </router-link>
                <span v-else class="genre-track-artist">Unknown Artist</span>
              </div>
            </button>
          </div>
        </article>
      </div>
    </section>

    <section class="section-block animate-slide-up" style="animation-delay: 180ms">
      <div class="section-top">
        <div>
          <h2 class="section-heading">类型热榜</h2>
          <p class="section-copy">当前最热门的高频曲目，适合直接接管播放器。</p>
        </div>
        <span class="pill-tag pill-tag--accent">Top Picks</span>
      </div>

      <div v-if="genreRankingLoading" class="genre-board loading-board">
        <div v-for="i in 4" :key="i" class="genre-column content-panel">
          <div class="skeleton skeleton-column-title"></div>
          <div v-for="j in 5" :key="j" class="skeleton skeleton-column-track"></div>
        </div>
      </div>

      <div v-else-if="genreRanking?.genres.length" class="genre-board">
        <article v-for="g in genreRanking.genres" :key="g.genre" class="genre-column">
          <div class="genre-column-header genre-column-header-hot">
            <span class="genre-bullet genre-bullet-hot"></span>
            <strong class="genre-title">{{ g.genre }}</strong>
          </div>

          <div class="genre-track-list">
            <button
              v-for="(track, idx) in g.tracks"
              :key="track.track_id"
              class="genre-track"
              type="button"
              @click="player.play(track, g.tracks)"
            >
              <span class="rank-badge">{{ idx + 1 }}</span>
              <img :src="track.cover_url || coverFallback" :alt="track.title" class="genre-track-cover" />
              <div class="genre-track-copy">
                <strong class="genre-track-title">{{ track.title }}</strong>
                <router-link
                  v-if="track.artist_name"
                  :to="`/artist/${encodeURIComponent(track.artist_name)}`"
                  class="genre-track-artist"
                  @click.stop
                >
                  {{ track.artist_name }}
                </router-link>
                <span v-else class="genre-track-artist">Unknown Artist</span>
              </div>
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<style scoped>
.search-panel {
  padding: 1.125rem;
}

.search-field {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-height: 56px;
  padding: 0 1rem;
  border-radius: var(--radius-pill);
  background: var(--color-bg-surface-strong);
  box-shadow: var(--shadow-input);
}

.search-field:focus-within {
  box-shadow:
    0 0 0 2px rgba(255, 255, 255, 0.08),
    var(--shadow-input);
}

.search-icon {
  color: var(--color-text-secondary);
  font-size: 1rem;
}

.search-input {
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.results-section {
  margin-top: 1.125rem;
}

.results-section.loading {
  opacity: 0.55;
  pointer-events: none;
}

.search-results-header {
  margin-bottom: 0.875rem;
}

.search-empty {
  margin-top: 0.75rem;
}

.refresh-btn span.spinning {
  display: inline-block;
  animation: spin 0.8s linear infinite;
}

.genre-board {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: 1rem;
}

.genre-column {
  padding: 1rem;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(37, 37, 37, 0.98), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-heavy);
}

.genre-column-header {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  margin-bottom: 0.875rem;
}

.genre-column-header-hot .genre-title {
  color: var(--color-text-base);
}

.genre-bullet {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-accent);
  box-shadow: 0 0 12px rgba(30, 215, 96, 0.35);
}

.genre-bullet-hot {
  background: var(--color-text-warning);
  box-shadow: 0 0 12px rgba(255, 164, 43, 0.35);
}

.genre-title {
  color: var(--color-text-base);
  font-size: var(--font-size-base);
  font-weight: 700;
}

.genre-track-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.genre-track {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  border-radius: 14px;
  text-align: left;
  background: rgba(255, 255, 255, 0.03);
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast);
}

.genre-track:hover {
  transform: translateY(-1px);
  background: rgba(255, 255, 255, 0.06);
}

.genre-track-cover {
  width: 42px;
  height: 42px;
  border-radius: var(--radius-lg);
  object-fit: cover;
  flex-shrink: 0;
}

.genre-track-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.genre-track-title {
  color: var(--color-text-base);
  font-size: var(--font-size-sm);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.genre-track-artist {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.genre-track-artist:hover {
  color: var(--color-text-base);
}

.rank-badge {
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: rgba(30, 215, 96, 0.16);
  color: var(--color-accent);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: var(--font-size-xs);
  font-weight: 700;
  flex-shrink: 0;
}

.loading-board .genre-column {
  min-height: 260px;
}

.skeleton-column-title {
  width: 52%;
  height: 18px;
  margin-bottom: 1rem;
}

.skeleton-column-track {
  width: 100%;
  height: 56px;
  margin-bottom: 0.625rem;
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
  .genre-board {
    grid-template-columns: 1fr;
  }
}
</style>
