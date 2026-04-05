/** Favorites store - caches favorited track IDs for fast UI state */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { usersApi, favoritesApi } from '@/api/tracks'
import { useAuthStore } from '@/stores/auth'

export const useFavoritesStore = defineStore('favorites', () => {
  const favoriteIds = ref<Set<string>>(new Set())
  const loaded = ref(false)
  const loading = ref(false)

  const isFavorited = computed(() => (trackId: string) => favoriteIds.value.has(trackId))

  async function loadFavorites() {
    const auth = useAuthStore()
    if (!auth.isLoggedIn || loading.value) return
    loading.value = true
    try {
      const { data } = await usersApi.favoriteIds()
      favoriteIds.value = new Set(data.track_ids)
      loaded.value = true
    } catch (e) {
      console.error('Failed to load favorite IDs:', e)
    } finally {
      loading.value = false
    }
  }

  async function toggleFavorite(trackId: string): Promise<boolean> {
    const auth = useAuthStore()
    if (!auth.isLoggedIn) return false

    const wasFavorited = favoriteIds.value.has(trackId)
    // Optimistic update
    if (wasFavorited) {
      favoriteIds.value.delete(trackId)
    } else {
      favoriteIds.value.add(trackId)
    }

    try {
      if (wasFavorited) {
        await favoritesApi.remove(trackId)
      } else {
        await favoritesApi.add(trackId)
      }
      return !wasFavorited
    } catch (e) {
      // Rollback on failure
      if (wasFavorited) {
        favoriteIds.value.add(trackId)
      } else {
        favoriteIds.value.delete(trackId)
      }
      return wasFavorited
    }
  }

  function reset() {
    favoriteIds.value = new Set()
    loaded.value = false
  }

  return { favoriteIds, loaded, loading, isFavorited, loadFavorites, toggleFavorite, reset }
})
