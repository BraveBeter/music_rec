<script setup lang="ts">
import { ref, onMounted } from 'vue'
import TrackCard from '@/components/common/TrackCard.vue'
import { recommendationsApi, tracksApi } from '@/api/tracks'
import { useAuthStore } from '@/stores/auth'
import type { Track, RecommendationResponse } from '@/types'

const auth = useAuthStore()
const recommendations = ref<Track[]>([])
const popularTracks = ref<Track[]>([])
const loading = ref(true)
const strategy = ref('')

onMounted(async () => {
  try {
    const [recRes, popRes] = await Promise.all([
      recommendationsApi.getFeed({ size: 20 }),
      tracksApi.popular(10),
    ])
    recommendations.value = recRes.data.items
    strategy.value = recRes.data.strategy_matched
    popularTracks.value = popRes.data
  } catch (e) {
    console.error('Failed to load recommendations:', e)
  } finally {
    loading.value = false
  }
})
</script>

<template>
  <div class="home-page">
    <header class="page-header animate-fade-in">
      <h1 class="page-title">
        <span v-if="auth.isLoggedIn">你好, </span>
        <span v-if="auth.isLoggedIn" class="gradient-text">{{ auth.user?.username }}</span>
        <span v-else class="gradient-text">发现你的音乐</span>
      </h1>
      <p class="page-subtitle">为你精心推荐的个性化音乐</p>
    </header>

    <!-- Recommendations Section -->
    <section class="section animate-slide-up">
      <div class="section-header">
        <h2 class="section-title">🎯 每日推荐</h2>
        <span class="strategy-tag" v-if="strategy">{{ strategy }}</span>
      </div>

      <div v-if="loading" class="track-grid">
        <div v-for="i in 8" :key="i" class="skeleton-card">
          <div class="skeleton" style="width: 100%; aspect-ratio: 1;"></div>
          <div class="skeleton" style="width: 80%; height: 14px; margin-top: 8px;"></div>
          <div class="skeleton" style="width: 60%; height: 12px; margin-top: 4px;"></div>
        </div>
      </div>

      <div v-else-if="recommendations.length" class="track-grid">
        <div
          v-for="(track, index) in recommendations"
          :key="track.track_id"
          class="track-grid-item animate-slide-up"
          :style="{ animationDelay: `${index * 50}ms` }"
        >
          <TrackCard :track="track" :tracks="recommendations" :show-score="true" />
        </div>
      </div>

      <div v-else class="empty-state">
        <p>暂无推荐，请先浏览一些歌曲 🎶</p>
        <router-link to="/discover" class="btn-primary">去发现音乐</router-link>
      </div>
    </section>

    <!-- Popular Section -->
    <section class="section animate-slide-up" style="animation-delay: 200ms">
      <div class="section-header">
        <h2 class="section-title">🔥 热门排行</h2>
      </div>

      <div class="track-list">
        <div
          v-for="(track, index) in popularTracks"
          :key="track.track_id"
          class="track-list-item"
        >
          <span class="rank-number" :class="{ 'top-3': index < 3 }">{{ index + 1 }}</span>
          <TrackCard :track="track" :tracks="popularTracks" />
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.home-page {
  max-width: 1200px;
  margin: 0 auto;
}

.page-header {
  margin-bottom: var(--spacing-2xl);
}

.page-title {
  font-size: var(--font-size-3xl);
  font-weight: 700;
  margin-bottom: var(--spacing-sm);
}

.page-subtitle {
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.section {
  margin-bottom: var(--spacing-2xl);
}

.section-header {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
  margin-bottom: var(--spacing-lg);
}

.section-title {
  font-size: var(--font-size-xl);
  font-weight: 600;
}

.strategy-tag {
  font-size: var(--font-size-xs);
  color: var(--color-accent-primary);
  background: rgba(99, 102, 241, 0.15);
  padding: 2px 8px;
  border-radius: var(--radius-sm);
  font-family: monospace;
}

.track-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
  gap: var(--spacing-sm);
}

.track-grid-item {
  /* opacity is handled by the animate-slide-up animation */
}

.skeleton-card {
  padding: var(--spacing-md);
}

.track-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.track-list-item {
  display: flex;
  align-items: center;
  gap: var(--spacing-md);
}

.rank-number {
  width: 28px;
  text-align: center;
  font-size: var(--font-size-base);
  font-weight: 700;
  color: var(--color-text-muted);
  flex-shrink: 0;
}

.rank-number.top-3 {
  color: var(--color-accent-primary);
  font-size: var(--font-size-lg);
}

.empty-state {
  text-align: center;
  padding: var(--spacing-2xl);
  color: var(--color-text-muted);
}

.empty-state p {
  margin-bottom: var(--spacing-lg);
  font-size: var(--font-size-lg);
}
</style>
