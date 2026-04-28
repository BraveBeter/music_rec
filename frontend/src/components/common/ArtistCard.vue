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

const coverFallback = 'data:image/svg+xml,<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><rect fill="%23121212" width="100" height="100"/><text x="50" y="58" text-anchor="middle" fill="%231ed760" font-size="28">A</text></svg>'

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
      <strong class="artist-name">{{ artist.artist_name }}</strong>
      <div class="artist-count">{{ artist.track_count }} 首歌曲</div>
    </div>

    <button
      v-if="showFavorite && auth.isLoggedIn"
      :class="['fav-btn', { liked: isFav() }]"
      @click.stop="toggleFav"
    >
      {{ isFav() ? '♥' : '♡' }}
    </button>
  </div>
</template>

<style scoped>
.artist-card {
  display: flex;
  align-items: center;
  gap: 0.875rem;
  padding: 0.875rem;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(37, 37, 37, 0.95), rgba(24, 24, 24, 0.98));
  box-shadow: var(--shadow-medium);
  cursor: pointer;
  transition:
    transform var(--transition-fast),
    background-color var(--transition-fast);
}

.artist-card:hover {
  transform: translateY(-1px);
  background: linear-gradient(180deg, rgba(45, 45, 45, 0.98), rgba(31, 31, 31, 1));
}

.artist-cover-wrapper {
  width: 58px;
  height: 58px;
  border-radius: 50%;
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
  display: flex;
  flex-direction: column;
  gap: 0.22rem;
}

.artist-name {
  color: var(--color-text-base);
  font-size: var(--font-size-base);
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.artist-count {
  color: var(--color-text-secondary);
  font-size: var(--font-size-xs);
}

.fav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--color-bg-surface-strong);
  color: var(--color-text-secondary);
  font-size: 1rem;
  transition:
    transform var(--transition-fast),
    color var(--transition-fast),
    background-color var(--transition-fast);
}

.fav-btn:hover {
  transform: scale(1.06);
  color: var(--color-text-base);
}

.fav-btn.liked {
  color: var(--color-accent);
}
</style>
