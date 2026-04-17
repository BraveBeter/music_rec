<script setup lang="ts">
import type { ArtistItem } from '@/api/artists'
import { useArtistFavoritesStore } from '@/stores/artists'
import { useAuthStore } from '@/stores/auth'
import { useRouter } from 'vue-router'

const props = defineProps<{
  artist: ArtistItem
  showFavorite?: boolean
}>()

const artistFav = useArtistFavoritesStore()
const auth = useAuthStore()
const router = useRouter()

const isFav = () => artistFav.isFavorited(props.artist.artist_name)

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%231a1a2e" width="100" height="100"/><text x="50" y="58" text-anchor="middle" fill="%236366f1" font-size="35">🎤</text></svg>'

function goToArtist() {
  router.push(`/artist/${encodeURIComponent(props.artist.artist_name)}`)
}

async function toggleFav() {
  if (!auth.isLoggedIn) return
  await artistFav.toggleFavorite(props.artist.artist_name)
}
</script>

<template>
  <div class="artist-card" @click="goToArtist">
    <div class="artist-cover-wrapper">
      <img
        :src="artist.cover_url || coverFallback"
        :alt="artist.artist_name"
        class="artist-cover-img"
      />
    </div>
    <div class="artist-info">
      <div class="artist-name">{{ artist.artist_name }}</div>
      <div class="artist-count">{{ artist.track_count }} 首歌曲</div>
    </div>
    <button
      v-if="showFavorite && auth.isLoggedIn"
      :class="['fav-btn', { liked: isFav() }]"
      @click.stop="toggleFav"
    >
      {{ isFav() ? '❤️' : '🤍' }}
    </button>
  </div>
</template>

<style scoped>
.artist-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  padding: var(--spacing-sm) var(--spacing-md);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background var(--transition-fast);
}

.artist-card:hover {
  background: var(--color-bg-card-hover);
}

.artist-cover-wrapper {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  overflow: hidden;
  flex-shrink: 0;
}

.artist-cover-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.artist-info {
  flex: 1;
  min-width: 0;
}

.artist-name {
  font-size: var(--font-size-sm);
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.artist-count {
  font-size: var(--font-size-xs);
  color: var(--color-text-muted);
}

.fav-btn {
  font-size: 1rem;
  background: none;
  border: none;
  cursor: pointer;
  transition: transform var(--transition-fast);
  padding: 4px;
}

.fav-btn:hover {
  transform: scale(1.2);
}
</style>
