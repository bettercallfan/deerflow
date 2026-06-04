import { createRouter, createWebHistory } from 'vue-router'
import CrawlView from '../views/CrawlView.vue'
import ModelConfigView from '../views/ModelConfigView.vue'
import TasksView from '../views/TasksView.vue'
import SchedulesView from '../views/SchedulesView.vue'
import StorageView from '../views/StorageView.vue'

const routes = [
  { path: '/', redirect: '/crawl' },
  { path: '/crawl', component: CrawlView },
  { path: '/model-config', component: ModelConfigView },
  { path: '/tasks', component: TasksView },
  { path: '/schedules', component: SchedulesView },
  { path: '/storage', component: StorageView }
]

export default createRouter({
  history: createWebHistory(),
  routes
})
