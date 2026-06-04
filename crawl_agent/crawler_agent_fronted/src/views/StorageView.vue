<template>
  <section class="panel">
    <h2>数据库配置管理</h2>
    <p class="page-note">维护 MySQL 与 Milvus 连接配置，任务执行时直接选择其一写入。</p>
    <el-tabs>
      <el-tab-pane label="MySQL配置">
        <el-form :model="mysqlForm" label-width="130px">
          <el-form-item label="名称"><el-input v-model="mysqlForm.name" /></el-form-item>
          <el-form-item label="Host"><el-input v-model="mysqlForm.host" /></el-form-item>
          <el-form-item label="Port"><el-input-number v-model="mysqlForm.port" :min="1" :max="65535" /></el-form-item>
          <el-form-item label="用户名"><el-input v-model="mysqlForm.username" /></el-form-item>
          <el-form-item label="密码"><el-input v-model="mysqlForm.password" show-password /></el-form-item>
          <el-form-item label="数据库"><el-input v-model="mysqlForm.database" /></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="createMySQL">保存MySQL配置</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>

      <el-tab-pane label="Milvus配置">
        <el-form :model="milvusForm" label-width="130px">
          <el-form-item label="名称"><el-input v-model="milvusForm.name" /></el-form-item>
          <el-form-item label="URI"><el-input v-model="milvusForm.uri" /></el-form-item>
          <el-form-item label="Token"><el-input v-model="milvusForm.token" show-password /></el-form-item>
          <el-form-item label="Collection前缀"><el-input v-model="milvusForm.collection_prefix" /></el-form-item>
          <el-form-item>
            <el-button type="primary" @click="createMilvus">保存Milvus配置</el-button>
          </el-form-item>
        </el-form>
      </el-tab-pane>
    </el-tabs>
  </section>

  <section class="panel">
    <h3>配置列表</h3>
    <div class="actions-row">
      <el-button @click="fetchConfigs">刷新</el-button>
    </div>
    <el-table :data="configs" style="margin-top:12px">
      <el-table-column prop="id" label="ID" min-width="220" />
      <el-table-column prop="name" label="名称" min-width="130" />
      <el-table-column prop="db_type" label="类型" width="110" />
      <el-table-column prop="last_test_status" label="最近测试" width="120" />
      <el-table-column label="操作" width="250">
        <template #default="{ row }">
          <el-space>
            <el-button size="small" @click="testConfig(row.id)">测试连接</el-button>
            <el-button size="small" type="danger" @click="removeConfig(row.id)">删除</el-button>
          </el-space>
        </template>
      </el-table-column>
    </el-table>
  </section>

</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import api from '../api/client'

const configs = ref([])

const mysqlForm = reactive({
  name: 'mysql-prod',
  host: '127.0.0.1',
  port: 3306,
  username: 'root',
  password: '',
  database: 'crawler_data',
  charset: 'utf8mb4'
})

const milvusForm = reactive({
  name: 'milvus-main',
  uri: 'http://127.0.0.1:19530',
  token: '',
  db_name: 'default',
  collection_prefix: 'crawler',
  dimension: 1024,
  metric_type: 'IP',
  index_type: 'AUTOINDEX'
})

async function fetchConfigs() {
  const { data } = await api.get('/storage/configs')
  configs.value = data
}

async function createMySQL() {
  await api.post('/storage/configs/mysql', mysqlForm)
  ElMessage.success('MySQL配置已保存')
  fetchConfigs()
}

async function createMilvus() {
  await api.post('/storage/configs/milvus', milvusForm)
  ElMessage.success('Milvus配置已保存')
  fetchConfigs()
}

async function testConfig(id) {
  const { data } = await api.post(`/storage/configs/${id}/test`)
  ElMessage.info(`${data.success ? '成功' : '失败'}: ${data.message}`)
  fetchConfigs()
}

async function removeConfig(id) {
  await api.delete(`/storage/configs/${id}`)
  ElMessage.success('配置已删除')
  fetchConfigs()
}

onMounted(() => {
  fetchConfigs()
})
</script>
