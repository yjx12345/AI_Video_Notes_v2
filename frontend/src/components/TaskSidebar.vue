<template>
  <div class="sidebar">
    <div class="sidebar-header">
      <!-- 默认模式头部 -->
      <div v-if="!isBatchMode" class="header-default">
        <h2>📚 笔记列表</h2>
        <div class="header-actions">
          <el-button link type="primary" size="small" @click="enterBatchMode">管理</el-button>
          <el-button type="info" size="small" circle @click="$emit('open-settings')" title="设置">
            <el-icon><Setting /></el-icon>
          </el-button>
          <el-button type="primary" size="small" circle @click="$emit('new-task')" title="新建">
            <el-icon><Plus /></el-icon>
          </el-button>
        </div>
      </div>

      <!-- 批量模式头部 -->
      <div v-else class="header-batch">
        <el-checkbox
          v-model="checkAll"
          :indeterminate="isIndeterminate"
          @change="handleCheckAllChange"
        >全选</el-checkbox>
        <div class="batch-actions">
          <el-button
            type="danger"
            link
            size="small"
            :disabled="selectedIds.length === 0"
            @click="emitBatchDelete"
          >
            删除({{ selectedIds.length }})
          </el-button>
          <el-button link size="small" @click="exitBatchMode">完成</el-button>
        </div>
      </div>
    </div>

    <div class="task-list" v-loading="loading">
      <el-empty v-if="tasks.length === 0" description="暂无任务" :image-size="60"></el-empty>
      <div
        v-for="task in tasks"
        :key="task.id"
        class="task-item"
        :class="{ active: currentTaskId === task.id }"
        @click="handleItemClick(task)"
      >
        <!-- 批量模式复选框 -->
        <div v-if="isBatchMode" class="task-checkbox" @click.stop>
           <el-checkbox
             v-model="selectedIds"
             :label="task.id"
             @change="handleCheckedTasksChange"
           >&nbsp;</el-checkbox>
        </div>

        <div class="task-info">
          <div class="task-title" :title="task.title">{{ task.title }}</div>
          <div class="task-meta">
            <span>
              <span class="status-dot" :class="getStatusClass(task.status)"></span>
              {{ getStatusText(task.status) }}
            </span>
            <span>{{ formatDate(task.created_at) }}</span>
          </div>
          <div v-if="task.attachment_status && task.attachment_status !== 'none'" class="task-attachment-meta">
            <el-tag size="small" :type="getAttachmentTagType(task.attachment_status)">
              {{ getAttachmentStatusText(task.attachment_status) }}
            </el-tag>
          </div>
        </div>

        <!-- 悬浮操作按钮 (仅在非批量模式显示) -->
        <div v-if="!isBatchMode" class="task-actions">
          <el-button link type="primary" size="small" @click.stop="$emit('rename-task', task)" title="重命名">
            <el-icon><Edit /></el-icon>
          </el-button>
          <el-button link type="danger" size="small" @click.stop="$emit('delete-task', task.id)" title="删除">
            <el-icon><Delete /></el-icon>
          </el-button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { formatDate } from '../utils'
import { Setting, Plus, Delete, Edit } from '@element-plus/icons-vue'

const props = defineProps(['tasks', 'currentTaskId', 'loading'])
const emit = defineEmits(['select-task', 'new-task', 'open-settings', 'delete-task', 'rename-task', 'batch-delete'])

const attachmentStatusText = {
  pending: '附件待解析',
  uploading: '文档上传中',
  processing: '文档解析中',
  done: '文档已解析',
  failed: '文档解析失败'
}
const attachmentTagTypeMap = {
  pending: 'warning',
  uploading: 'warning',
  processing: 'warning',
  done: 'success',
  failed: 'danger'
}

// 状态管理
const isBatchMode = ref(false)
const selectedIds = ref([])
const checkAll = ref(false)
const isIndeterminate = ref(false)

// 计算所有 ID
const allTaskIds = computed(() => props.tasks.map(t => t.id))

// 监听任务列表变化，自动清理已不存在的选中项
watch(() => props.tasks, (newTasks) => {
  const currentIds = new Set(newTasks.map(t => t.id))
  selectedIds.value = selectedIds.value.filter(id => currentIds.has(id))
  handleCheckedTasksChange(selectedIds.value)
})

// === 批量操作逻辑 ===
const enterBatchMode = () => {
  isBatchMode.value = true
}

const exitBatchMode = () => {
  isBatchMode.value = false
  selectedIds.value = []
  isIndeterminate.value = false
  checkAll.value = false
}

const handleCheckAllChange = (val) => {
  selectedIds.value = val ? allTaskIds.value : []
  isIndeterminate.value = false
}

const handleCheckedTasksChange = (value) => {
  const checkedCount = value.length
  checkAll.value = checkedCount === props.tasks.length && props.tasks.length > 0
  isIndeterminate.value = checkedCount > 0 && checkedCount < props.tasks.length
}

const handleItemClick = (task) => {
  if (isBatchMode.value) {
    // 批量模式下点击行 = 切换选中状态
    const index = selectedIds.value.indexOf(task.id)
    if (index > -1) {
      selectedIds.value.splice(index, 1)
    } else {
      selectedIds.value.push(task.id)
    }
    handleCheckedTasksChange(selectedIds.value)
  } else {
    // 普通模式下点击行 = 选择任务
    emit('select-task', task)
  }
}

const emitBatchDelete = () => {
  if (selectedIds.value.length === 0) return
  emit('batch-delete', [...selectedIds.value], () => {
    // 回调函数：删除成功后退出批量模式或清空
    selectedIds.value = []
    handleCheckedTasksChange([])
  })
}

// === 辅助函数 ===
const getStatusText = (s) => ({
  'pending': '等待',
  'processing_audio': '提取音频',
  'transcribing': '转写',
  'attachment_parsing': '文档解析',
  'polishing': '润色',
  'fusion': '融合生成',
  'completed': '完成',
  'failed': '失败'
}[s] || s)
const getStatusClass = (s) => {
  if (s === 'completed') return 'status-completed'
  if (s === 'failed') return 'status-failed'
  return 'status-processing'
}
const getAttachmentStatusText = (s) => attachmentStatusText[s] || s
const getAttachmentTagType = (s) => attachmentTagTypeMap[s] || 'info'
</script>

<style scoped>
.sidebar { width: 300px; background: #fff; border-right: 1px solid #e6e6e6; display: flex; flex-direction: column; }
.sidebar-header { padding: 15px 20px; border-bottom: 1px solid #ebeef5; height: 60px; box-sizing: border-box; display: flex; align-items: center; }

/* 头部布局 */
.header-default, .header-batch { display: flex; justify-content: space-between; align-items: center; width: 100%; }
.header-default h2 { margin: 0; font-size: 18px; color: #303133; }
.header-actions { display: flex; align-items: center; gap: 5px; }
.batch-actions { display: flex; gap: 10px; }

.task-list { flex: 1; overflow-y: auto; padding: 10px; }

.task-item {
  padding: 12px 15px; border-radius: 8px; cursor: pointer; margin-bottom: 8px;
  border: 1px solid transparent; display: flex; align-items: center;
  establishedposition: relative; transition: all 0.2s;
}
.task-item:hover { background-color: #f5f7fa; }
task-item.active { background-color: #ecf5ff; border-color: #409eff; }

.task-checkbox { margin-right: 10px; display: flex; align-items: center; }
:deep(.el-checkbox) { margin-right: 0; height: auto; }

task-info { flex: 1; overflow: hidden; }
task-title { font-weight: bold; margin-bottom: 5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 14px; }
task-meta { font-size: 12px; color: #909399; display: flex; justify-content: space-between; align-items: center; }
task-attachment-meta { margin-top: 6px; }

task-actions { display: none; margin-left: 5px; }
task-item:hover .task-actions { display: flex; }

status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 5px; }
status-completed { background-color: #67c23a; }
status-processing { background-color: #e6a23c; animation: blink 1s infinite; }
status-failed { background-color: #f56c6c; }
status-pending { background-color: #909399; }
@keyframes blink { 0% { opacity: 1; } 50% { opacity: 0.5; } 100% { opacity: 1; } }
</style>