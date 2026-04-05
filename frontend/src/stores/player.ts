/** Player store - global music player state */
import { defineStore } from 'pinia'
import { ref, computed, watch } from 'vue'
import { interactionsApi } from '@/api/tracks'
import type { Track } from '@/types'

export const usePlayerStore = defineStore('player', () => {
  // Restore last-played track from localStorage
  const _savedTrack = (() => {
    try {
      const raw = localStorage.getItem('player_last_track')
      return raw ? (JSON.parse(raw) as Track) : null
    } catch { return null }
  })()
  const _savedVolume = (() => {
    const v = parseFloat(localStorage.getItem('player_volume') || '')
    return isNaN(v) ? 0.8 : Math.min(1, Math.max(0, v))
  })()

  const currentTrack = ref<Track | null>(_savedTrack)
  const playlist = ref<Track[]>(_savedTrack ? [_savedTrack] : [])
  const currentIndex = ref(0)
  const isPlaying = ref(false)
  const currentTime = ref(0)
  const duration = ref(_savedTrack ? (_savedTrack.duration_ms || 30000) / 1000 : 0)
  const volume = ref(_savedVolume)
  const audio = ref<HTMLAudioElement | null>(null)

  const progress = computed(() => {
    if (duration.value === 0) return 0
    return (currentTime.value / duration.value) * 100
  })

  const formattedCurrentTime = computed(() => formatTime(currentTime.value))
  const formattedDuration = computed(() => formatTime(duration.value))

  function formatTime(seconds: number): string {
    const m = Math.floor(seconds / 60)
    const s = Math.floor(seconds % 60)
    return `${m}:${s.toString().padStart(2, '0')}`
  }

  function initAudio() {
    if (audio.value) return
    audio.value = new Audio()
    audio.value.volume = volume.value

    audio.value.addEventListener('timeupdate', () => {
      currentTime.value = audio.value!.currentTime
      // Fix duration if it's still Infinity/NaN (streaming without Content-Length)
      if ((!isFinite(duration.value) || isNaN(duration.value)) && currentTrack.value?.duration_ms) {
        duration.value = currentTrack.value.duration_ms / 1000
      }
    })
    audio.value.addEventListener('loadedmetadata', () => {
      const d = audio.value!.duration
      // Use actual duration if valid, else fall back to track metadata
      if (isFinite(d) && d > 0) {
        duration.value = d
      } else if (currentTrack.value?.duration_ms) {
        duration.value = currentTrack.value.duration_ms / 1000
      }
    })
    audio.value.addEventListener('durationchange', () => {
      const d = audio.value!.duration
      if (isFinite(d) && d > 0) duration.value = d
    })
    audio.value.addEventListener('ended', () => {
      logPlayInteraction()
      next()
    })
    audio.value.addEventListener('error', () => {
      console.warn('Audio playback error')
      isPlaying.value = false
    })
  }

  function play(track: Track, tracks?: Track[]) {
    initAudio()
    if (tracks) {
      playlist.value = tracks
      currentIndex.value = tracks.findIndex(t => t.track_id === track.track_id)
      if (currentIndex.value === -1) currentIndex.value = 0
    }

    // Log interaction for previous track if switching
    if (currentTrack.value && currentTrack.value.track_id !== track.track_id) {
      logPlayInteraction()
    }

    currentTrack.value = track
    currentTime.value = 0
    // Pre-initialize duration from track metadata (streaming may not have Content-Length)
    duration.value = (track.duration_ms || 30000) / 1000

    // Persist last-played track to localStorage
    try { localStorage.setItem('player_last_track', JSON.stringify(track)) } catch {}

    if (track.preview_url) {
      // Use backend proxy to bypass CDN origin restrictions
      const proxyUrl = `/api/v1/tracks/${track.track_id}/preview`
      audio.value!.src = proxyUrl
      audio.value!.play().catch(() => {
        isPlaying.value = false
      })
      isPlaying.value = true
    } else {
      // No preview available - simulate playback
      isPlaying.value = true
      duration.value = (track.duration_ms || 30000) / 1000
      simulatePlayback()
    }
  }

  function togglePlay() {
    if (!currentTrack.value) return
    if (isPlaying.value) {
      audio.value?.pause()
      isPlaying.value = false
    } else {
      if (currentTrack.value.preview_url) {
        audio.value?.play().catch(() => {})
      } else {
        simulatePlayback()
      }
      isPlaying.value = true
    }
  }

  let simulationInterval: ReturnType<typeof setInterval> | null = null

  function simulatePlayback() {
    if (simulationInterval) clearInterval(simulationInterval)
    simulationInterval = setInterval(() => {
      if (isPlaying.value && !currentTrack.value?.preview_url) {
        currentTime.value += 0.25
        if (currentTime.value >= duration.value) {
          logPlayInteraction()
          next()
        }
      }
    }, 250)
  }

  function next() {
    if (playlist.value.length === 0) return
    currentIndex.value = (currentIndex.value + 1) % playlist.value.length
    play(playlist.value[currentIndex.value])
  }

  function prev() {
    if (playlist.value.length === 0) return
    currentIndex.value = (currentIndex.value - 1 + playlist.value.length) % playlist.value.length
    play(playlist.value[currentIndex.value])
  }

  function seekTo(percent: number) {
    const targetTime = (percent / 100) * duration.value
    if (audio.value?.src) {
      audio.value.currentTime = targetTime
    }
    currentTime.value = targetTime
  }

  function setVolume(v: number) {
    volume.value = v
    if (audio.value) audio.value.volume = v
  }

  function logPlayInteraction() {
    if (!currentTrack.value) return
    const playDurationMs = Math.floor(currentTime.value * 1000)
    if (playDurationMs < 1000) return // Don't log very short plays

    try {
      interactionsApi.log({
        track_id: currentTrack.value.track_id,
        interaction_type: 1, // play
        play_duration: playDurationMs,
        client_timestamp: Math.floor(Date.now() / 1000),
      })
    } catch {
      // Try sendBeacon as fallback
      interactionsApi.logBeacon({
        track_id: currentTrack.value.track_id,
        interaction_type: 1,
        play_duration: playDurationMs,
        client_timestamp: Math.floor(Date.now() / 1000),
      })
    }
  }

  // Send beacon on page unload
  if (typeof window !== 'undefined') {
    window.addEventListener('beforeunload', () => {
      if (currentTrack.value && isPlaying.value) {
        interactionsApi.logBeacon({
          track_id: currentTrack.value.track_id,
          interaction_type: 1,
          play_duration: Math.floor(currentTime.value * 1000),
          client_timestamp: Math.floor(Date.now() / 1000),
        })
      }
    })
  }

  watch(volume, (v) => {
    if (audio.value) audio.value.volume = v
    try { localStorage.setItem('player_volume', String(v)) } catch {}
  })

  return {
    currentTrack, playlist, currentIndex, isPlaying,
    currentTime, duration, volume, progress,
    formattedCurrentTime, formattedDuration,
    play, togglePlay, next, prev, seekTo, setVolume,
  }
})
