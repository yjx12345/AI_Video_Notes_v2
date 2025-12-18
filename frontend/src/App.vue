<template>
  <div class="app-container">
    <TaskSidebar
      :tasks="tasks"
      :currentTaskId="currentTaskId"
      :loading="initLoading"
      @select-task="selectTask"
      @new-task="showUploadDialog = true"
      @open-settings="openSettings"
      @delete-task="deleteTask"
      @rename-task="renameTask"
      @batch-delete="batchDeleteTasks"
    />

    <div class="main-content">
      <!-- 欢迎页 -->
      <div v-if="!currentTask" class="welcome-screen">
        <el-icon size="60"><Notebook /></el-icon>
        <h2>AI 视频笔记助手</h2>
        <p>请新建任务或选择左侧列表</p>
        <el-button type="primary" size="large" @click="showUploadDialog = true">新建任务</el-button>
      </div>

      <!-- 编辑器区域 -->
      <div v-else class="editor-wrapper">
        <div class="content-header">
          <div class="header-row">
            <div class="title-group">
              <h2 class="title">{{ currentTask.title }}</h2>
              <!-- 手动刷新按钮：强制拉取最新数据 -->
              <el-button
                link
                type="primary"
                size="small"
                @click="forceRefreshTask"
                title="强制刷新：拉取服务器最新结果（会覆盖未保存的修改）"
              >
                <el-icon><Refresh /></el-icon> 同步
              </el-button>
            </div>

            <div>
              <el-tag :type="getStatusType(currentTask.status)" style="margin-right: 10px">
                {{ currentTask.status }}
              </el-tag>
            </div>
          </div>
          <el-progress
            v-if="['pending', 'processing_audio', 'transcribing', 'attachment_parsing', 'polishing', 'fusion'].includes(currentTask.status)"
            :percentage="getProgress(currentTask.status)"
            :status="currentTask.status === 'failed' ? 'exception' : ''"
            striped striped-flow
          />
          <div v-if="showAttachmentStatus" class="attachment-status-row">
            <el-tag size="small" :type="getAttachmentTagType(currentTask.attachment_status)">
              {{ getAttachmentStatusLabel(currentTask.attachment_status) }}
            </el-tag>
            <span v-if="currentTask.attachment_error" class="attachment-error">{{ currentTask.attachment_error }}</span>
          </div>
          <div v-if="currentTask.error_message" class="error-msg">错误: {{ currentTask.error_message }}</div>
        </div>

        <div class="editor-container">
          <el-tabs v-model="activeTab" type="border-card" class="editor-tabs">
            <el-tab-pane label="📝 润色文本" name="polished">
              <!-- 改为 @input 实现实时监听，绑定防抖处理 -->
              <el-input
                v-model="currentTask.polished_text"
                type="textarea"
                class="editor-input"
                resize="none"
                @input="handleInput"
              />
            </el-tab-pane>
            <el-tab-pane label="🎙️ 原始转写" name="raw">
              <el-input
                v-model="currentTask.raw_text"
                type="textarea"
                class="editor-input"
                resize="none"
                @input="handleInput"
              />
            </el-tab-pane>
            <el-tab-pane v-if="isAttachmentTabVisible" label="📄 文档解析" name="attachment">
              <div class="attachment-panel">
                <div v-if="!currentTask.attachment_content" class="attachment-hint">
                  {{ normalizeStatus(currentTask.attachment_status) === 'failed' ? '文档解析失败，请查看错误信息' : '文档解析结果尚未生成，请稍候...' }}
                </div>
                <el-input
                  v-else
                  v-model="currentTask.attachment_content"
                  type="textarea"
                  class="editor-input attachment-input"
                  resize="none"
                  :readonly="true"
                />
                <div v-if="currentTask.attachment_error" class="attachment-error-block">
                  {{ currentTask.attachment_error }}
                </div>
              </div>
            </el-tab-pane>
            <el-tab-pane label="📒 最终笔记" name="note">
              <div class="note-toolbar">
                <div class="left">
                  <span>模板:</span>
                  <el-select v-model="selectedTemplateId" placeholder="选择模板" size="small" style="width: 150px; margin: 0 10px;">
                    <el-option v-for="t in templates" :key="t.id" :label="t.name" :value="t.id" />
                  </el-select>
                  <el-button type="primary" size="small" @click="generateNote" :loading="generatingNote">AI 生成</el-button>
                </div>
                <el-button type="success" size="small" @click="exportToObsidian" :disabled="!currentTask.final_note">导出 Obsidian</el-button>
              </div>
              <el-input
                v-model="currentTask.final_note"
                type="textarea"
                class="editor-input"
                resize="none"
                @input="handleInput"
              />
            </el-tab-pane>
          </el-tabs>

          <div class="status-bar">
            <!-- 状态显示区域 -->
            <span v-if="saveStatus" class="save-msg">
              <el-icon v-if="saveStatus.includes('已')"><Check /></el-icon>
              <el-icon v-else class="is-loading"><Loading /></el-icon>
              {{ saveStatus }}
            </span>

            <div class="actions">
              <!-- [新增] 保存按钮 -->
              <el-button type="primary" size="small" @click="manualSave" :loading="isSaving">
                <el-icon><Select /></el-icon> 保存
              </el-button>
              <el-button type="info" plain size="small" @click="copyContent">
                <el-icon><CopyDocument /></el-icon> 复制全文
              </el-button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 弹窗组件 -->
    <UploadDialog v-model="showUploadDialog" @success="refreshList" />
    <SettingsDialog
      v-model="showSettingsDialog"
      @update-templates="fetchTemplates"
      @settings-saved="reloadSettings"
    />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { Refresh, CopyDocument, Check, Notebook, Delete, Edit, Select, Loading } from '@element-plus/icons-vue'
import { taskApi, settingsApi } from './api'
import TaskSidebar from './components/TaskSidebar.vue'
import UploadDialog from './components/UploadDialog.vue'
import SettingsDialog from './components/SettingsDialog.vue'

// 状态
const tasks = ref([])
const templates = ref([])
const currentTaskId = ref(null)
const currentTask = computed(() => tasks.value.find(t => t.id === currentTaskId.value))
const activeTab = ref('polished')
const initLoading = ref(true)
const saveStatus = ref('')
const isSaving = ref(false)

// [配置] 自动保存延迟 (默认2000ms)，从 localStorage 读取
const autoSaveDelay = ref(parseInt(localStorage.getItem('autoSaveDelay')) || 2000)
const autoSaveTimer = ref(null)

const showUploadDialog = ref(false)
const showSettingsDialog = ref(false)
const selectedTemplateId = ref(null)
const generatingNote = ref(false)

const attachmentStatusText = {
  none: '无附件',
  pending: '附件待解析',
  uploading: '文档上传中',
  processing: '文档解析中',
  done: '文档解析完成',
  failed: '文档解析失败'
}
const attachmentTagTypeMap = {
  pending: 'warning',
  uploading: 'warning',
  processing: 'warning',
  done: 'success',
  failed: 'danger'
}

// === 工具函数: 统一处理附件状态大小写 ===
// 后端现在返回大写 (NONE, DONE)，前端兼容处理
const normalizeStatus = (status) => {
  return status ? status.toLowerCase() : 'none'
}

const showAttachmentStatus = computed(() => {
  return !!(currentTask.value && currentTask.value.attachment_status && normalizeStatus(currentTask.value.attachment_status) !== 'none')
})

const isAttachmentTabVisible = computed(() => {
  if (!currentTask.value) return false
  const status = normalizeStatus(currentTask.value.attachment_status)
  const content = currentTask.value.attachment_content
  return (status && status !== 'none') || (content && content.trim())
})

const getAttachmentStatusLabel = (status) => attachmentStatusText[normalizeStatus(status)] || status
const getAttachmentTagType = (status) => attachmentTagTypeMap[normalizeStatus(status)] || 'info'

// 初始化
const initData = async () => {
  try {
    await refreshList()
    await fetchTemplates()
  } finally {
    initLoading.value = false
  }
}

// 当设置保存时触发，重新加载延迟配置
const reloadSettings = () => {
  const delay = parseInt(localStorage.getItem('autoSaveDelay'))
  if (!isNaN(delay)) {
    autoSaveDelay.value = delay
  }
}

const refreshList = async () => {
  try {
    const res = await taskApi.list()
    if (currentTask.value) {
      tasks.value = res.data.map(rt => {
        if (rt.id === currentTaskId.value) {
          const local = currentTask.value
          // 仅当本地有内容时保留本地内容，否则使用服务器最新内容
          return {
            ...rt,
            raw_text: (local.raw_text && local.raw_text.trim()) ? local.raw_text : rt.raw_text,
            polished_text: (local.polished_text && local.polished_text.trim()) ? local.polished_text : rt.polished_text,
            final_note: (local.final_note && local.final_note.trim()) ? local.final_note : rt.final_note
          }
        }
        return rt
      })
    } else {
      tasks.value = res.data
    }
  } catch (e) { console.error('刷新列表失败', e) }
}

const forceRefreshTask = async () => {
  try {
    const res = await taskApi.list()
    tasks.value = res.data
    ElMessage.success('已同步最新状态')
  } catch (e) {
    ElMessage.error('同步失败')
  }
}

const fetchTemplates = async () => {
  try {
    const res = await settingsApi.getTemplates()
    templates.value = res.data
    if (templates.value.length > 0 && !selectedTemplateId.value) {
      selectedTemplateId.value = templates.value[0].id
    }
  } catch (e) { console.error('获取模板失败', e) }
}

onMounted(() => {
  initData()
  // 建议增加清理定时器的逻辑
  const timer = setInterval(refreshList, 5000)
  // 在非 setup script 中通常需要 onUnmounted 清理，但这里是 setup 简单示例暂且保留
})

// 业务逻辑
const selectTask = (task) => {
  currentTaskId.value = task.id
  const status = normalizeStatus(task.attachment_status)
  const hasAttachment = (status && status !== 'none') || (task.attachment_content && task.attachment_content.trim())

  if (task.source_type === 'document') {
    activeTab.value = hasAttachment ? 'attachment' : 'note'
  } else if (!hasAttachment && activeTab.value === 'attachment') {
    activeTab.value = 'polished'
  } else if (task.status === 'completed' && activeTab.value === 'raw') {
    activeTab.value = 'polished'
  }
  saveStatus.value = '' // 切换任务时清空保存状态
}

const openSettings = () => {
  fetchTemplates()
  showSettingsDialog.value = true
}

// === [核心逻辑] 防抖输入处理 ===
const handleInput = () => {
  saveStatus.value = '正在输入...' // 实时反馈

  if (autoSaveTimer.value) {
    clearTimeout(autoSaveTimer.value)
  }

  autoSaveTimer.value = setTimeout(() => {
    saveTaskContent(true) // true 表示这是自动保存
  }, autoSaveDelay.value)
}

const manualSave = () => {
  if (autoSaveTimer.value) clearTimeout(autoSaveTimer.value) // 清除待执行的自动保存
  saveTaskContent(false) // false 表示这是手动保存
}

const saveTaskContent = async (isAuto = false) => {
  if (!currentTask.value) return

  isSaving.value = true
  saveStatus.value = isAuto ? '自动保存中...' : '正在保存...'

  try {
    await taskApi.updateContent(currentTask.value.id, {
      raw_text: currentTask.value.raw_text,
      polished_text: currentTask.value.polished_text,
      final_note: currentTask.value.final_note
    })
    const time = new Date().toLocaleTimeString()
    saveStatus.value = isAuto ? `已自动保存 ${time}` : `已保存 ${time}`
    if (!isAuto) ElMessage.success('保存成功')
  } catch (e) {
    // 修复点：这里原来是 catch (} finally {，语法错误
    console.error('保存失败', e)
    saveStatus.value = '保存失败'
    if (!isAuto) ElMessage.error('保存失败')
  } finally {
    isSaving.value = false
  }
}

const deleteTask = async (id) => {
  try {
    await ElMessageBox.confirm('确定删除该任务及文件吗?', '警告', { type: 'warning' })
    await taskApi.delete(id)
    if (currentTaskId.value === id) currentTaskId.value = null
    refreshList()
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

const batchDeleteTasks = async (ids, onSuccess) => {
  try {
    await ElMessageBox.confirm(`确定要批量删除选中的 ${ids.length} 个任务吗?`, '警告', { type: 'warning' })
    const deletePromises = ids.map(id => taskApi.delete(id))
    await Promise.all(deletePromises)
    if (ids.includes(currentTaskId.value)) currentTaskId.value = null
    await refreshList()
    ElMessage.success('批量删除成功')
    if (onSuccess) onSuccess()
  } catch (e) {
    if (e !== 'cancel') ElMessage.error('批量删除过程中出现错误')
  }
}

const renameTask = async (task) => {
  try {
    const { value } = await ElMessageBox.prompt('请输入新标题', '重命名', {
      inputValue: task.title,
      confirmButtonText: '确定',
      cancelButtonText: '取消'
    })
    if (value && value !== task.title) {
      await taskApi.updateContent(task.id, { title: value })
      refreshList()
      ElMessage.success('重命名成功')
    }
  } catch (e) {
    if (e !== 'cancel') console.error(e)
  }
}

const generateNote = async () => {
  if (!selectedTemplateId.value) return ElMessage.warning('请选择模板')
  generatingNote.value = true
  try {
    const res = await taskApi.generateNote(currentTask.value.id, selectedTemplateId.value)
    if (currentTask.value) {
        currentTask.value.final_note = res.data.final_note
        saveTaskContent(true) // 生成后触发一次自动保存
    }
    ElMessage.success('生成成功')
  } catch (e) {
    console.error(e)
    ElMessage.error('生成笔记失败')
  }
  finally { generatingNote.value = false }
}

const exportToObsidian = async () => {
  try {
    const res = await taskApi.exportObsidian(currentTask.value.id)
    ElMessage.success(`导出成功: ${res.data.path}`)
  } catch (e) {
    console.error(e)
    ElMessage.error('导出失败')
  }
}

const copyContent = async () => {
  if (!currentTask.value) return

  // 1. 确定要复制的内容
  let textToCopy = ''
  if (activeTab.value === 'raw') textToCopy = currentTask.value.raw_text
  else if (activeTab.value === 'polished') textToCopy = currentTask.value.polished_text
  else if (activeTab.value === 'attachment') textToCopy = currentTask.value.attachment_content
  else if (activeTab.value === 'note') textToCopy = currentTask.value.final_note

  if (!textToCopy) {
    ElMessage.info('当前区域没有内容可复制')
    return
  }

  // 2. 执行复制逻辑 (带降级方案)
  try {
    // 方案 A: 尝试使用现代异步 API (仅限 HTTPS 或 localhost)
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(textToCopy)
      ElMessage.success('已复制到剪贴板')
    } else {
      // 如果 API 不可用，主动抛出异常进入 catch
      throw new Error('Clipboard API unavailable')
    }
  } catch (e) {
    // 方案 B: 兼容模式 (创建一个隐藏的输入框来选中复制)
    try {
      const textarea = document.createElement('textarea')
      textarea.value = textToCopy
      // 防止滚动和闪烁
      textarea.style.position = 'fixed'
      textarea.style.left = '-9999px'
      textarea.style.top = '0'
      document.body.appendChild(textarea)

      textarea.focus()
      textarea.select()

      const successful = document.execCommand('copy')
      document.body.removeChild(textarea)

      if (successful) {
        ElMessage.success('已复制到剪贴板')
      } else {
        ElMessage.error('复制失败，请尝试手动选中复制')
      }
    } catch (err) {
      console.error('复制出错:', err)
      ElMessage.error('复制失败')
    }
  }
}

const getStatusType = (s) => {
  if (s === 'completed') return 'success'
  if (s === 'failed') return 'danger'
  if (s === 'fusion') return 'info'
  return 'warning'
}

const progressMap = {
  pending: 10,
  processing_audio: 30,
  transcribing: 55,
  attachment_parsing: 65,
  polishing: 80,
  fusion: 90,
  completed: 100
}
const getProgress = (s) => progressMap[s] || 0
</script>

<style scoped>
.app-container { display: flex; height: 100vh; background-color: #f5f7fa; font-family: 'Segoe UI', sans-serif; }
.main-content { flex: 1; padding: 20px; overflow-y: auto; display: flex; flex-direction: column; }
.welcome-screen { height: 100%; display: flex; flex-direction: column; align-items: center; justify-content: center; color: #909399; }
.welcome-screen h2 { margin: 20px 0 10px; }

.editor-wrapper { height: 100%; display: flex; flex-direction: column; }
.content-header { margin-bottom: 20px; background: #fff; padding: 20px; border-radius: 8px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.05); flex-shrink: 0; }
.header-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }

/* 标题区域样式 */
.title-group { display: flex; align-items: center; gap: 10px; }
.title { margin: 0; font-size: 1.2rem; }

.error-msg { color: #f56c6c; margin-top: 10px; font-size: 13px; }
.attachment-status-row { margin-top: 10px; display: flex; align-items: center; gap: 10px; font-size: 13px; }
.attachment-error { color: #f56c6c; }

.editor-container { background: #fff; border-radius: 8px; box-shadow: 0 2px 12px 0 rgba(0,0,0,0.05); flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.editor-tabs { flex: 1; display: flex; flex-direction: column; border: none; box-shadow: none; height: 0; }
:deep(.el-tabs__content) { flex: 1; padding: 0 !important; display: flex; flex-direction: column; overflow: hidden;}
:deep(.el-tab-pane) { height: 100%; display: flex; flex-direction: column; }
.editor-input { flex: 1; height: 100%; }
:deep(.el-textarea__inner) { height: 100% !important; box-shadow: none; border-radius: 0; padding: 20px; font-family: 'Consolas', monospace; font-size: 14px; line-height: 1.6; border: none; resize: none; }
.attachment-input :deep(.el-textarea__inner) { background: #fafafa; cursor: default; }
.attachment-panel { flex: 1; display: flex; flex-direction: column; }
.attachment-hint { padding: 20px; color: #909399; font-size: 13px; }
.attachment-error-block { margin-top: 10px; color: #f56c6c; font-size: 13px; }
.note-toolbar { background: #f0f9eb; padding: 10px 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e1f3d8; flex-shrink: 0; }

/* 底部状态栏样式优化 */
.status-bar {
  padding: 10px 20px; background: #f5f7fa; border-top: 1px solid #e4e7ed; font-size: 12px; flex-shrink: 0;
  display: flex; justify-content: space-between; align-items: center;
}
.save-msg { color: #67c23a; display: flex; align-items: center; gap: 5px; }
.actions { display: flex; gap: 10px; }
</style>