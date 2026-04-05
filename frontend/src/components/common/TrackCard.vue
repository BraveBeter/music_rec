<script setup lang="ts">
import type { Track } from '@/types'
import { usePlayerStore } from '@/stores/player'
import { useAuthStore } from '@/stores/auth'
import { useFavoritesStore } from '@/stores/favorites'
import { interactionsApi } from '@/api/tracks'
import { computed } from 'vue'

const props = defineProps<{
  track: Track
  tracks?: Track[]
  index?: number
  showScore?: boolean
}>()

const player = usePlayerStore()
const auth = useAuthStore()
const favStore = useFavoritesStore()

const isLiked = computed(() => favStore.isFavorited(props.track.track_id))

function playTrack() {
  player.play(props.track, props.tracks)
}

async function toggleLike() {
  if (!auth.isLoggedIn) return
  const nowLiked = await favStore.toggleFavorite(props.track.track_id)
  if (nowLiked) {
    interactionsApi.log({
      track_id: props.track.track_id,
      interaction_type: 2, // like
    }).catch(() => {})
  }
}

function formatDuration(ms: number | null): string {
  if (!ms) return '--:--'
  const s = Math.floor(ms / 1000)
  const m = Math.floor(s / 60)
  const sec = s % 60
  return `${m}:${sec.toString().padStart(2, '0')}`
}

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%231a1a2e" width="100" height="100"/><text x="50" y="55" text-anchor="middle" fill="%236366f1" font-size="40">♪</text></svg>'
const isCurrentlyPlaying = () =>
  player.currentTrack?.track_id === props.track.track_id && player.isPlaying
</script>

<template>
  <div
    :class="['track-card', { 'is-playing': isCurrentlyPlaying() }]"
    @click="playTrack"
  >
    <div class="track-cover-wrapper">
      <img
        :src="track.cover_url || coverFallback"
        :alt="track.title"
        class="track-cover-img"
      />
      <div class="play-overlay">
        <span class="play-icon">{{ isCurrentlyPlaying() ? '⏸' : '▶' }}</span>
      </div>
      <div v-if="showScore && track.score" class="score-badge">
        {{ (track.score * 100).toFixed(0) }}
      </div>
    </div>
    <div class="track-details">
      <div class="track-name">{{ track.title }}</div>
      <div class="track-artist-name">{{ track.artist_name || 'Unknown Artist' }}</div>
    </div>
    <div class="track-actions" @click.stop>
      <span class="track-duration">{{ formatDuration(track.duration_ms) }}</span>
      <button
        v-if="auth.isLoggedIn"
        :class="['like-btn', { liked: isLiked }]"
        @click="toggleLike"
        :title="isLiked ? '取消收藏' : '收藏'"
      >
        {{ isLiked ? '❤️' : '🤍' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.track-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.track-card:hover {
  background: var(--color-bg-card-hover);
}

.track-card.is-playing {
  background: rgba(99, 102, 241, 0.1);
}

.track-cover-wrapper {
  position: relative;
  width: 48px;
  height: 48px;
  border-radius: var(--radius-sm);
  overflow: hidden;
  flex-shrink: 0;
}

.track-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.play-overlay {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.track-card:hover .play-overlay {
  opacity: 1;
}

.play-icon {
  font-size: 1.2rem;
  color: white;
}

.score-badge {
  position: absolute;
  top: 2px;
  right: 2px;
  background: var(--color-accent-gradient);
  color: white;
  font-size: 0.6rem;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 4px;
}

.track-details {
  flex: 1;
  min-width: 0;
}

.track-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-card.is-playing .track-name {
  color: var(--color-accent-primary);
}

.track-artist-name {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-actions {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.track-duration {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.like-btn {
  font-size: 1rem;
  background: none;
  border: none;
  cursor: pointer;
  transition: transform var(--transition-fast);
  padding: 4px;
}

.like-btn:hover {
  transform: scale(1.2);
}

.like-btn.liked {
  animation: heartBeat 0.3s ease;
}

@keyframes heartBeat {
  0% { transform: scale(1); }
  50% { transform: scale(1.3); }
  100% { transform: scale(1); }
}
</style>
