<template>
  <div class="stat-card">
    <div class="stat-value">{{ value }}</div>
    <div class="stat-label">{{ label }}</div>
  </div>
</template>

<script setup lang="ts">
defineProps<{ label: string; value: string | number }>()
</script>

<style scoped>
.stat-card {
  background: #16213e;
  border-radius: 10px;
  padding: 1.2rem;
  text-align: center;
}
.stat-value { font-size: 1.8rem; font-weight: 700; color: #e94560; }
.stat-label { font-size: 0.85rem; color: #a0a0b0; margin-top: 0.3rem; }
</style>
