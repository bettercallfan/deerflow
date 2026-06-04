import { ElMessageBox } from 'element-plus'
import api from '../api/client'

const TARGET_LABELS = {
  crawler_agent: 'Agent导航模型',
  recursive_acquisition: '单页面信息抽取模型'
}

const REQUIRED_TARGETS = {
  json: ['crawler_agent', 'recursive_acquisition'],
  markdown: ['crawler_agent'],
  html: ['crawler_agent']
}

export async function fetchModelConfigs() {
  const { data } = await api.get('/model-configs')
  return data.items || []
}

export async function ensureModelConfigReady(outputMode = 'json') {
  const items = await fetchModelConfigs()
  const requiredTargets = REQUIRED_TARGETS[outputMode] || REQUIRED_TARGETS.markdown
  const missingTargets = requiredTargets.filter((target) => {
    const row = items.find((item) => item.target === target)
    return !row?.is_configured
  })

  if (!missingTargets.length) {
    return true
  }

  const targetText = missingTargets.map((target) => TARGET_LABELS[target] || target).join('、')

  try {
    await ElMessageBox.confirm(
      `${targetText} 尚未配置，对应功能暂不可用。请先前往模型配置页面填写 API Key、Base URL 与 Model Name。`,
      '模型配置未完成',
      {
        confirmButtonText: '前往配置',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    const router = (await import('../router')).default
    router.push('/model-config')
  } catch {
    return false
  }

  return false
}
