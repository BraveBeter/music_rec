<template>
  <router-view />
</template>

<style>
/* Global reset — eliminate browser default margins */
*, *::before, *::after {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}
html, body, #app {
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 0;
  overflow: hidden;
}
body {
  background: #0d0d1a;
}
</style>
