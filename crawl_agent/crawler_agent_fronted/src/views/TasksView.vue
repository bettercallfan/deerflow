<template>
  <section class="panel">
    <h2>定时调度</h2>
    <p class="page-note">这里展示所有定时调度，可直接执行、暂停/恢复与删除。</p>
    <div class="actions-row">
      <el-button @click="fetchSchedules">刷新调度</el-button>
    </div>
    <el-table :data="schedules" style="margin-top: 16px">
      <el-table-column prop="id" label="调度ID" min-width="220" />
      <el-table-column prop="name" label="名称" min-width="140" />
      <el-table-column prop="status" label="状态" width="120" />
      <el-table-column label="上次运行" min-width="200">
        <template #default="{ row }">
          {{ formatDateTime(row.last_run_at) }}
        </template>
      </el-table-column>
      <el-table-column label="下次运行" min-width="200">
        <template #default="{ row }">
          {{ formatDateTime(row.next_run_at) }}
        </template>
      </el-table-column>
      <el-table-column label="操作" width="260">
        <template #default="{ row }">
          <el-space>
            <el-button size="small" @click="runOnce(row)">执行一次</el-button>
            <el-button size="small" @click="toggleSchedule(row)">
              {{ row.status === 'ACTIVE' ? '暂停' : '恢复' }}
            </el-button>
            <el-button size="small" type="danger" @click="removeSchedule(row.id)">删除</el-button>
          </el-space>
        </template>
      </el-table-column>
    </el-table>
  </section>

  <section class="panel">
    <h2>任务中心</h2>
    <p class="page-note">这里记录每次执行的过程，包括成功、失败、跳过与哈希命中详情。</p>
    <div class="actions-row">
      <el-select v-model="status" placeholder="状态筛选" clearable style="width: 180px" @change="fetchTasks">
        <el-option value="PENDING" label="PENDING" />
        <el-option value="RUNNING" label="RUNNING" />
        <el-option value="SUCCEEDED" label="SUCCEEDED" />
        <el-option value="FAILED" label="FAILED" />
        <el-option value="SKIPPED_NO_CHANGE" label="SKIPPED_NO_CHANGE" />
      </el-select>
      <el-button @click="fetchTasks">刷新</el-button>
    </div>

    <el-table :data="tasks" style="margin-top: 16px" @row-click="selectTask">
      <el-table-column prop="id" label="任务ID" min-width="240" />
      <el-table-column prop="name" label="名称" min-width="180" />
      <el-table-column label="状态" width="220">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" effect="light">
            {{ row.status }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="result_summary" label="摘要" min-width="260" />
    </el-table>
  </section>

  <section v-if="selectedTask" class="panel">
    <h3>任务详情：{{ selectedTask.id }}</h3>
    <p>状态：{{ selectedTask.status }}</p>
    <p>跳过原因：{{ selectedTask.skip_reason || '-' }}</p>
    <p>错误信息：{{ selectedTask.error_message || '-' }}</p>

    <div class="actions-row">
      <el-button @click="fetchResults">查看结果</el-button>
      <el-button @click="fetchFingerprints">查看哈希指纹</el-button>
    </div>

    <el-table v-if="results.length" :data="results" style="margin-top: 12px">
      <el-table-column prop="url" label="URL" min-width="280" />
      <el-table-column prop="is_duplicate" label="重复" width="90" />
      <el-table-column prop="duplicate_reason" label="重复原因" width="170" />
      <el-table-column prop="result_type" label="类型" width="120" />
    </el-table>

    <el-table v-if="fingerprints.length" :data="fingerprints" style="margin-top: 12px">
      <el-table-column prop="url" label="URL" min-width="260" />
      <el-table-column prop="raw_html_hash" label="raw_hash" min-width="220" />
      <el-table-column prop="normalized_content_hash" label="normalized_hash" min-width="220" />
    </el-table>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { ensureModelConfigReady } from '../utils/modelConfig'

const tasks = ref([])
const schedules = ref([])
const status = ref('')
const selectedTask = ref(null)
const results = ref([])
const fingerprints = ref([])

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

function formatDateTime(value) {
  if (!value) return '-'

  if (typeof value === 'string') {
    const match = value.match(/^(\d{4})-(\d{2})-(\d{2})[T\s](\d{2}):(\d{2}):(\d{2})/)
    if (match) {
      const [, year, month, day, hour, minute, second] = match
      return `${year}年${month}月${day}日 ${hour}:${minute}:${second}`
    }
  }

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return String(value)
  }

  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  const hour = String(date.getHours()).padStart(2, '0')
  const minute = String(date.getMinutes()).padStart(2, '0')
  const second = String(date.getSeconds()).padStart(2, '0')
  return `${year}年${month}月${day}日 ${hour}:${minute}:${second}`
}

function statusTagType(taskStatus) {
  if (taskStatus === 'SUCCEEDED') return 'success'
  if (taskStatus === 'FAILED') return 'danger'
  if (taskStatus === 'RUNNING') return 'primary'
  if (taskStatus === 'SKIPPED_NO_CHANGE') return 'info'
  return 'warning'
}

async function fetchTasks() {
  try {
    const params = {}
    if (status.value) params.status = status.value
    const { data } = await api.get('/crawl/tasks', { params })
    tasks.value = data.items || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}

async function fetchSchedules() {
  try {
    const { data } = await api.get('/schedules')
    schedules.value = data.items || []
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}

async function runOnce(row) {
  if (!(await ensureModelConfigReady(row.payload?.output_mode || 'json'))) {
    return
  }
  try {
    await api.post(`/schedules/${row.id}/run-once`)
    ElMessage.success('已触发执行')
    await fetchSchedules()
    await sleep(700)
    await fetchTasks()
    await fetchSchedules()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}

async function toggleSchedule(row) {
  if (row.status !== 'ACTIVE' && !(await ensureModelConfigReady(row.payload?.output_mode || 'json'))) {
    return
  }
  try {
    const apiPath = row.status === 'ACTIVE' ? 'pause' : 'resume'
    await api.post(`/schedules/${row.id}/${apiPath}`)
    fetchSchedules()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}

async function removeSchedule(id) {
  try {
    await api.delete(`/schedules/${id}`)
    ElMessage.success('删除成功')
    fetchSchedules()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}

function selectTask(row) {
  selectedTask.value = row
  results.value = []
  fingerprints.value = []
}

async function fetchResults() {
  if (!selectedTask.value) return
  const { data } = await api.get(`/crawl/tasks/${selectedTask.value.id}/results`)
  results.value = data
}

async function fetchFingerprints() {
  if (!selectedTask.value) return
  const { data } = await api.get(`/crawl/tasks/${selectedTask.value.id}/fingerprints`)
  fingerprints.value = data
}

onMounted(() => {
  fetchSchedules()
  fetchTasks()
})
</script>
