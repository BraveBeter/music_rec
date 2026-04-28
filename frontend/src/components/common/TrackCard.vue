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
      interaction_type: 2,
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

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23121212" width="100" height="100"/><text x="50" y="56" text-anchor="middle" fill="%231ed760" font-size="38">♪</text></svg>'
const isCurrentlyPlaying = () => player.currentTrack?.track_id === props.track.track_id && player.isPlaying
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
      <div class="play-overlay" aria-hidden="true">
        <span class="play-icon">{{ isCurrentlyPlaying() ? '⏸' : '▶' }}</span>
      </div>
    </div>

    <div class="track-details">
      <div class="track-heading">
        <strong class="track-name">{{ track.title }}</strong>
        <span v-if="showScore && track.score" class="score-badge">
          Match {{ (track.score * 100).toFixed(0) }}
        </span>
      </div>

      <router-link
        v-if="track.artist_name"
        :to="`/artist/${encodeURIComponent(track.artist_name)}`"
        class="track-artist-link"
        @click.stop
      >
        {{ track.artist_name }}
      </router-link>
      <div v-else class="track-artist-name">Unknown Artist</div>
    </div>

    <div class="track-actions" @click.stop>
      <span class="track-duration">{{ formatDuration(track.duration_ms) }}</span>
      <button
        v-if="auth.isLoggedIn"
        :class="['like-btn', { liked: isLiked }]"
        :title="isLiked ? '取消收藏' : '收藏'"
        @click="toggleLike"
      >
        {{ isLiked ? '♥' : '♡' }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.track-card {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.75rem 0.875rem;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(37, 37, 37, 0.95), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-medium);
  cursor: pointer;
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast),
    box-shadow var(--transition-fast);
}

.track-card:hover {
  transform: translateY(-1px);
  background: linear-gradient(180deg, rgba(45, 45, 45, 0.98), rgba(31, 31, 31, 1));
}

.track-card.is-playing {
  box-shadow:
    inset 3px 0 0 var(--color-accent),
    var(--shadow-medium);
}

.track-cover-wrapper {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
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
  display: grid;
  place-items: center;
  background: rgba(0, 0, 0, 0.45);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.track-card:hover .play-overlay,
.track-card.is-playing .play-overlay {
  opacity: 1;
}

.play-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #000000;
  font-size: 0.9rem;
}

.track-details {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
}

.track-heading {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  min-width: 0;
}

.track-name {
  color: var(--color-text-base);
  font-size: var(--font-size-base);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-card.is-playing .track-name {
  color: var(--color-accent);
}

.track-artist-link,
.track-artist-name {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-artist-link:hover {
  color: var(--color-text-base);
}

.score-badge {
  flex-shrink: 0;
  padding: 0.18rem 0.45rem;
  border-radius: var(--radius-pill-full);
  background: rgba(30, 215, 96, 0.16);
  color: var(--color-accent);
  font-size: var(--font-size-micro);
  font-weight: 700;
  letter-spacing: 0.1em;
  text-transform: uppercase;
}

.track-actions {
  display: flex;
  align-items: center;
  gap: 0.625rem;
  flex-shrink: 0;
}

.track-duration {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
}

.like-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: var(--color-bg-surface-strong);
  color: var(--color-text-secondary);
  font-size: 1rem;
  transition:
    transform var(--transition-fast),
    color var(--transition-fast),
    background-color var(--transition-fast);
}

.like-btn:hover {
  transform: scale(1.06);
  color: var(--color-text-base);
}

.like-btn.liked {
  color: var(--color-accent);
}

@media (max-width: 768px) {
  .track-card {
    padding: 0.75rem;
  }

  .score-badge {
    display: none;
  }
}
</style>
