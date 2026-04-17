<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usersApi } from '@/api/tracks'
import { usePlayerStore } from '@/stores/player'
import type { PlaybackHistoryItem } from '@/types'

const player = usePlayerStore()
const history = ref<PlaybackHistoryItem[]>([])
const loading = ref(true)
const page = ref(1)
const pageSize = 50

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%231a1a2e" width="100" height="100"/><text x="50" y="55" text-anchor="middle" fill="%236366f1" font-size="40">♪</text></svg>'

async function loadHistory() {
  loading.value = true
  try {
    const { data } = await usersApi.playbackHistory(500)
    history.value = data
  } catch (e) {
    console.error('Failed to load history:', e)
  } finally {
    loading.value = false
  }
}

function formatDuration(ms: number | null): string {
  if (!ms) return '--:--'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

function formatTimestamp(timestamp: string): string {
  const date = new Date(timestamp)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffMins < 1) return '刚刚'
  if (diffMins < 60) return `${diffMins}分钟前`
  if (diffHours < 24) return `${diffHours}小时前`
  if (diffDays < 7) return `${diffDays}天前`

  return date.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric' })
}

function playTrack(item: PlaybackHistoryItem) {
  const track = {
    track_id: item.track_id,
    title: item.title,
    artist_name: item.artist_name,
    cover_url: item.cover_url,
    duration_ms: item.duration_ms,
    preview_url: null,
    album_name: null,
    release_year: null,
    play_count: 0,
  }
  player.play(track, history.value.map(i => ({
    track_id: i.track_id,
    title: i.title,
    artist_name: i.artist_name,
    cover_url: i.cover_url,
    duration_ms: i.duration_ms,
    preview_url: null,
    album_name: null,
    release_year: null,
    play_count: 0,
  })))
}

onMounted(() => {
  loadHistory()
})
</script>

<template>
  <div class="history-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title gradient-text">🎵 播放历史</h1>
      <p class="page-subtitle">最近播放的 {{ history.length }} 首歌曲</p>
    </header>

    <div v-if="loading" class="loading-state">
      <div v-for="i in 10" :key="i" class="skeleton-row">
        <div class="skeleton skeleton-cover"></div>
        <div class="skeleton skeleton-info"></div>
        <div class="skeleton skeleton-time"></div>
      </div>
    </div>

    <div v-else-if="history.length === 0" class="empty-state">
      <p>暂无播放记录</p>
      <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
    </div>

    <div v-else class="history-list animate-slide-up">
      <div
        v-for="item in history"
        :key="item.interaction_id"
        class="history-row"
        @click="playTrack(item)"
      >
        <img
          :src="item.cover_url || coverFallback"
          :alt="item.title"
          class="history-cover"
        />
        <div class="history-info">
          <div class="history-title">{{ item.title }}</div>
          <div class="history-artist">{{ item.artist_name || 'Unknown Artist' }}</div>
        </div>
        <div class="history-meta">
          <span class="history-time">{{ formatTimestamp(item.created_at) }}</span>
          <span v-if="item.play_duration" class="history-duration">
            {{ formatDuration(item.play_duration) }}
          </span>
        </div>
      </div>
    </div>
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
  font-size: var(--font-size-base);
}

.loading-state {
  display: flex;
  flex-direction: column;
  gap: var(--spacing-sm);
}

.skeleton-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-md);
  background: var(--color-bg-card);
  border-radius: var(--radius-md);
}

.skeleton-cover {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  flex-shrink: 0;
}

.skeleton-info {
  flex: 1;
  height: 40px;
  border-radius: var(--radius-sm);
}

.skeleton-time {
  width: 80px;
  height: 24px;
  border-radius: var(--radius-sm);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-3xl);
  color: var(--color-text-muted);
}

.empty-state p {
  font-size: var(--font-size-lg);
  margin-bottom: var(--spacing-lg);
}

.history-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--color-bg-secondary);
  border-radius: var(--radius-lg);
  overflow: hidden;
}

.history-row {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  background: var(--color-bg-card);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.history-row:hover {
  background: var(--color-bg-card-hover);
}

.history-cover {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  object-fit: cover;
  flex-shrink: 0;
}

.history-info {
  flex: 1;
  min-width: 0;
}

.history-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-primary);
}

.history-artist {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 4px;
  flex-shrink: 0;
}

.history-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.history-duration {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

@media (max-width: 768px) {
  .history-meta {
    flex-direction: row;
    gap: var(--spacing-sm);
  }
}
</style>
