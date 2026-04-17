<script setup lang="ts">
import { usePlayerStore } from '@/stores/player'
import { computed } from 'vue'

const player = usePlayerStore()

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

const trackTitle = computed(() => player.currentTrack?.title || '♪ MusicRec')
const artistName = computed(() => player.currentTrack?.artist_name || '')
const coverUrl = computed(() =>
  player.currentTrack?.cover_url || 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%231a1a2e" width="100" height="100"/><text x="50" y="55" text-anchor="middle" fill="%236366f1" font-size="40">♪</text></svg>'
)
</script>

<template>
  <div class="player-bar glass" :class="{ idle: !player.currentTrack }">
    <!-- Progress Bar -->
    <div class="progress-wrapper" @click="handleProgressClick">
      <div class="progress-track">
        <div class="progress-fill" :style="{ width: player.progress + '%' }"></div>
      </div>
    </div>

    <div class="player-content">
      <!-- Track Info -->
      <div class="track-info">
        <div class="track-cover">
          <img :src="coverUrl" :alt="trackTitle" />
          <div v-if="player.isPlaying" class="playing-indicator">
            <span></span><span></span><span></span>
          </div>
        </div>
        <div class="track-meta">
          <div class="track-title">{{ trackTitle }}</div>
          <router-link
            v-if="player.currentTrack && artistName"
            :to="`/artist/${encodeURIComponent(artistName)}`"
            class="track-artist"
          >{{ artistName }}</router-link>
          <div v-else class="track-artist">{{ player.currentTrack ? artistName : '点击任意歌曲开始播放' }}</div>
        </div>
      </div>

      <!-- Controls -->
      <div class="player-controls">
        <button class="btn-icon" @click="player.prev()" :disabled="!player.currentTrack" title="上一首">⏮</button>
        <button class="play-btn" @click="player.togglePlay()" :disabled="!player.currentTrack" :title="player.isPlaying ? '暂停' : '播放'">
          {{ player.isPlaying ? '⏸' : '▶' }}
        </button>
        <button class="btn-icon" @click="player.next()" :disabled="!player.currentTrack" title="下一首">⏭</button>
      </div>

      <!-- Time & Volume -->
      <div class="player-extra">
        <span class="time-display" v-if="player.currentTrack">
          {{ player.formattedCurrentTime }} / {{ player.formattedDuration }}
        </span>
        <div class="volume-control">
          <span class="volume-icon">🔊</span>
          <input
            type="range"
            min="0"
            max="1"
            step="0.01"
            :value="player.volume"
            @input="handleVolumeChange"
            class="volume-slider"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.player-bar {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: var(--player-height);
  z-index: 200;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--color-border);
  transition: opacity var(--transition-base);
}

/* Idle state - no track loaded */
.player-bar.idle .track-cover img {
  opacity: 0.35;
  filter: grayscale(1);
}
.player-bar.idle .track-title {
  color: var(--color-text-muted);
}
.player-bar.idle .play-btn,
.player-bar.idle .btn-icon {
  opacity: 0.35;
  cursor: not-allowed;
}

button:disabled {
  opacity: 0.35;
  cursor: not-allowed;
  pointer-events: none;
}


.progress-wrapper {
  height: 4px;
  cursor: pointer;
  position: relative;
}

.progress-wrapper:hover {
  height: 6px;
}

.progress-track {
  width: 100%;
  height: 100%;
  background: rgba(255, 255, 255, 0.1);
  position: relative;
}

.progress-fill {
  height: 100%;
  background: var(--color-accent-gradient);
  border-radius: 0 2px 2px 0;
  transition: width 0.1s linear;
}

.player-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--spacing-xl);
  gap: var(--spacing-xl);
}

.track-info {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  min-width: 200px;
  flex: 1;
}

.track-cover {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-md);
  overflow: hidden;
  position: relative;
  flex-shrink: 0;
}

.track-cover img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.playing-indicator {
  position: absolute;
  bottom: 4px;
  left: 50%;
  transform: translateX(-50%);
  display: flex;
  gap: 2px;
  align-items: flex-end;
  height: 14px;
}

.playing-indicator span {
  width: 3px;
  background: var(--color-accent-primary);
  border-radius: 1px;
  animation: equalize 0.8s infinite;
}

.playing-indicator span:nth-child(1) { height: 60%; animation-delay: 0s; }
.playing-indicator span:nth-child(2) { height: 100%; animation-delay: 0.2s; }
.playing-indicator span:nth-child(3) { height: 40%; animation-delay: 0.4s; }

@keyframes equalize {
  0%, 100% { height: 40%; }
  50% { height: 100%; }
}

.track-meta {
  min-width: 0;
}

.track-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.track-artist {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  text-decoration: none;
  transition: color var(--transition-fast);
}

.track-artist:hover {
  color: var(--color-accent-primary);
}

.player-controls {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.play-btn {
  width: 48px;
  height: 48px;
  border-radius: var(--radius-full);
  background: var(--color-accent-gradient);
  color: white;
  font-size: 1.2rem;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all var(--transition-fast);
  border: none;
  cursor: pointer;
}

.play-btn:hover {
  transform: scale(1.05);
  box-shadow: var(--shadow-glow);
}

.player-extra {
  display: flex;
  align-items: center;
  gap: var(--spacing-lg);
  min-width: 200px;
  justify-content: flex-end;
  flex: 1;
}

.time-display {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.volume-control {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
}

.volume-icon {
  font-size: 0.9rem;
}

.volume-slider {
  width: 80px;
  height: 4px;
  -webkit-appearance: none;
  appearance: none;
  background: rgba(255, 255, 255, 0.15);
  border-radius: 2px;
  outline: none;
  border: none;
  padding: 0;
}

.volume-slider::-webkit-slider-thumb {
  -webkit-appearance: none;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--color-accent-primary);
  cursor: pointer;
}

@media (max-width: 768px) {
  .player-extra {
    display: none;
  }

  .track-info {
    min-width: 120px;
  }
}
</style>
