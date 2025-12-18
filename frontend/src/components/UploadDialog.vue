<template>
  <el-dialog
    v-model="visible"
    title="新建任务"
    width="560px"
    @close="resetForm"
  >
    <el-tabs v-model="activeTab">
      <el-tab-pane label="音视频任务" name="media">
        <el-upload
          class="upload-block"
          drag
          action="#"
          :auto-upload="false"
          :on-change="handleMediaChange"
          :on-remove="handleMediaRemove"
          v-model:file-list="mediaFiles"
          multiple
          ref="mediaUploadRef"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            拖拽音视频至此处，或 <em>点击上传</em>
            <div class="tip">支持 .mp4 .mov .avi .mkv .mp3 .wav 等格式</div>
          </div>
        </el-upload>
        <div v-if="mediaFiles.length" class="file-stats">已选择 {{ mediaFiles.length }} 个文件</div>
      </el-tab-pane>

      <el-tab-pane label="文档任务" name="document">
        <el-upload
          class="upload-block"
          drag
          action="#"
          :auto-upload="false"
          :on-change="handleDocumentChange"
          :on-remove="handleDocumentRemove"
          v-model:file-list="documentFiles"
          multiple
          ref="documentUploadRef"
          accept=".pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg"
        >
          <el-icon class="el-icon--upload"><upload-filled /></el-icon>
          <div class="el-upload__text">
            拖拽文档至此处，或 <em>点击上传</em>
            <div class="tip">支持 PDF、Office、图片等格式，单个不超过 200MB</div>
          </div>
        </el-upload>
        <div v-if="documentFiles.length" class="file-stats">已选择 {{ documentFiles.length }} 个文档</div>
      </el-tab-pane>

      <el-tab-pane label="融合任务" name="fusion">
        <div class="fusion-wrapper">
          <el-form label-position="top">
            <el-form-item label="主文件（视频或音频）">
              <el-upload
                class="upload-inline"
                action="#"
                :auto-upload="false"
                :limit="1"
                :on-change="handleFusionMainChange"
                :on-remove="handleFusionMainRemove"
                v-model:file-list="fusionMainList"
                ref="fusionMainUploadRef"
              >
                <el-button type="primary" link>选择文件</el-button>
                <template #tip>
                  <div class="tip">例如课程录像，支持 mp4/mp3 等格式</div>
                </template>
              </el-upload>
              <div v-if="fusionMainList.length" class="fusion-file-name">{{ fusionMainList[0].name }}</div>
            </el-form-item>

            <el-form-item label="课件文档">
              <el-upload
                class="upload-inline"
                action="#"
                :auto-upload="false"
                :limit="1"
                :on-change="handleFusionAttachmentChange"
                :on-remove="handleFusionAttachmentRemove"
                v-model:file-list="fusionAttachmentList"
                ref="fusionAttachmentUploadRef"
                accept=".pdf,.doc,.docx,.ppt,.pptx,.png,.jpg,.jpeg"
              >
                <el-button type="primary" link>选择文档</el-button>
                <template #tip>
                  <div class="tip">上传与课堂对应的讲义/课件</div>
                </template>
              </el-upload>
              <div v-if="fusionAttachmentList.length" class="fusion-file-name">{{ fusionAttachmentList[0].name }}</div>
            </el-form-item>

            <el-form-item label="任务标题 (可选)">
              <el-input v-model="fusionTitle" placeholder="不填写则使用主文件名称" />
            </el-form-item>
          </el-form>
        </div>
      </el-tab-pane>

      <el-tab-pane label="文本输入" name="text">
        <el-input
          v-model="textForm.title"
          placeholder="请输入标题"
          style="margin-bottom: 10px;"
        />
        <el-input
          v-model="textForm.content"
          type="textarea"
          :rows="6"
          placeholder="在此粘贴需要处理的文本..."
        />
      </el-tab-pane>
    </el-tabs>

    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false" :disabled="uploading">取消</el-button>
        <el-button type="primary" @click="submit" :loading="uploading">
          {{ buttonLabel }}
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled } from '@element-plus/icons-vue'
import { taskApi } from '../api'

const props = defineProps(['modelValue'])
const emit = defineEmits(['update:modelValue', 'success'])

const visible = computed({
  get: () => props.modelValue,
  set: (val) => emit('update:modelValue', val)
})

const activeTab = ref('media')
const uploading = ref(false)
const successCount = ref(0)

const mediaUploadRef = ref(null)
const documentUploadRef = ref(null)
const fusionMainUploadRef = ref(null)
const fusionAttachmentUploadRef = ref(null)

const mediaFiles = ref([])
const documentFiles = ref([])
const fusionMainList = ref([])
const fusionAttachmentList = ref([])
const fusionTitle = ref('')

const textForm = reactive({
  title: '',
  content: ''
})

const totalCount = computed(() => {
  switch (activeTab.value) {
    case 'media':
      return mediaFiles.value.length
    case 'document':
      return documentFiles.value.length
    case 'fusion':
      return fusionMainList.value.length && fusionAttachmentList.value.length ? 1 : 0
    case 'text':
      return 1
    default:
      return 0
  }
})

const buttonLabel = computed(() => {
  if (uploading.value) {
    const total = totalCount.value || 1
    return `正在上传 (${successCount.value}/${total})...`
  }
  if (activeTab.value === 'fusion') return '开始融合'
  if (activeTab.value === 'document') return '开始解析'
  return '开始处理'
})

const handleMediaChange = (_, files) => { mediaFiles.value = files }
const handleMediaRemove = (_, files) => { mediaFiles.value = files }
const handleDocumentChange = (_, files) => { documentFiles.value = files }
const handleDocumentRemove = (_, files) => { documentFiles.value = files }
const handleFusionMainChange = (_, files) => { fusionMainList.value = files }
const handleFusionMainRemove = (_, files) => { fusionMainList.value = files }
const handleFusionAttachmentChange = (_, files) => { fusionAttachmentList.value = files }
const handleFusionAttachmentRemove = (_, files) => { fusionAttachmentList.value = files }

const resetForm = () => {
  mediaFiles.value = []
  documentFiles.value = []
  fusionMainList.value = []
  fusionAttachmentList.value = []
  fusionTitle.value = ''
  textForm.title = ''
  textForm.content = ''
  successCount.value = 0
  mediaUploadRef.value?.clearFiles()
  documentUploadRef.value?.clearFiles()
  fusionMainUploadRef.value?.clearFiles()
  fusionAttachmentUploadRef.value?.clearFiles()
}

const getSourceType = (filename) => {
  const ext = filename.split('.').pop().toLowerCase()
  const videoExt = ['mp4', 'mov', 'avi', 'mkv', 'flv']
  const audioExt = ['mp3', 'wav', 'aac', 'm4a', 'ogg']
  if (videoExt.includes(ext)) return 'video'
  if (audioExt.includes(ext)) return 'audio'
  return 'video'
}

const submit = async () => {
  if (activeTab.value === 'media') {
    if (!mediaFiles.value.length) return ElMessage.warning('请先选择音视频文件')
    await handleMediaUpload()
    return
  }

  if (activeTab.value === 'document') {
    if (!documentFiles.value.length) return ElMessage.warning('请先选择文档文件')
    await handleDocumentUpload()
    return
  }

  if (activeTab.value === 'fusion') {
    if (!fusionMainList.value.length || !fusionAttachmentList.value.length) {
      return ElMessage.warning('请同时选择主文件和课件文档')
    }
    await handleFusionUpload()
    return
  }

  if (activeTab.value === 'text') {
    if (!textForm.title) return ElMessage.warning('请输入标题')
    await handleTextSubmit()
  }
}

const handleMediaUpload = async () => {
  uploading.value = true
  successCount.value = 0
  try {
    const uploaders = mediaFiles.value.map(async (fileItem) => {
      const formData = new FormData()
      formData.append('file', fileItem.raw)
      formData.append('source_type', getSourceType(fileItem.name))
      formData.append('title', fileItem.name)
      try {
        await taskApi.upload(formData)
        successCount.value++
      } catch (error) {
        console.error(`文件 ${fileItem.name} 上传失败`, error)
        ElMessage.error(`文件 ${fileItem.name} 上传失败`)
      }
    })
    await Promise.all(uploaders)
    if (successCount.value > 0) {
      ElMessage.success(`成功创建 ${successCount.value} 个任务`)
      visible.value = false
      emit('success')
    }
  } finally {
    uploading.value = false
  }
}

const handleDocumentUpload = async () => {
  uploading.value = true
  successCount.value = 0
  try {
    const uploaders = documentFiles.value.map(async (fileItem) => {
      const formData = new FormData()
      formData.append('file', fileItem.raw)
      formData.append('source_type', 'document')
      formData.append('title', fileItem.name)
      try {
        await taskApi.upload(formData)
        successCount.value++
      } catch (error) {
        console.error(`文档 ${fileItem.name} 上传失败`, error)
        ElMessage.error(`文档 ${fileItem.name} 上传失败`)
      }
    })
    await Promise.all(uploaders)
    if (successCount.value > 0) {
      ElMessage.success(`成功创建 ${successCount.value} 个文档任务`)
      visible.value = false
      emit('success')
    }
  } finally {
    uploading.value = false
  }
}

const handleFusionUpload = async () => {
  uploading.value = true
  successCount.value = 0
  try {
    const mainFile = fusionMainList.value[0]
    const attachmentFile = fusionAttachmentList.value[0]
    const formData = new FormData()
    formData.append('file', mainFile.raw)
    formData.append('attachment_file', attachmentFile.raw)
    formData.append('source_type', getSourceType(mainFile.name))
    if (fusionTitle.value) formData.append('title', fusionTitle.value)
    try {
      await taskApi.upload(formData)
      successCount.value = 1
      ElMessage.success('融合任务创建成功')
      visible.value = false
      emit('success')
    } catch (error) {
      console.error('融合任务创建失败', error)
      ElMessage.error('融合任务创建失败')
    }
  } finally {
    uploading.value = false
  }
}

const handleTextSubmit = async () => {
  uploading.value = true
  successCount.value = 0
  try {
    const formData = new FormData()
    formData.append('title', textForm.title)
    formData.append('content', textForm.content)
    await taskApi.createText(formData)
    ElMessage.success('任务创建成功')
    visible.value = false
    emit('success')
  } finally {
    uploading.value = false
  }
}
</script>

<style scoped>
.upload-block { width: 100%; }
.tip { font-size: 12px; color: #999; margin-top: 5px; }
.file-stats { margin-top: 10px; font-size: 13px; color: #606266; font-weight: bold; }
.fusion-wrapper { padding: 0 10px; }
.upload-inline { display: inline-flex; align-items: center; }
.fusion-file-name { margin-top: 6px; font-size: 12px; color: #606266; }
.dialog-footer { display: flex; justify-content: flex-end; }
</style>