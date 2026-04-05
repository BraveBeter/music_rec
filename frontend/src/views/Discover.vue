<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { tracksApi } from '@/api/tracks'
import type { Track } from '@/types'

const tracks = ref<Track[]>([])
const searchQuery = ref('')
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

onMounted(() => loadTracks())
</script>

<template>
  <div class="discover-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">发现音乐</h1>
      <p class="page-subtitle">探索海量曲库，找到你喜欢的音乐</p>
    </header>

    <!-- Search -->
    <div class="search-bar animate-slide-up">
      <span class="search-icon">🔍</span>
      <input
        v-model="searchQuery"
        @input="onSearchInput"
        type="text"
        placeholder="搜索歌曲、歌手或专辑..."
        class="search-input"
        id="discover-search"
      />
    </div>

    <!-- Results -->
    <div class="results-section" :class="{ loading }">
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
        <p>没有找到匹配的歌曲 😢</p>
      </div>

      <!-- Pagination -->
      <div class="pagination" v-if="total > pageSize">
        <button class="btn-secondary" @click="prevPage" :disabled="page <= 1">← 上一页</button>
        <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
        <button class="btn-secondary" @click="nextPage" :disabled="page * pageSize >= total">下一页 →</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.discover-page {
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

.search-bar {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  background: var(--color-bg-card);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--spacing-md) var(--spacing-lg);
  margin-bottom: var(--spacing-xl);
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

.search-input:focus {
  box-shadow: none;
}

.results-section.loading {
  opacity: 0.5;
  pointer-events: none;
}

.results-header {
  margin-bottom: var(--spacing-md);
}

.results-count {
  font-size: var(--font-size-sm);
  color: var(--color-text-muted);
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
  font-size: var(--font-size-lg);
}
</style>
