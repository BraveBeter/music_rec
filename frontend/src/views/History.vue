<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { interactionsApi } from '@/api/tracks'
import type { PlayHistoryItem, Track } from '@/types'

const historyItems = ref<PlayHistoryItem[]>([])
const page = ref(1)
const total = ref(0)
const pageSize = 20
const loading = ref(false)

async function loadHistory() {
  loading.value = true
  try {
    const { data } = await interactionsApi.playHistory(page.value, pageSize)
    historyItems.value = data.items
    total.value = data.total
  } catch (e) {
    console.error('Failed to load play history:', e)
  } finally {
    loading.value = false
  }
}

function extractTracks(): Track[] {
  return historyItems.value.map(item => ({
    track_id: item.track.track_id,
    title: item.track.title,
    artist_name: item.track.artist_name,
    album_name: item.track.album_name,
    duration_ms: item.track.duration_ms,
    play_count: item.track.play_count,
    preview_url: item.track.preview_url,
    cover_url: item.track.cover_url,
  }))
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - d.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHour = Math.floor(diffMs / 3600000)
  const diffDay = Math.floor(diffMs / 86400000)

  if (diffMin < 1) return '刚刚'
  if (diffMin < 60) return `${diffMin}分钟前`
  if (diffHour < 24) return `${diffHour}小时前`
  if (diffDay < 7) return `${diffDay}天前`
  return d.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function formatDuration(ms: number | null): string {
  if (!ms) return '--:--'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function nextPage() {
  if (page.value * pageSize < total.value) {
    page.value++
    loadHistory()
  }
}

function prevPage() {
  if (page.value > 1) {
    page.value--
    loadHistory()
  }
}

onMounted(() => loadHistory())
</script>

<template>
  <div class="history-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">播放历史</h1>
      <p class="page-subtitle">共 {{ total }} 首歌曲</p>
    </header>

    <div v-if="loading" class="loading-state">
      <div v-for="i in 8" :key="i" class="skeleton skeleton-row" />
    </div>

    <template v-else>
      <div v-if="historyItems.length === 0" class="empty-state">
        <p>还没有播放记录</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>

      <template v-else>
        <div class="history-list">
          <div
            v-for="item in historyItems"
            :key="item.interaction_id"
            class="history-item"
          >
            <TrackCard
              :track="{
                track_id: item.track.track_id,
                title: item.track.title,
                artist_name: item.track.artist_name,
                album_name: item.track.album_name,
                duration_ms: item.track.duration_ms,
                play_count: item.track.play_count,
                preview_url: item.track.preview_url,
                cover_url: item.track.cover_url,
              }"
              :tracks="extractTracks()"
            />
            <div class="history-meta">
              <span class="history-time">{{ formatDate(item.created_at) }}</span>
              <span v-if="item.completion_rate" class="history-completion">
                {{ (item.completion_rate * 100).toFixed(0) }}%
              </span>
            </div>
          </div>
        </div>

        <div class="pagination" v-if="total > pageSize">
          <button class="btn-secondary" @click="prevPage" :disabled="page <= 1">← 上一页</button>
          <span class="page-info">{{ page }} / {{ Math.ceil(total / pageSize) }}</span>
          <button class="btn-secondary" @click="nextPage" :disabled="page * pageSize >= total">下一页 →</button>
        </div>
      </template>
    </template>
  </div>
</template>

<style scoped>
.history-page {
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
  font-size: var(--font-size-sm);
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

.history-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.history-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.history-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
  flex-shrink: 0;
  min-width: 70px;
}

.history-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.history-completion {
  font-size: 0.65rem;
  color: var(--color-accent-primary);
  opacity: 0.7;
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

.empty-state p {
  margin-bottom: var(--spacing-lg);
  font-size: var(--font-size-lg);
}
</style>
