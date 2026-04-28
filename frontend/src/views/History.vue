<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { usersApi } from '@/api/tracks'
import { usePlayerStore } from '@/stores/player'
import type { PlaybackHistoryItem } from '@/types'

const player = usePlayerStore()
const history = ref<PlaybackHistoryItem[]>([])
const loading = ref(true)

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23121212" width="100" height="100"/><text x="50" y="56" text-anchor="middle" fill="%231ed760" font-size="38">♪</text></svg>'

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
  <div class="history-page page-shell">
    <header class="page-hero animate-fade-in">
      <div class="page-hero-copy">
        <span class="page-kicker">Playback Memory</span>
        <h1 class="page-title">播放历史</h1>
        <p class="page-subtitle">最近播放的 {{ history.length }} 首歌曲，会继续作为推荐系统的输入。</p>
      </div>
      <div class="page-actions">
        <span class="pill-tag">{{ history.length }} Items</span>
      </div>
    </header>

    <section class="section-block animate-slide-up">
      <div class="section-top">
        <div>
          <h2 class="section-heading">最近播放</h2>
          <p class="section-copy">点击任意记录即可重新开始播放。</p>
        </div>
      </div>

      <div v-if="loading" class="row-list">
        <div v-for="i in 8" :key="i" class="skeleton skeleton-row"></div>
      </div>

      <div v-else-if="history.length === 0" class="empty-state">
        <p>暂无播放记录。</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>

      <div v-else class="history-list">
        <button
          v-for="item in history"
          :key="item.interaction_id"
          class="history-row"
          type="button"
          @click="playTrack(item)"
        >
          <img
            :src="item.cover_url || coverFallback"
            :alt="item.title"
            class="history-cover"
          />

          <div class="history-info">
            <strong class="history-title">{{ item.title }}</strong>
            <router-link
              v-if="item.artist_name"
              :to="`/artist/${encodeURIComponent(item.artist_name)}`"
              class="history-artist"
              @click.stop
            >
              {{ item.artist_name }}
            </router-link>
            <span v-else class="history-artist">Unknown Artist</span>
          </div>

          <div class="history-meta">
            <span class="history-time">{{ formatTimestamp(item.created_at) }}</span>
            <span v-if="item.play_duration" class="history-duration">
              {{ formatDuration(item.play_duration) }}
            </span>
          </div>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.history-list {
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
}

.history-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.875rem;
  border-radius: 14px;
  text-align: left;
  background: linear-gradient(180deg, rgba(37, 37, 37, 0.95), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-medium);
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast);
}

.history-row:hover {
  transform: translateY(-1px);
  background: linear-gradient(180deg, rgba(45, 45, 45, 1), rgba(31, 31, 31, 1));
}

.history-cover {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  object-fit: cover;
  flex-shrink: 0;
}

.history-info {
  min-width: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
}

.history-title {
  color: var(--color-text-base);
  font-size: var(--font-size-base);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-artist {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-artist:hover {
  color: var(--color-text-base);
}

.history-meta {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 0.3rem;
  flex-shrink: 0;
}

.history-time,
.history-duration {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
}

.skeleton-row {
  width: 100%;
  height: 82px;
}

@media (max-width: 768px) {
  .history-meta {
    align-items: flex-start;
  }

  .history-row {
    align-items: flex-start;
  }
}
</style>
