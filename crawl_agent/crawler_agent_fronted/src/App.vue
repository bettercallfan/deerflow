<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-head">
        <p class="brand-kicker">Crawler Workspace</p>
        <h1 class="brand">Crawler Agent</h1>
        <p class="brand-desc">便利的智能爬虫工具。</p>
      </div>
      <nav class="nav-list">
        <RouterLink to="/crawl">智能爬取</RouterLink>
        <RouterLink to="/tasks">任务中心</RouterLink>
        <RouterLink to="/schedules">定时任务</RouterLink>
        <RouterLink to="/model-config">模型配置</RouterLink>
        <RouterLink to="/storage">存储配置</RouterLink>
      </nav>
      <div class="sidebar-foot">
        <p>FastAPI · Vue</p>
      </div>
    </aside>
    <main class="main-content">
      <header class="topbar">
        <div>
          <p class="topbar-kicker">采集工作台</p>
          <h2 class="topbar-title">Crawler Agent 控制面板</h2>
        </div>
      </header>
      <RouterView />
    </main>
  </div>
</template>

<script setup>
import { RouterLink, RouterView } from 'vue-router'
</script>
