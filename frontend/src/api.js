import axios from 'axios'
import { ElMessage } from 'element-plus'

// 创建 axios 实例
const api = axios.create({
  // 开发环境通过 vite proxy 转发，生产环境直接访问当前域名
  baseURL: import.meta.env.DEV ? '' : '',
  timeout: 10000
})

// 响应拦截器
api.interceptors.response.use(
  response => response,
  error => {
    const msg = error.response?.data?.detail || error.message
    ElMessage.error(`请求失败: ${msg}`)
    return Promise.reject(error)
  }
)

export const taskApi = {
  list: () => api.get('/tasks/'),
  get: (id) => api.get(`/tasks/${id}`),
  upload: (formData) => api.post('/tasks/upload', formData),
  createText: (formData) => api.post('/tasks/create_text', formData),
  updateContent: (id, data) => api.patch(`/tasks/${id}`, data),
  delete: (id) => api.delete(`/tasks/${id}`),
  generateNote: (id, templateId) => api.post(`/tasks/${id}/generate_note`, { template_id: templateId }),
  exportObsidian: (id) => api.post(`/tasks/${id}/export_obsidian`)
}

export const settingsApi = {
  getConfig: () => api.get('/settings/config'),
  updateConfig: (data) => api.post('/settings/config', data),
  getTemplates: () => api.get('/settings/templates'),
  addTemplate: (data) => api.post('/settings/templates', data),
  updateTemplate: (id, data) => api.patch(`/settings/templates/${id}`, data), // [新增]
  deleteTemplate: (id) => api.delete(`/settings/templates/${id}`)
}