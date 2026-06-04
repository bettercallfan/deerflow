<template>
  <section class="panel">
    <h2>模型配置</h2>
    <p class="page-note">
      这里分别配置 Agent导航模型与单页面信息抽取模型。前者负责站内导航，模型越大效果通常越好；后者负责结构化抽取，4B 左右的小模型通常就够用。
    </p>

    <div class="status-grid">
      <div v-for="item in configs" :key="item.target" class="status-card">
        <div class="status-card-head">
          <strong>{{ item.label }}</strong>
          <el-tag :type="item.is_configured ? 'success' : 'warning'" effect="light">
            {{ item.is_configured ? '已配置' : '未配置' }}
          </el-tag>
        </div>
        <p class="field-note">当前模型：{{ item.model_name || '未设置' }}</p>
        <p class="field-note">当前地址：{{ item.base_url || '未设置' }}</p>
        <p class="field-note">凭证状态：{{ item.has_api_key ? '已设置' : '未设置' }}</p>
      </div>
    </div>
  </section>

  <section class="panel">
    <h3>Agent导航模型</h3>
    <p class="page-note">推荐选择能力更强的模型，它会直接影响站内导航、翻页和目标页面命中效果。</p>
    <el-form :model="crawlerForm" label-width="140px">
      <el-form-item label="API Key">
        <el-input
          v-model="crawlerForm.api_key"
          show-password
          placeholder="首次保存必填；后续留空表示保持现有 API Key 不变"
        />
      </el-form-item>
      <el-form-item label="Base URL">
        <el-input v-model="crawlerForm.base_url" placeholder="https://api.example.com/v1" />
      </el-form-item>
      <el-form-item label="Model Name">
        <el-input v-model="crawlerForm.model_name" placeholder="例如：qwen3.5-32b" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="saveConfig('crawler_agent', crawlerForm)">验证并保存 Agent导航模型</el-button>
      </el-form-item>
    </el-form>
  </section>

  <section class="panel">
    <h3>单页面信息抽取模型</h3>
    <p class="page-note">这个模型主要负责单页结构化抽取，4B 左右通常即可；如果更关注成本，可以优先把小模型放在这里。</p>
    <el-form :model="recursiveForm" label-width="140px">
      <el-form-item label="API Key">
        <el-input
          v-model="recursiveForm.api_key"
          show-password
          placeholder="首次保存必填；后续留空表示保持现有 API Key 不变"
        />
      </el-form-item>
      <el-form-item label="Base URL">
        <el-input v-model="recursiveForm.base_url" placeholder="https://api.example.com/v1" />
      </el-form-item>
      <el-form-item label="Model Name">
        <el-input v-model="recursiveForm.model_name" placeholder="例如：qwen2.5-4b" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="saveConfig('recursive_acquisition', recursiveForm)">验证并保存单页面信息抽取模型</el-button>
      </el-form-item>
    </el-form>
  </section>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'
import { fetchModelConfigs } from '../utils/modelConfig'

const configs = ref([])

const crawlerForm = reactive({
  api_key: '',
  base_url: '',
  model_name: ''
})

const recursiveForm = reactive({
  api_key: '',
  base_url: '',
  model_name: ''
})

function syncForms(items) {
  const crawlerConfig = items.find((item) => item.target === 'crawler_agent')
  const recursiveConfig = items.find((item) => item.target === 'recursive_acquisition')

  crawlerForm.api_key = ''
  crawlerForm.base_url = crawlerConfig?.base_url || ''
  crawlerForm.model_name = crawlerConfig?.model_name || ''

  recursiveForm.api_key = ''
  recursiveForm.base_url = recursiveConfig?.base_url || ''
  recursiveForm.model_name = recursiveConfig?.model_name || ''
}

async function fetchConfigs() {
  const items = await fetchModelConfigs()
  configs.value = items
  syncForms(items)
}

async function saveConfig(target, form) {
  try {
    await api.put(`/model-configs/${target}`, { ...form })
    ElMessage.success('模型配置验证通过并已保存')
    await fetchConfigs()
  } catch (error) {
    ElMessage.error(error.response?.data?.detail || error.message)
  }
}

onMounted(() => {
  fetchConfigs()
})
</script>
