<template>
  <el-dialog
    v-model="visible"
    title="软件设置"
    width="650px"
    @open="loadConfig"
  >
    <el-form label-position="top" v-loading="loading">

      <!-- 1. 常规设置 (新增) -->
      <el-divider content-position="left">⚙️ 常规设置</el-divider>
      <el-form-item label="自动保存延迟 (秒)">
        <el-input-number
          v-model="autoSaveDelaySec"
          :min="1"
          :max="60"
          style="width: 150px;"
          placeholder="默认 2"
        />
        <span style="margin-left: 10px; font-size: 12px; color: #909399;">
          停止打字 {{ autoSaveDelaySec }} 秒后自动保存
        </span>
      </el-form-item>

      <!-- 2. 存储设置 -->
      <el-divider content-position="left">📂 存储设置</el-divider>
      <el-form-item label="Obsidian 库路径 (本地文件夹)">
        <el-input v-model="configForm.obsidian_path" placeholder="例如: D:\MyNotes" />
      </el-form-item>

      <!-- 3. API 设置 -->
      <el-divider content-position="left">🔗 API 密钥配置</el-divider>
      <el-form-item label="SiliconFlow API Key (ASR)">
        <el-input v-model="configForm.siliconflow_key" placeholder="sk-..." show-password />
      </el-form-item>
      <el-form-item label="CREC API Key (LLM)">
        <el-input v-model="configForm.crec_key" placeholder="sk-..." show-password />
      </el-form-item>

      <el-divider content-position="left">📄 MinerU 文档解析</el-divider>
      <el-form-item label="MinerU API Token">
        <el-input v-model="configForm.mineru_api_token" placeholder="Bearer Token" show-password />
      </el-form-item>
      <el-form-item label="解析模式">
        <el-radio-group v-model="configForm.mineru_model_mode">
          <el-radio label="vlm">VLM（推荐，图文理解能力强）</el-radio>
          <el-radio label="pipeline">Pipeline（快速文本解析）</el-radio>
        </el-radio-group>
      </el-form-item>

      <!-- 4. 模板管理 (增强) -->
      <el-divider content-position="left">📝 笔记模板管理</el-divider>
      <div class="template-list">
        <div v-for="t in templates" :key="t.id" class="template-item" :class="{ 'is-editing': editingId === t.id }">
          <div class="tpl-header">
            <strong>{{ t.name }}</strong>
            <div class="tpl-actions">
              <el-button type="primary" link size="small" @click="editTemplate(t)">
                {{ editingId === t.id ? '正在编辑' : '编辑' }}
              </el-button>
              <el-button type="danger" link size="small" @click="deleteTemplate(t.id)" :disabled="editingId === t.id">删除</el-button>
            </div>
          </div>
          <div class="tpl-preview">{{ t.prompt_content.substring(0, 60) }}...</div>
        </div>
      </div>

      <!-- 添加/编辑模板表单 -->
      <div class="add-template-box">
        <div class="box-title">{{ editingId ? '✏️ 编辑模板' : '➕ 添加新模板' }}</div>
        <el-input v-model="tplForm.name" placeholder="模板名称" size="small" style="margin-bottom: 5px;" />
        <el-input v-model="tplForm.prompt" type="textarea" :rows="3" placeholder="输入 Prompt..." size="small" />

        <div style="margin-top: 5px; display: flex; gap: 10px;">
          <el-button type="primary" size="small" @click="saveTemplate">
            {{ editingId ? '更新模板' : '添加模板' }}
          </el-button>
          <el-button v-if="editingId" size="small" @click="cancelEdit">取消编辑</el-button>
        </div>
      </div>
    </el-form>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">关闭</el-button>
        <el-button type="primary" @click="saveConfig">保存设置</el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { settingsApi } from '../api'

const props = defineProps(['modelValue'])
const emit = defineEmits(['update:modelValue', 'update-templates', 'settings-saved'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const loading = ref(false)
const configForm = reactive({
  obsidian_path: '',
  siliconflow_key: '',
  crec_key: '',
  mineru_api_token: '',
  mineru_model_mode: 'vlm'
})

// 自动保存延迟 (本地状态，单位秒)
const autoSaveDelaySec = ref(2)

const templates = ref([])
// 模板表单
const tplForm = reactive({ name: '', prompt: '' })
const editingId = ref(null) // 当前正在编辑的模板ID，null表示新增模式

const loadConfig = async () => {
  loading.value = true
  editingId.value = null
  resetTplForm()

  // 读取本地存储的延迟设置
  const localDelay = localStorage.getItem('autoSaveDelay')
  autoSaveDelaySec.value = localDelay ? parseInt(localDelay) / 1000 : 2

  try {
    const [confRes, tplRes] = await Promise.all([
      settingsApi.getConfig(),
      settingsApi.getTemplates()
    ])

    // 填充配置
    configForm.obsidian_path = confRes.data.obsidian_path
    configForm.siliconflow_key = confRes.data.siliconflow_key
    configForm.crec_key = confRes.data.crec_key
    configForm.mineru_api_token = confRes.data.mineru_api_token
    configForm.mineru_model_mode = confRes.data.mineru_model_mode || 'vlm'

    // 填充模板
    templates.value = tplRes.data
  } catch (e) {
    // api.js 已处理错误提示
  } finally {
    loading.value = false
  }
}

const saveConfig = async () => {
  try {
    await settingsApi.updateConfig(configForm)

    // 保存延迟设置到本地存储 (转换为毫秒)
    localStorage.setItem('autoSaveDelay', autoSaveDelaySec.value * 1000)

    ElMessage.success('设置已保存')
    visible.value = false
    emit('settings-saved') // 通知父组件重新读取设置
  } catch (e) {}
}

// === 模板逻辑 ===

const resetTplForm = () => {
  tplForm.name = ''
  tplForm.prompt = ''
  editingId.value = null
}

const editTemplate = (t) => {
  editingId.value = t.id
  tplForm.name = t.name
  tplForm.prompt = t.prompt_content
}

const cancelEdit = () => {
  resetTplForm()
}

const saveTemplate = async () => {
  if (!tplForm.name || !tplForm.prompt) return ElMessage.warning('请填写完整')

  try {
    if (editingId.value) {
      // 更新模式
      await settingsApi.updateTemplate(editingId.value, {
        name: tplForm.name,
        prompt_content: tplForm.prompt
      })
      ElMessage.success('模板已更新')
    } else {
      // 新增模式
      await settingsApi.addTemplate({
        name: tplForm.name,
        prompt_content: tplForm.prompt
      })
      ElMessage.success('模板添加成功')
    }

    // 刷新列表并重置表单
    const res = await settingsApi.getTemplates()
    templates.value = res.data
    emit('update-templates') // 通知父组件更新下拉框
    resetTplForm()
  } catch (e) {}
}

const deleteTemplate = async (id) => {
  try {
    await ElMessageBox.confirm('确定删除该模板吗?', '提示', { type: 'warning' })
    await settingsApi.deleteTemplate(id)
    const res = await settingsApi.getTemplates()
    templates.value = res.data
    emit('update-templates')
    // 如果删除的是正在编辑的，重置表单
    if (editingId.value === id) resetTplForm()
  } catch (e) {}
}
</script>

<style scoped>
.template-list { max-height: 180px; overflow-y: auto; margin-bottom: 10px; }
.template-item { border: 1px solid #eee; padding: 8px 10px; border-radius: 4px; margin-bottom: 6px; transition: all 0.3s; }
.template-item.is-editing { border-color: #409eff; background-color: #ecf5ff; }

.tpl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px; }
.tpl-preview { font-size: 12px; color: #909399; white-space: pre-wrap; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }

.add-template-box { background: #f9f9f9; padding: 12px; border-radius: 4px; border: 1px dashed #dcdfe6; }
.box-title { font-size: 13px; font-weight: bold; margin-bottom: 8px; color: #606266; }
</style>