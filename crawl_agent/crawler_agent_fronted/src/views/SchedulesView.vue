<template>
  <section class="panel">
    <h2>网站定时爬取</h2>
    <p class="page-note">定时任务会先判断站点是否变化，只在必要时执行完整抓取。使用前请先完成 Agent导航模型配置；如果选择 JSON 输出，还需要先配置单页面信息抽取模型。</p>
    <el-form :model="form" label-width="170px">
      <el-form-item label="调度名称">
        <el-input v-model="form.name" />
      </el-form-item>
      <el-form-item label="调度类型">
        <el-tag type="success">间隔调度</el-tag>
      </el-form-item>
      <el-form-item label="时间间隔">
        <div class="actions-row">
          <el-input-number v-model="form.interval_days" :min="0" :step="1" />
          <span>天</span>
          <el-input-number v-model="form.interval_hours" :min="0" :max="23" :step="1" />
          <span>时</span>
          <el-input-number v-model="form.interval_minutes" :min="0" :max="59" :step="1" />
          <span>分</span>
        </div>
      </el-form-item>
      <el-form-item label="门户URL">
        <el-input v-model="payload.portal_url" />
      </el-form-item>
      <el-form-item label="自然语言需求">
        <el-input v-model="payload.query" type="textarea" :rows="3" />
      </el-form-item>
      <el-form-item label="输出模式">
        <el-select v-model="payload.output_mode" style="width: 160px">
          <el-option value="json" label="JSON" />
          <el-option value="markdown" label="Markdown" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="payload.output_mode === 'json'" label="JSON结构定义">
        <div style="width: 100%">
          <el-input
            v-model="jsonSchemaText"
            type="textarea"
            :rows="8"
            placeholder='例如：{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"title":{"type":"string"},"url":{"type":"string"}}}}}}'
          />
          <p class="field-note">定时任务同样支持自定义 JSON 输出结构；该能力会使用单页面信息抽取模型，留空时将自动生成结构。</p>
        </div>
      </el-form-item>
      <el-form-item label="存储数据库类型">
        <el-select v-model="payload.storage_db_type" style="width: 180px">
          <el-option value="mysql" label="MySQL" />
          <el-option value="milvus" label="Milvus" />
        </el-select>
      </el-form-item>
      <el-form-item label="变化检测">
        <el-switch v-model="form.change_detect_enabled" />
      </el-form-item>
      <el-form-item label="快速哈希策略">
        <el-select v-model="form.quick_hash_strategy" style="width: 180px">
          <el-option value="content_only" label="content_only" />
          <el-option value="etag+content" label="etag+content" />
        </el-select>
      </el-form-item>
      <el-form-item class="actions-row">
        <el-button type="primary" @click="createSchedule">创建调度</el-button>
        <el-button @click="fetchSchedules">刷新列表</el-button>
      </el-form-item>
    </el-form>
  </section>

</template>

<script setup>
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { ensureModelConfigReady } from '../utils/modelConfig'

const payload = reactive({
  name: '定时抓取任务模板',
  portal_url: '',
  query: '',
  output_mode: 'json',
  storage_db_type: 'mysql'
})
const jsonSchemaText = ref('')

const form = reactive({
  name: '定时任务',
  schedule_type: 'interval',
  interval_days: 0,
  interval_hours: 1,
  interval_minutes: 0,
  timezone: 'Asia/Shanghai',
  enabled: true,
  change_detect_enabled: true,
  quick_hash_strategy: 'content_only',
  force_full_crawl_every: 10,
  dedup_enabled: true
})

function parseJsonSchema() {
  if (payload.output_mode !== 'json') {
    return null
  }
  const text = jsonSchemaText.value.trim()
  if (!text) {
    return null
  }
  try {
    return JSON.parse(text)
  } catch {
    throw new Error('JSON 结构定义必须是合法 JSON')
  }
}

async function createSchedule() {
  if (!payload.portal_url || !payload.query) {
    ElMessage.warning('请先填写门户 URL 与需求')
    return
  }
  if (!(await ensureModelConfigReady(payload.output_mode))) {
    return
  }

  let jsonSchema = null
  try {
    jsonSchema = parseJsonSchema()
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }

  const req = {
    ...form,
    payload: {
      ...payload,
      json_schema: jsonSchema
    }
  }
  try {
    await api.post('/schedules', req)
    ElMessage.success('调度创建成功')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}
</script>
