<template>
  <section class="panel">
    <h2>网页智能化爬取</h2>
    <p class="page-note">给出网站门户URL与所需信息的自然语言描述，系统会自动执行站内导航与信息提取。使用前请先完成 Agent导航模型配置；如果选择 JSON 输出，还需要先配置单页面信息抽取模型。</p>
    <el-form :model="form" label-width="150px">
      <el-form-item label="任务名称">
        <el-input v-model="form.name" placeholder="例如：陕西要闻抓取" />
      </el-form-item>
      <el-form-item label="门户 URL">
        <el-input v-model="form.portal_url" placeholder="https://example.com" />
      </el-form-item>
      <el-form-item label="自然语言需求">
        <el-input v-model="form.query" type="textarea" :rows="4" />
      </el-form-item>
      <el-form-item label="输出模式">
        <el-select v-model="form.output_mode" style="width: 180px">
          <el-option value="json" label="JSON" />
          <el-option value="markdown" label="Markdown" />
          <el-option value="html" label="HTML" />
        </el-select>
      </el-form-item>
      <el-form-item v-if="form.output_mode === 'json'" label="JSON结构定义">
        <div style="width: 100%">
          <el-input
            v-model="jsonSchemaText"
            type="textarea"
            :rows="8"
            placeholder='例如：{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"title":{"type":"string"},"publish_time":{"type":"string"}}}}}}'
          />
          <p class="field-note">如果希望固定 JSON 输出结构，请填写 JSON Schema 或结构模板；该能力会使用单页面信息抽取模型，留空则由系统自动生成结构。</p>
        </div>
      </el-form-item>
      <el-form-item label="存储数据库类型">
        <el-select v-model="form.storage_db_type" style="width: 180px">
          <el-option value="" label="文件（本地输出）" />
          <el-option value="mysql" label="MySQL" />
          <el-option value="milvus" label="Milvus" />
        </el-select>
      </el-form-item>
      <el-form-item class="actions-row">
        <el-button type="primary" :loading="submitting" @click="submit">创建并执行任务</el-button>
      </el-form-item>
    </el-form>

    <el-alert v-if="createdTaskId" type="success" :closable="false" show-icon>
      <template #title>
        已创建任务，任务ID：{{ createdTaskId }}
      </template>
    </el-alert>
  </section>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '../api/client'
import { ensureModelConfigReady } from '../utils/modelConfig'

const submitting = ref(false)
const createdTaskId = ref('')
const jsonSchemaText = ref('')

const form = reactive({
  name: '新建抓取任务',
  portal_url: '',
  query: '',
  output_mode: 'json',
  storage_db_type: 'mysql',
  hash_mode: 'raw+normalized'
})

function parseJsonSchema() {
  if (form.output_mode !== 'json') {
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

async function submit() {
  if (!form.portal_url || !form.query) {
    ElMessage.warning('请先填写门户 URL 与自然语言需求')
    return
  }

  if (!(await ensureModelConfigReady(form.output_mode))) {
    return
  }

  let jsonSchema = null
  try {
    jsonSchema = parseJsonSchema()
  } catch (error) {
    ElMessage.warning(error.message)
    return
  }

  try {
    await ElMessageBox.confirm(
      '该任务可能需要较长执行时间（取决于网站复杂度与页面数量），建议稍后在任务中心查看结果。',
      '任务执行提示',
      {
        confirmButtonText: '继续执行',
        cancelButtonText: '先不执行',
        type: 'warning'
      }
    )
  } catch {
    return
  }

  submitting.value = true
  try {
    const payload = {
      ...form,
      json_schema: jsonSchema,
      storage_db_type: form.storage_db_type || null
    }
    const { data } = await api.post('/crawl/tasks', payload)
    createdTaskId.value = data.id
    ElMessage.success('任务已创建并开始执行')
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  } finally {
    submitting.value = false
  }
}
</script>
