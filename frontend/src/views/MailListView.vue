<template>
  <div class="mail-list-page">
    <div class="page-header">
      <h1 class="page-title">{{ pageTitle }}</h1>
      <div class="header-actions">
        <el-button v-if="selectedEmailId !== 'all'" type="primary" @click="openCompose">写邮件</el-button>
        <el-button @click="refreshAll" :loading="loading">刷新</el-button>
      </div>
    </div>

    <div class="mail-layout">
      <el-card class="mail-panel accounts-panel">
        <template #header>
          <div class="panel-title">邮箱账户</div>
        </template>
        <el-scrollbar height="calc(100vh - 220px)">
          <el-menu
            :default-active="selectedEmailId ? String(selectedEmailId) : ''"
            class="mail-menu"
            @select="handleSelectEmail"
          >
            <el-menu-item index="all">
              <div class="email-item">
                <div class="email-address">
                  <template v-if="filterMode === 'sent'">
                    <span>总账户（全部邮箱）</span>
                  </template>
                  <el-badge v-else :value="totalUnread" :hidden="!totalUnread" :max="999">
                    <span>总账户（全部邮箱）</span>
                  </el-badge>
                </div>
              </div>
            </el-menu-item>
            <el-menu-item v-for="email in pagedEmails" :key="email.id" :index="String(email.id)">
              <div class="email-item">
                <div class="email-address">
                  <template v-if="filterMode === 'sent'">
                    <span>{{ email.email || '(未获取邮箱)' }}</span>
                  </template>
                  <el-badge v-else :value="email.unread_count" :hidden="!email.unread_count" :max="99">
                    <span>{{ email.email || '(未获取邮箱)' }}</span>
                  </el-badge>
                </div>
              </div>
            </el-menu-item>
          </el-menu>
        </el-scrollbar>
        <div class="accounts-pagination">
          <el-pagination
            v-model:current-page="accountCurrentPage"
            v-model:page-size="accountPageSize"
            :total="emails.length"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, next"
            size="small"
            @current-change="handleAccountPageChange"
            @size-change="handleAccountPageSizeChange"
          />
        </div>
      </el-card>

      <el-card class="mail-panel records-panel">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">邮件记录 {{ selectedEmailName }}</span>
            <div class="detail-actions">
              <el-button v-if="selectedEmailId !== 'all'" type="danger" size="small" :disabled="!selectedMailIds.length" @click="batchDeleteMails">
                批量删除 ({{ selectedMailIds.length }})
              </el-button>
              <el-button type="warning" size="small" :disabled="!selectedEmailId || selectedEmailId === 'all'" @click="recheckAll">重新全量拉取</el-button>
            </div>
          </div>
        </template>

        <el-table
          :data="sortedMailRecords"
          v-loading="loadingMails"
          class="records-table"
          height="calc(100vh - 250px)"
          row-key="id"
          @row-click="selectMail"
          @selection-change="handleSelectionChange"
          @sort-change="handleSortChange"
        >
          <el-table-column type="selection" width="52" />
          <el-table-column label="主题" min-width="260" sortable="custom" prop="subject">
            <template #default="{ row }">
              <div class="subject-cell">
                <span v-if="isUnread(row)" class="unread-dot"></span>
                <span :class="{ 'unread-text': isUnread(row) }">{{ row.subject }}</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="sender" label="发件人" min-width="180" show-overflow-tooltip sortable="custom" />
          <el-table-column label="收件人" prop="recipient" min-width="220" show-overflow-tooltip sortable="custom">
            <template #default="{ row }">
              <span>{{ getMailRecipient(row) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="folder" label="文件夹" width="110" sortable="custom" />
          <el-table-column label="时间" width="170" sortable="custom" prop="received_time">
            <template #default="{ row }">{{ formatDate(row.received_time) }}</template>
          </el-table-column>
        </el-table>
        <div class="records-pagination">
          <el-pagination
            v-model:current-page="currentPage"
            v-model:page-size="pageSize"
            :total="totalRecords"
            :page-sizes="[10, 20, 50, 100]"
            layout="total, sizes, prev, pager, next, jumper"
            @current-change="handlePageChange"
            @size-change="handlePageSizeChange"
          />
        </div>
      </el-card>
    </div>

    <el-dialog v-model="detailVisible" title="邮件详情" width="70%" destroy-on-close>
      <EmailContentViewer
        v-if="activeMail"
        :mail="activeMail"
        :attachments="activeAttachments"
        :loading-attachments="loadingAttachments"
      />
      <template #footer>
        <div class="drawer-footer">
          <el-button v-if="filterMode === 'sent'" :disabled="!activeMail" @click="openEditFromSent">编辑</el-button>
          <template v-else>
            <el-button :disabled="!activeMail" @click="openReply('reply')">回复</el-button>
            <el-button :disabled="!activeMail" @click="openReply('replyAll')">回复全部</el-button>
          </template>
          <el-button type="danger" :disabled="!activeMail" @click="deleteCurrentMail">删除</el-button>
          <el-button @click="detailVisible = false">关闭</el-button>
        </div>
      </template>
    </el-dialog>

    <el-drawer v-model="composeVisible" :title="composeTitle" size="48%" destroy-on-close>
      <el-form :model="composeForm" label-width="72px">
        <el-form-item v-if="composeMode === 'reply'" label="方式">
          <el-radio-group v-model="replyAction">
            <el-radio-button label="reply">回复</el-radio-button>
            <el-radio-button label="replyAll">回复全部</el-radio-button>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="收件人">
          <el-input v-model="composeForm.to" placeholder="多个邮箱用英文逗号分隔；回复可留空使用系统默认" />
        </el-form-item>
        <el-form-item label="抄送">
          <el-input v-model="composeForm.cc" placeholder="多个邮箱用英文逗号分隔" />
        </el-form-item>
        <el-form-item label="密送">
          <el-input v-model="composeForm.bcc" placeholder="多个邮箱用英文逗号分隔" />
        </el-form-item>
        <el-form-item label="主题">
          <el-input v-model="composeForm.subject" />
        </el-form-item>
        <el-form-item label="内容">
          <div class="editor-wrap">
            <Toolbar
              :editor="wangEditorRef"
              :defaultConfig="toolbarConfig"
              mode="default"
              class="editor-toolbar"
            />
            <Editor
              v-model="composeForm.content"
              :defaultConfig="editorConfig"
              mode="default"
              class="compose-editor"
              :style="{ height: `${editorHeight}px` }"
              @onCreated="handleEditorCreated"
            />
            <div class="editor-resize-handle" @mousedown.prevent="startResizeEditor">
              <span>拖拽调整编辑区高度</span>
            </div>
            <input ref="attachmentInputRef" type="file" multiple class="hidden-input" @change="handleAttachmentChange" />
          </div>
        </el-form-item>
        <el-form-item v-if="composeMode === 'reply' && (loadingAttachments || activeAttachments.length)" label="原附件">
          <div class="attachment-list">
            <div v-if="loadingAttachments" class="attachment-item">
              <span>附件加载中...</span>
            </div>
            <div v-for="attachment in activeAttachments" :key="`origin-${attachment.id}`" class="attachment-item">
              <span>{{ attachment.filename }} ({{ formatFileSize(attachment.size) }})</span>
              <div class="attachment-actions">
                <el-link
                  type="primary"
                  :underline="false"
                  :href="`/api/attachments/${attachment.id}/download`"
                  target="_blank"
                >
                  下载链接
                </el-link>
                <el-button link type="primary" @click="downloadServerAttachment(attachment)">下载</el-button>
              </div>
            </div>
          </div>
        </el-form-item>
        <el-form-item v-if="composeAttachments.length" label="附件">
          <div class="attachment-list">
            <div v-for="(item, index) in composeAttachments" :key="`${item.name}-${index}`" class="attachment-item">
              <span>{{ item.name }} ({{ formatFileSize(item.size) }})</span>
              <div class="attachment-actions">
                <el-button link type="primary" @click="downloadComposeAttachment(item)">下载</el-button>
                <el-button link type="danger" @click="removeAttachment(index)">移除</el-button>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <div class="drawer-footer">
          <el-button @click="composeVisible = false">取消</el-button>
          <el-button type="primary" :loading="composeLoading" @click="sendCompose">发送</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, shallowRef, computed, onMounted, onUnmounted, watch } from 'vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRoute } from 'vue-router'
import '@wangeditor/editor/dist/css/style.css'
import { Editor, Toolbar } from '@wangeditor/editor-for-vue'
import { Boot } from '@wangeditor/editor'
import api from '@/services/api'
import { useEmailsStore } from '@/store/emails'
import websocket from '@/services/websocket'
import EmailContentViewer from '@/components/EmailContentViewer.vue'
import logger from '@/utils/debugLogger'

const props = defineProps({
  filterMode: {
    type: String,
    default: 'inbox_junk'
  }
})

const emailsStore = useEmailsStore()
const route = useRoute()
const loading = ref(false)
const loadingMails = ref(false)
const loadingAttachments = ref(false)
const selectedEmailId = ref('all')
const activeMail = ref(null)
const activeAttachments = ref([])
const detailVisible = ref(false)
const mailRecordsData = ref([])
const selectedMailIds = ref([])
const accountCurrentPage = ref(1)
const accountPageSize = ref(20)
const currentPage = ref(1)
const pageSize = ref(20)
const totalRecords = ref(0)

const composeVisible = ref(false)
const composeLoading = ref(false)
const composeMode = ref('new')
const replyAction = ref('reply')
const wangEditorRef = shallowRef(null)
const attachmentInputRef = ref(null)
const composeAttachments = ref([])
const editorHeight = ref(360)
const composeForm = ref({
  to: '',
  cc: '',
  bcc: '',
  subject: '',
  content: ''
})

const sortState = ref({ prop: 'received_time', order: 'descending' })
const allMailRecords = ref([])
const resizeState = {
  active: false,
  startY: 0,
  startHeight: 360
}

const emails = computed(() => emailsStore.emails || [])
const pagedEmails = computed(() => {
  const start = (accountCurrentPage.value - 1) * accountPageSize.value
  const end = start + accountPageSize.value
  return emails.value.slice(start, end)
})
const mailRecords = computed(() => mailRecordsData.value || [])
const totalUnread = computed(() => emails.value.reduce((sum, item) => sum + Number(item.unread_count || 0), 0))
const selectedEmailName = computed(() => {
  if (selectedEmailId.value === 'all') return '（全部邮箱）'
  const found = emails.value.find(x => Number(x.id) === Number(selectedEmailId.value))
  return found ? `（${found.email}）` : ''
})
const pageTitle = computed(() => (props.filterMode === 'sent' ? '已发送邮件' : '邮件列表'))

const composeTitle = computed(() => {
  if (composeMode.value === 'edit') return '编辑邮件'
  if (composeMode.value !== 'reply') return '写邮件'
  return replyAction.value === 'replyAll' ? '回复全部' : '回复邮件'
})

const sortedMailRecords = computed(() => {
  const records = Array.isArray(allMailRecords.value) ? [...allMailRecords.value] : []
  const { prop, order } = sortState.value || {}
  if (prop && order) {
    const direction = order === 'ascending' ? 1 : -1
    const getValue = (row) => {
      if (prop === 'received_time') return row?.received_time ? new Date(row.received_time).getTime() : 0
      if (prop === 'recipient') return getMailRecipient(row).toLowerCase()
      return (row?.[prop] ?? '').toString().toLowerCase()
    }
    records.sort((a, b) => {
      const va = getValue(a)
      const vb = getValue(b)
      if (va < vb) return -1 * direction
      if (va > vb) return 1 * direction
      return 0
    })
  }
  const start = (currentPage.value - 1) * pageSize.value
  const end = start + pageSize.value
  return records.slice(start, end)
})

const formatDate = (dateString) => {
  if (!dateString) return '-'
  return dayjs(dateString).format('YYYY-MM-DD HH:mm:ss')
}

const isUnread = (row) => {
  if (row == null) return false
  if (typeof row.is_read !== 'undefined' && row.is_read !== null) {
    return Number(row.is_read) === 0
  }
  if (typeof row.isRead !== 'undefined') {
    return row.isRead === false
  }
  return false
}

const isSentFolder = (folder) => {
  const value = String(folder || '').trim().toLowerCase()
  return value.includes('sent') || value.includes('已发送')
}

const isInboxOrJunkFolder = (folder) => {
  const value = String(folder || '').trim().toLowerCase()
  return value.includes('inbox') || value.includes('收件箱') || value.includes('junk') || value.includes('spam') || value.includes('垃圾')
}

const parseRecipients = (text) => {
  if (!text || !text.trim()) return []
  return text.split(',').map(x => x.trim()).filter(Boolean)
}

const formatFileSize = (size) => {
  const n = Number(size || 0)
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  return `${(n / (1024 * 1024)).toFixed(1)} MB`
}

const fileToBase64 = (file) => new Promise((resolve, reject) => {
  const reader = new FileReader()
  reader.onload = () => {
    const result = String(reader.result || '')
    const content_base64 = result.includes(',') ? result.split(',', 2)[1] : result
    resolve(content_base64)
  }
  reader.onerror = reject
  reader.readAsDataURL(file)
})

const inferExtensionFromMime = (mime = '') => {
  const normalized = String(mime || '').toLowerCase()
  if (normalized === 'image/jpeg') return 'jpg'
  if (normalized === 'image/png') return 'png'
  if (normalized === 'image/gif') return 'gif'
  if (normalized === 'image/webp') return 'webp'
  if (normalized === 'image/svg+xml') return 'svg'
  return 'bin'
}

const buildCidInlineImages = (html = '') => {
  const source = String(html || '')
  if (!source.trim() || typeof DOMParser === 'undefined') {
    return { html: source, inlineAttachments: [] }
  }

  const parser = new DOMParser()
  const doc = parser.parseFromString(source, 'text/html')
  const images = Array.from(doc.querySelectorAll('img[src^="data:image/"]'))
  const inlineAttachments = []

  images.forEach((img, index) => {
    const src = String(img.getAttribute('src') || '')
    const matched = src.match(/^data:([^;]+);base64,(.+)$/i)
    if (!matched) return

    const mime = matched[1] || 'application/octet-stream'
    const contentBase64 = matched[2] || ''
    if (!contentBase64) return

    const ext = inferExtensionFromMime(mime)
    const cid = `fm-inline-${Date.now()}-${index}@firemail.local`
    const altName = String(img.getAttribute('alt') || '').trim()
    const name = altName || `inline-${index + 1}.${ext}`

    img.setAttribute('src', `cid:${cid}`)
    inlineAttachments.push({
      name,
      content_type: mime,
      content_base64: contentBase64,
      is_inline: true,
      content_id: cid
    })
  })

  return {
    html: doc.body.innerHTML || source,
    inlineAttachments
  }
}

const triggerAttachmentPick = () => attachmentInputRef.value?.click()

const ATTACHMENT_MENU_KEY = 'fmUploadAttachment'
const globalObj = typeof window !== 'undefined' ? window : globalThis
if (!globalObj.__fmUploadAttachmentMenuRegistered) {
  class UploadAttachmentMenu {
    constructor() {
      this.title = '上传附件'
      this.iconSvg = '<svg viewBox="0 0 1024 1024"><path d="M746.624 173.376c-93.632-93.632-245.376-93.632-339.008 0L184.576 396.416c-72.704 72.704-72.704 190.528 0 263.232 72.704 72.704 190.528 72.704 263.232 0l198.4-198.4a124.16 124.16 0 0 0 0-175.616 124.16 124.16 0 0 0-175.616 0L285.824 470.4a46.933 46.933 0 1 0 66.368 66.368l184.768-184.768a30.293 30.293 0 0 1 42.88 0 30.293 30.293 0 0 1 0 42.88l-198.4 198.4c-36.096 36.096-94.72 36.096-130.816 0-36.096-36.096-36.096-94.72 0-130.816l223.04-223.04c56.96-56.96 149.248-56.96 206.208 0 56.96 56.96 56.96 149.248 0 206.208L468.16 657.344a218.035 218.035 0 0 1-308.224 0 218.035 218.035 0 0 1 0-308.224l223.04-223.04a46.933 46.933 0 0 0-66.368-66.368L93.568 282.752a311.893 311.893 0 0 0 0 441.088 311.893 311.893 0 0 0 441.088 0l211.712-211.712c93.632-93.632 93.632-245.376 0-338.752z"></path></svg>'
      this.tag = 'button'
    }
    getValue() { return '' }
    isActive() { return false }
    isDisabled() { return false }
    exec() { triggerAttachmentPick() }
  }
  Boot.registerMenu({
    key: ATTACHMENT_MENU_KEY,
    factory() {
      return new UploadAttachmentMenu()
    }
  })
  globalObj.__fmUploadAttachmentMenuRegistered = true
}

const toolbarConfig = {
  excludeKeys: ['group-video'],
  insertKeys: {
    index: 24,
    keys: [ATTACHMENT_MENU_KEY]
  }
}

const editorConfig = {
  placeholder: '请输入邮件正文...',
  MENU_CONF: {
    uploadImage: {
      customUpload: async (file, insertFn) => {
        try {
          if (!file || !String(file.type || '').startsWith('image/')) {
            ElMessage.warning('仅支持上传图片文件')
            return
          }
          const contentBase64 = await fileToBase64(file)
          const dataUrl = `data:${file.type};base64,${contentBase64}`
          insertFn(dataUrl, file.name || 'image')
          if (wangEditorRef.value) {
            composeForm.value.content = wangEditorRef.value.getHtml()
          }
        } catch (_) {
          ElMessage.error('图片上传失败')
        }
      }
    }
  }
}

const handleEditorCreated = (editor) => {
  wangEditorRef.value = editor
}

const setEditorContent = (html = '') => {
  composeForm.value.content = html
  if (wangEditorRef.value) {
    wangEditorRef.value.setHtml(html || '<p><br></p>')
  }
}

const handleAttachmentChange = async (event) => {
  const files = Array.from(event.target.files || [])
  for (const file of files) {
    const content_base64 = await fileToBase64(file)
    composeAttachments.value.push({
      name: file.name,
      size: file.size,
      content_type: file.type || 'application/octet-stream',
      content_base64
    })
  }
  event.target.value = ''
}

const removeAttachment = (index) => {
  composeAttachments.value.splice(index, 1)
}

const downloadServerAttachment = (attachment) => {
  if (!attachment?.id) return
  const link = document.createElement('a')
  link.href = `/api/attachments/${attachment.id}/download`
  link.setAttribute('download', attachment.filename || 'attachment.bin')
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
}

const downloadComposeAttachment = (item) => {
  if (!item?.content_base64) return
  try {
    const byteCharacters = atob(item.content_base64)
    const byteNumbers = new Array(byteCharacters.length)
    for (let i = 0; i < byteCharacters.length; i += 1) {
      byteNumbers[i] = byteCharacters.charCodeAt(i)
    }
    const byteArray = new Uint8Array(byteNumbers)
    const blob = new Blob([byteArray], { type: item.content_type || 'application/octet-stream' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.setAttribute('download', item.name || 'attachment.bin')
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    URL.revokeObjectURL(url)
  } catch (_) {
    ElMessage.error('附件下载失败')
  }
}

const normalizeSenderToEmail = (sender) => {
  if (!sender) return ''
  if (sender.includes('<') && sender.includes('>')) {
    return sender.split('<', 1)[1].split('>', 1)[0].trim()
  }
  return sender.trim()
}

const getMailRecipient = (row) => {
  if (!row) return '(未知收件人)'

  const fromContent = (() => {
    const content = row.content
    if (!content || typeof content !== 'object') return null
    return content.to ?? content.recipient ?? content.recipients ?? content.receiver ?? content.receivers ?? null
  })()

  const raw = row.recipient
    ?? row.to
    ?? row.recipients
    ?? row.receiver
    ?? row.receivers
    ?? fromContent

  if (Array.isArray(raw)) {
    const values = raw.map(v => String(v || '').trim()).filter(Boolean)
    return values.length ? values.join(', ') : '(未知收件人)'
  }

  if (raw && typeof raw === 'object') {
    const values = Object.values(raw).map(v => String(v || '').trim()).filter(Boolean)
    if (values.length) return values.join(', ')
  }

  const text = String(raw || '').trim()
  if (text) return text

  if (props.filterMode === 'sent') {
    return '(未知收件人)'
  }
  const accountEmail = emails.value.find(item => Number(item.id) === Number(row.email_id))?.email
  return accountEmail || '(未知收件人)'
}

const normalizeRecipientInputText = (raw) => {
  if (Array.isArray(raw)) return raw.map(v => String(v || '').trim()).filter(Boolean).join(', ')
  if (raw && typeof raw === 'object') {
    return Object.values(raw).map(v => String(v || '').trim()).filter(Boolean).join(', ')
  }
  return String(raw || '').trim()
}

const loadEmails = async () => {
  const startedAt = Date.now()
  logger.debug('mail-list-view', 'loadEmails:start', {
    route: route.fullPath,
    selectedEmailId: selectedEmailId.value
  })
  loading.value = true
  try {
    await emailsStore.fetchEmails()
    const maxAccountPages = Math.max(1, Math.ceil((emails.value.length || 0) / accountPageSize.value))
    if (accountCurrentPage.value > maxAccountPages) {
      accountCurrentPage.value = maxAccountPages
    }
    try {
      await loadMailRecords()
    } catch (error) {
      console.error('加载邮件记录失败:', error)
      ElMessage.error('邮件记录加载失败，请稍后重试')
    }
  } catch (error) {
    logger.error('mail-list-view', 'loadEmails:error', { message: error?.message })
    console.error('加载邮箱列表失败:', error)
    ElMessage.error('邮箱列表加载失败，请稍后重试')
  } finally {
    loading.value = false
    logger.debug('mail-list-view', 'loadEmails:end', {
      durationMs: Date.now() - startedAt,
      emailCount: emails.value.length
    })
  }
}

const loadMailRecords = async () => {
  const startedAt = Date.now()
  logger.debug('mail-list-view', 'loadMailRecords:start', {
    selectedEmailId: selectedEmailId.value,
    route: route.fullPath
  })
  loadingMails.value = true
  try {
    const fetchByWs = async (emailId) => {
      const response = await websocket.requestResponse({
        sendType: 'get_mail_records',
        payload: { email_id: emailId },
        responseType: 'mail_records',
        match: (msg) => Number(msg?.email_id) === Number(emailId),
        timeoutMs: 15000
      })
      return Array.isArray(response?.data) ? response.data : []
    }

    let records = []
    if (selectedEmailId.value === 'all') {
      const ids = (emails.value || []).map(item => Number(item.id)).filter(Boolean)
      if (ids.length > 0) {
        const all = []
        for (const id of ids) {
          const one = await fetchByWs(id).catch(() => [])
          all.push(...one)
        }
        records = all
      }
    } else {
      records = await fetchByWs(selectedEmailId.value)
    }

    if (props.filterMode === 'sent') {
      records = records.filter((item) => isSentFolder(item?.folder))
    } else if (props.filterMode === 'inbox_junk') {
      records = records.filter((item) => isInboxOrJunkFolder(item?.folder))
    }

    allMailRecords.value = records
    mailRecordsData.value = records
    totalRecords.value = records.length

    const totalPages = Math.max(1, Math.ceil(totalRecords.value / pageSize.value))
    if (currentPage.value > totalPages) {
      currentPage.value = totalPages
    }

    if (!records.length) {
      activeMail.value = null
      activeAttachments.value = []
      detailVisible.value = false
    }
  } catch (error) {
    logger.error('mail-list-view', 'loadMailRecords:error', { message: error?.message })
    try {
      const payload = await api.emails.getRecordsPage({
        emailId: selectedEmailId.value === 'all' ? null : selectedEmailId.value,
        page: currentPage.value,
        pageSize: pageSize.value
      })
      const fallback = Array.isArray(payload?.records) ? payload.records : []
      allMailRecords.value = fallback
      mailRecordsData.value = fallback
      totalRecords.value = Number(payload?.pagination?.total || fallback.length)
    } catch (fallbackError) {
      allMailRecords.value = []
      mailRecordsData.value = []
      totalRecords.value = 0
      throw fallbackError
    }
  } finally {
    loadingMails.value = false
    logger.debug('mail-list-view', 'loadMailRecords:end', {
      durationMs: Date.now() - startedAt,
      totalRecords: totalRecords.value,
      currentPage: currentPage.value
    })
  }
}

const handleSelectEmail = async (id) => {
  logger.debug('mail-list-view', 'handleSelectEmail', { id })
  selectedEmailId.value = id === 'all' ? 'all' : Number(id)
  selectedMailIds.value = []
  currentPage.value = 1
  await loadMailRecords()
}

const handleAccountPageChange = (page) => {
  accountCurrentPage.value = page
}

const handleAccountPageSizeChange = (size) => {
  accountPageSize.value = size
  accountCurrentPage.value = 1
}

const handlePageChange = (page) => {
  currentPage.value = page
  selectedMailIds.value = []
}

const handlePageSizeChange = (size) => {
  pageSize.value = size
  currentPage.value = 1
  selectedMailIds.value = []
}

const loadAttachments = async (mailId) => {
  loadingAttachments.value = true
  try {
    const res = await api.emails.getAttachments(mailId)
    activeAttachments.value = Array.isArray(res) ? res : []
  } catch (_) {
    activeAttachments.value = []
  } finally {
    loadingAttachments.value = false
  }
}

const selectMail = async (row) => {
  activeMail.value = row
  await loadAttachments(row.id)
  detailVisible.value = true
  if (row && row.id && isUnread(row)) {
    try {
      await api.emails.markRead(row.id)
      row.is_read = 1
      const emailInfo = emails.value.find(x => Number(x.id) === Number(row.email_id))
      if (emailInfo && Number(emailInfo.unread_count || 0) > 0) {
        emailInfo.unread_count = Number(emailInfo.unread_count) - 1
      }
    } catch (_) {
      ElMessage.error('标记已读失败')
    }
  }
}

const handleSelectionChange = (rows) => {
  selectedMailIds.value = (rows || []).map(row => row.id)
}

const openCompose = () => {
  if (!selectedEmailId.value || selectedEmailId.value === 'all') {
    ElMessage.warning('请先选择具体邮箱账号再写邮件')
    return
  }
  composeMode.value = 'new'
  replyAction.value = 'reply'
  composeForm.value = { to: '', cc: '', bcc: '', subject: '', content: '' }
  composeAttachments.value = []
  editorHeight.value = 360
  composeVisible.value = true
  setEditorContent('')
}

const openReply = (action = 'reply') => {
  if (!activeMail.value) return
  composeMode.value = 'reply'
  replyAction.value = action

  const to = normalizeSenderToEmail(activeMail.value.sender)
  const currentSubject = activeMail.value.subject || ''
  const subject = currentSubject.toLowerCase().startsWith('re:') ? currentSubject : `Re: ${currentSubject}`
  composeForm.value = { to, cc: '', bcc: '', subject, content: '' }
  composeAttachments.value = []
  editorHeight.value = 360
  composeVisible.value = true
  setEditorContent('')
  if (activeMail.value.has_attachments && !activeAttachments.value.length) {
    loadAttachments(activeMail.value.id)
  }
}

const openEditFromSent = () => {
  if (!activeMail.value) return
  composeMode.value = 'edit'
  replyAction.value = 'reply'

  const rawTo = activeMail.value.recipient ?? activeMail.value.to ?? activeMail.value.recipients
  const rawCc = activeMail.value.cc ?? activeMail.value.ccs ?? activeMail.value.carbon_copy
  const rawBcc = activeMail.value.bcc ?? activeMail.value.bccs ?? activeMail.value.blind_carbon_copy
  const content = String(activeMail.value.content || '')

  selectedEmailId.value = Number(activeMail.value.email_id || selectedEmailId.value)
  composeForm.value = {
    to: normalizeRecipientInputText(rawTo),
    cc: normalizeRecipientInputText(rawCc),
    bcc: normalizeRecipientInputText(rawBcc),
    subject: String(activeMail.value.subject || ''),
    content
  }
  composeAttachments.value = []
  editorHeight.value = 360
  composeVisible.value = true
  setEditorContent(content)
}

const sendCompose = async () => {
  if (composeMode.value !== 'reply' && (!selectedEmailId.value || selectedEmailId.value === 'all')) {
    ElMessage.warning('请先选择具体邮箱账号再发信')
    return
  }
  composeLoading.value = true
  try {
    if (wangEditorRef.value) {
      composeForm.value.content = wangEditorRef.value.getHtml()
    }
    const { html: finalContent, inlineAttachments } = buildCidInlineImages(composeForm.value.content)
    const finalAttachments = [...composeAttachments.value, ...inlineAttachments]
    if (composeMode.value === 'reply' && activeMail.value) {
      await api.emails.replyMail(activeMail.value.id, {
        action: replyAction.value,
        to: parseRecipients(composeForm.value.to),
        cc: parseRecipients(composeForm.value.cc),
        bcc: parseRecipients(composeForm.value.bcc),
        subject: composeForm.value.subject,
        content: finalContent,
        attachments: finalAttachments
      })
    } else {
      const to = parseRecipients(composeForm.value.to)
      if (!to.length) {
        ElMessage.warning('收件人不能为空')
        return
      }
      await api.emails.sendMail(selectedEmailId.value, {
        to,
        cc: parseRecipients(composeForm.value.cc),
        bcc: parseRecipients(composeForm.value.bcc),
        subject: composeForm.value.subject,
        content: finalContent,
        attachments: finalAttachments
      })
    }
    ElMessage.success('发送成功')
    composeVisible.value = false
  } catch (e) {
    ElMessage.error(e?.response?.data?.error || '发送失败')
  } finally {
    composeLoading.value = false
  }
}

const deleteCurrentMail = async () => {
  if (!activeMail.value) return
  try {
    await ElMessageBox.confirm('确认删除这封邮件？', '删除确认', { type: 'warning' })
    await api.emails.deleteMail(activeMail.value.id)
    ElMessage.success('删除成功')
    detailVisible.value = false
    await loadMailRecords()
    await loadEmails()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.error || '删除失败')
    }
  }
}

const batchDeleteMails = async () => {
  if (!selectedMailIds.value.length) return
  try {
    await ElMessageBox.confirm(
      `确认批量删除已选中的 ${selectedMailIds.value.length} 封邮件？`,
      '批量删除确认',
      { type: 'warning' }
    )
    let successCount = 0
    let failedCount = 0
    try {
      const res = await api.emails.batchDeleteMail(selectedMailIds.value)
      successCount = Array.isArray(res?.success_ids) ? res.success_ids.length : 0
      failedCount = Array.isArray(res?.failed) ? res.failed.length : 0
    } catch (apiError) {
      // 兜底：后端不支持批量接口时，前端逐条删除
      const settled = await Promise.allSettled(
        selectedMailIds.value.map((id) => api.emails.deleteMail(id))
      )
      successCount = settled.filter(item => item.status === 'fulfilled').length
      failedCount = settled.length - successCount
      if (failedCount > 0) {
        console.error('批量接口失败，逐条删除仍有失败:', apiError)
      }
    }

    if (successCount === 0 && failedCount > 0) {
      ElMessage.error('批量删除失败，请查看后端日志')
      return
    }
    if (failedCount > 0) ElMessage.warning(`已删除 ${successCount} 封，失败 ${failedCount} 封`)
    else ElMessage.success(`已删除 ${successCount} 封邮件`)

    if (activeMail.value && selectedMailIds.value.includes(activeMail.value.id)) {
      detailVisible.value = false
      activeMail.value = null
      activeAttachments.value = []
    }
    selectedMailIds.value = []
    await loadMailRecords()
    await loadEmails()
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e?.response?.data?.error || e?.message || '批量删除失败')
    }
  }
}

const recheckAll = async () => {
  if (!selectedEmailId.value) return
  try {
    await emailsStore.recheckEmailAll(selectedEmailId.value)
    ElMessage.success('已触发重新全量拉取')
  } catch (e) {
    ElMessage.error(e.message || '重新全量拉取失败')
  }
}

const handleSortChange = ({ prop, order }) => {
  sortState.value = { prop, order }
}

const refreshAll = async () => {
  await loadEmails()
}

const onResizeEditorMove = (event) => {
  if (!resizeState.active) return
  const delta = event.clientY - resizeState.startY
  const next = resizeState.startHeight + delta
  editorHeight.value = Math.max(220, Math.min(720, next))
}

const stopResizeEditor = () => {
  if (!resizeState.active) return
  resizeState.active = false
  document.body.style.userSelect = ''
  window.removeEventListener('mousemove', onResizeEditorMove)
  window.removeEventListener('mouseup', stopResizeEditor)
}

const startResizeEditor = (event) => {
  resizeState.active = true
  resizeState.startY = event.clientY
  resizeState.startHeight = editorHeight.value
  document.body.style.userSelect = 'none'
  window.addEventListener('mousemove', onResizeEditorMove)
  window.addEventListener('mouseup', stopResizeEditor)
}

onMounted(async () => {
  logger.debug('mail-list-view', 'mounted', { route: route.fullPath })
  await loadEmails()
})

onUnmounted(() => {
  stopResizeEditor()
  if (wangEditorRef.value) {
    wangEditorRef.value.destroy()
    wangEditorRef.value = null
  }
  logger.debug('mail-list-view', 'unmounted', { route: route.fullPath })
})

watch(
  () => route.fullPath,
  (newPath, oldPath) => {
    logger.debug('mail-list-view', 'route:changed', { from: oldPath, to: newPath })
  }
)
</script>

<style scoped>
.mail-list-page {
  min-height: 100vh;
  background-color: var(--bg-color);
  padding: 20px;
}

.page-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  color: var(--primary-color);
  font-size: 1.4rem;
}

.header-actions {
  display: flex;
  gap: 8px;
}

.mail-layout {
  display: grid;
  grid-template-columns: 300px minmax(860px, 1fr);
  gap: 12px;
}

.mail-panel {
  border-radius: var(--border-radius);
}

.panel-title {
  font-weight: 600;
}

.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.mail-menu {
  border-right: none;
}

.accounts-pagination {
  display: flex;
  justify-content: center;
  padding: 10px 0 2px;
}

.mail-menu :deep(.el-menu-item) {
  height: auto;
  line-height: 1.2;
  padding: 12px 16px;
  white-space: normal;
}

.mail-menu :deep(.el-menu-item.is-active) {
  background: rgba(64, 158, 255, 0.12);
  border-radius: 8px;
  margin: 4px 8px;
}

.email-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.email-address {
  font-weight: 600;
  word-break: break-all;
}

.records-table {
  width: 100%;
}

.records-pagination {
  display: flex;
  justify-content: flex-end;
  padding-top: 12px;
}

.subject-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.unread-dot {
  width: 8px;
  height: 8px;
  border-radius: 999px;
  background: #e3483f;
  flex: 0 0 auto;
}

.unread-text {
  font-weight: 700;
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.editor-wrap {
  width: 100%;
  border: 1px solid var(--border-color, #dcdfe6);
  border-radius: 6px;
}

.editor-toolbar {
  border-bottom: 1px solid var(--border-color, #dcdfe6);
}

.compose-editor {
  border: 0;
}

.compose-editor :deep(.w-e-text-container) {
  height: calc(100% - 1px) !important;
}

.compose-editor :deep(.w-e-scroll) {
  line-height: 1.6;
}

.editor-resize-handle {
  display: flex;
  justify-content: center;
  align-items: center;
  height: 24px;
  border-top: 1px dashed #dcdfe6;
  background: #fafafa;
  color: #909399;
  font-size: 12px;
  cursor: ns-resize;
}

.hidden-input {
  display: none;
}

.attachment-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
}

.attachment-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: #f5f7fa;
  padding: 6px 10px;
  border-radius: 6px;
}

.attachment-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

@media (max-width: 1400px) {
  .mail-layout {
    grid-template-columns: 260px 1fr;
  }
}

@media (max-width: 960px) {
  .mail-layout {
    grid-template-columns: 1fr;
  }
}
</style>

