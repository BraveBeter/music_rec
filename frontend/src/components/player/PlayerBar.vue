<script setup lang="ts">
import { usePlayerStore } from '@/stores/player'
import { useAuthStore } from '@/stores/auth'
import { useFavoritesStore } from '@/stores/favorites'
import { interactionsApi } from '@/api/tracks'
import { computed } from 'vue'

const player = usePlayerStore()
const auth = useAuthStore()
const favStore = useFavoritesStore()

function handleProgressClick(e: MouseEvent) {
  const bar = e.currentTarget as HTMLElement
  const rect = bar.getBoundingClientRect()
  const percent = ((e.clientX - rect.left) / rect.width) * 100
  player.seekTo(percent)
}

function handleVolumeChange(e: Event) {
  const input = e.target as HTMLInputElement
  player.setVolume(parseFloat(input.value))
}

async function toggleLike() {
  if (!auth.isLoggedIn || !player.currentTrack) return
  const nowLiked = await favStore.toggleFavorite(player.currentTrack.track_id)
  if (nowLiked) {
    interactionsApi.log({
      track_id: player.currentTrack.track_id,
      interaction_type: 2,
    }).catch(() => {})
  }
}

const trackTitle = computed(() => player.currentTrack?.title || 'MusicRec')
const artistName = computed(() => player.currentTrack?.artist_name || '')
const coverUrl = computed(() =>
  player.currentTrack?.cover_url || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23121212" width="100" height="100"/><text x="50" y="56" text-anchor="middle" fill="%231ed760" font-size="38">♪</text></svg>'
)
const isLiked = computed(() => (player.currentTrack ? favStore.isFavorited(player.currentTrack.track_id) : false))
</script>

<template>
  <div class="player-bar" :class="{ idle: !player.currentTrack }">
    <button
      type="button"
      class="progress-hitbox"
      :disabled="!player.currentTrack"
      aria-label="调整播放进度"
      @click="handleProgressClick"
    >
      <span class="progress-track">
        <span class="progress-fill" :style="{ width: player.progress + '%' }"></span>
      </span>
    </button>

    <div class="player-shell">
      <div class="player-now">
        <div class="track-cover">
          <img :src="coverUrl" :alt="trackTitle" />
          <div v-if="player.isPlaying" class="cover-pulse" aria-hidden="true"></div>
        </div>

        <div class="track-copy">
          <span class="track-status">{{ player.currentTrack ? 'Now Playing' : 'Standby' }}</span>
          <strong class="track-title">{{ trackTitle }}</strong>
          <router-link
            v-if="player.currentTrack && artistName"
            :to="`/artist/${encodeURIComponent(artistName)}`"
            class="track-artist"
          >
            {{ artistName }}
          </router-link>
          <span v-else class="track-artist">点击任意歌曲开始播放</span>
        </div>
      </div>

      <div class="player-transport">
        <div class="transport-row">
          <button class="btn-icon transport-btn" :disabled="!player.currentTrack" title="上一首" @click="player.prev()">
            ⏮
          </button>
          <button
            class="play-btn"
            :disabled="!player.currentTrack"
            :title="player.isPlaying ? '暂停' : '播放'"
            @click="player.togglePlay()"
          >
            {{ player.isPlaying ? '⏸' : '▶' }}
          </button>
          <button class="btn-icon transport-btn" :disabled="!player.currentTrack" title="下一首" @click="player.next()">
            ⏭
          </button>
          <button
            v-if="auth.isLoggedIn"
            :class="['btn-icon transport-btn', 'like-btn', { liked: isLiked }]"
            :disabled="!player.currentTrack"
            :title="isLiked ? '取消收藏' : '收藏'"
            @click="toggleLike"
          >
            {{ isLiked ? '♥' : '♡' }}
          </button>
        </div>
      </div>

      <div class="player-extra">
        <div class="player-timing" v-if="player.currentTrack">
          <span>{{ player.formattedCurrentTime }}</span>
          <span class="timing-separator">/</span>
          <span>{{ player.formattedDuration }}</span>
        </div>

        <div class="volume-control">
          <span class="volume-label">VOL</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            :value="player.volume"
            class="volume-slider"
            @input="handleVolumeChange"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-bar {
  position: fixed;
  inset: auto 0 0;
  z-index: 220;
  height: var(--player-height);
  padding: 0.35rem 1rem 0.75rem;
  background:
    linear-gradient(180deg, rgba(18, 18, 18, 0.92), rgba(10, 10, 10, 0.98));
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  box-shadow: var(--shadow-heavy);
}

.progress-hitbox {
  width: 100%;
  padding: 0.1rem 0 0.45rem;
  border-radius: 0;
  background: transparent;
}

.progress-track {
  display: block;
  width: 100%;
  height: 4px;
  border-radius: var(--radius-pill-full);
  background: rgba(255, 255, 255, 0.14);
  overflow: hidden;
}

.progress-hitbox:hover .progress-track {
  height: 6px;
}

.progress-fill {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: var(--color-accent);
  transition: width 90ms linear;
}

.player-shell {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) auto minmax(0, 1fr);
  align-items: center;
  gap: 1rem;
  height: calc(100% - 0.55rem);
}

.player-now {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  min-width: 0;
}

.track-cover {
  position: relative;
  width: 56px;
  height: 56px;
  border-radius: var(--radius-lg);
  overflow: hidden;
  background: var(--color-bg-surface-strong);
  flex-shrink: 0;
}

.track-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.cover-pulse {
  position: absolute;
  inset: auto 8px 8px;
  height: 6px;
  border-radius: var(--radius-pill-full);
  background: var(--color-accent);
  box-shadow: 0 0 12px rgba(30, 215, 96, 0.4);
}

.track-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.12rem;
}

.track-status {
  color: var(--color-text-secondary);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: 0.18em;
  text-transform: uppercase;
}

.track-title {
  color: var(--color-text-base);
  font-size: var(--font-size-sm);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-artist {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-artist:hover {
  color: var(--color-text-base);
}

.player-transport {
  display: flex;
  justify-content: center;
}

.transport-row {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.transport-btn {
  font-size: 0.95rem;
}

.play-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 50px;
  height: 50px;
  border-radius: 50%;
  background: var(--color-accent);
  color: #000000;
  font-size: 1.05rem;
  box-shadow: var(--shadow-medium);
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast);
}

.play-btn:hover:not(:disabled) {
  transform: scale(1.04);
  background: #3be477;
}

.like-btn.liked {
  color: var(--color-accent);
}

.player-extra {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 1rem;
  min-width: 0;
}

.player-timing {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
  font-variant-numeric: tabular-nums;
}

.timing-separator {
  color: var(--color-text-muted);
}

.volume-control {
  display: inline-flex;
  align-items: center;
  gap: 0.625rem;
}

.volume-label {
  color: var(--color-text-secondary);
  font-size: var(--font-size-badge);
  font-weight: 700;
  letter-spacing: 0.18em;
}

.volume-slider {
  width: 96px;
  padding: 0;
  background: transparent;
  box-shadow: none;
}

.volume-slider::-webkit-slider-runnable-track {
  height: 4px;
  border-radius: var(--radius-pill-full);
  background: rgba(255, 255, 255, 0.2);
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 12px;
  height: 12px;
  margin-top: -4px;
  border-radius: 50%;
  background: var(--color-accent);
}

.volume-slider::-moz-range-track {
  height: 4px;
  border-radius: var(--radius-pill-full);
  background: rgba(255, 255, 255, 0.2);
}

.volume-slider::-moz-range-thumb {
  width: 12px;
  height: 12px;
  border: none;
  border-radius: 50%;
  background: var(--color-accent);
}

.player-bar.idle .track-cover img,
.player-bar.idle .play-btn,
.player-bar.idle .transport-btn {
  opacity: 0.45;
}

@media (max-width: 1024px) {
  .player-shell {
    grid-template-columns: minmax(0, 1fr) auto;
  }

  .player-extra {
    display: none;
  }
}

@media (max-width: 768px) {
  .player-bar {
    height: 88px;
    padding: 0.35rem 0.75rem 0.6rem;
  }

  .player-shell {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 0.75rem;
  }

  .track-cover {
    width: 48px;
    height: 48px;
  }

  .transport-row {
    gap: 0.5rem;
  }

  .play-btn {
    width: 44px;
    height: 44px;
  }
}
</style>
