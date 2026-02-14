<template>
  <div class="mail-list-page">
    <div class="page-header">
      <h1 class="page-title">邮件列表</h1>
      <div class="header-actions">
        <el-button type="primary" @click="openCompose">写邮件</el-button>
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
                  <el-badge :value="totalUnread" :hidden="!totalUnread" :max="999">
                    <span>总账户（全部邮箱）</span>
                  </el-badge>
                </div>
                <div class="email-type">all</div>
              </div>
            </el-menu-item>
            <el-menu-item v-for="email in emails" :key="email.id" :index="String(email.id)">
              <div class="email-item">
                <div class="email-address">
                  <el-badge :value="email.unread_count" :hidden="!email.unread_count" :max="99">
                    <span>{{ email.email || '(未获取邮箱)' }}</span>
                  </el-badge>
                </div>
                <div class="email-type">{{ email.mail_type }}</div>
              </div>
            </el-menu-item>
          </el-menu>
        </el-scrollbar>
      </el-card>

      <el-card class="mail-panel records-panel">
        <template #header>
          <div class="panel-head">
            <span class="panel-title">邮件记录 {{ selectedEmailName }}</span>
            <div class="detail-actions">
              <el-button type="danger" size="small" :disabled="!selectedMailIds.length" @click="batchDeleteMails">
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
          <el-table-column prop="folder" label="文件夹" width="110" sortable="custom" />
          <el-table-column label="时间" width="170" sortable="custom" prop="received_time">
            <template #default="{ row }">{{ formatDate(row.received_time) }}</template>
          </el-table-column>
        </el-table>
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
          <el-button :disabled="!activeMail" @click="openReply('reply')">回复</el-button>
          <el-button :disabled="!activeMail" @click="openReply('replyAll')">回复全部</el-button>
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
            <div class="editor-toolbar">
              <el-button size="small" @click="applyEditorCommand('bold')"><b>B</b></el-button>
              <el-button size="small" @click="applyEditorCommand('italic')"><i>I</i></el-button>
              <el-button size="small" @click="applyEditorCommand('underline')"><u>U</u></el-button>
              <el-button size="small" @click="applyEditorCommand('insertUnorderedList')">列表</el-button>
              <el-select v-model="fontSizeValue" size="small" class="font-size-select" @change="onFontSizeChange">
                <el-option label="小" value="2" />
                <el-option label="中" value="3" />
                <el-option label="大" value="5" />
                <el-option label="特大" value="6" />
              </el-select>
              <el-button size="small" @click="triggerInlineImagePick">上传图片</el-button>
              <el-button size="small" @click="triggerAttachmentPick">上传附件</el-button>
            </div>
            <div
              ref="editorRef"
              class="compose-editor"
              contenteditable="true"
              @input="syncEditorToForm"
            />
            <input ref="inlineImageInputRef" type="file" accept="image/*" multiple class="hidden-input" @change="handleInlineImageChange" />
            <input ref="attachmentInputRef" type="file" multiple class="hidden-input" @change="handleAttachmentChange" />
          </div>
        </el-form-item>
        <el-form-item v-if="composeAttachments.length" label="附件">
          <div class="attachment-list">
            <div v-for="(item, index) in composeAttachments" :key="`${item.name}-${index}`" class="attachment-item">
              <span>{{ item.name }} ({{ formatFileSize(item.size) }})</span>
              <el-button link type="danger" @click="removeAttachment(index)">移除</el-button>
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
import { ref, computed, onMounted, nextTick } from 'vue'
import dayjs from 'dayjs'
import { ElMessage, ElMessageBox } from 'element-plus'
import api from '@/services/api'
import { useEmailsStore } from '@/store/emails'
import EmailContentViewer from '@/components/EmailContentViewer.vue'

const emailsStore = useEmailsStore()
const loading = ref(false)
const loadingMails = ref(false)
const loadingAttachments = ref(false)
const selectedEmailId = ref('all')
const activeMail = ref(null)
const activeAttachments = ref([])
const detailVisible = ref(false)
const mailRecordsData = ref([])
const selectedMailIds = ref([])

const composeVisible = ref(false)
const composeLoading = ref(false)
const composeMode = ref('new')
const replyAction = ref('reply')
const editorRef = ref(null)
const attachmentInputRef = ref(null)
const inlineImageInputRef = ref(null)
const composeAttachments = ref([])
const fontSizeValue = ref('3')
const composeForm = ref({
  to: '',
  cc: '',
  bcc: '',
  subject: '',
  content: ''
})

const sortState = ref({ prop: 'received_time', order: 'descending' })

const emails = computed(() => emailsStore.emails || [])
const mailRecords = computed(() => mailRecordsData.value || [])
const totalUnread = computed(() => emails.value.reduce((sum, item) => sum + Number(item.unread_count || 0), 0))
const selectedEmailName = computed(() => {
  if (selectedEmailId.value === 'all') return '（全部邮箱）'
  const found = emails.value.find(x => Number(x.id) === Number(selectedEmailId.value))
  return found ? `（${found.email}）` : ''
})

const composeTitle = computed(() => {
  if (composeMode.value !== 'reply') return '写邮件'
  return replyAction.value === 'replyAll' ? '回复全部' : '回复邮件'
})

const sortedMailRecords = computed(() => {
  const records = Array.isArray(mailRecords.value) ? [...mailRecords.value] : []
  const { prop, order } = sortState.value || {}
  if (!prop || !order) return records
  const direction = order === 'ascending' ? 1 : -1
  const getValue = (row) => {
    if (prop === 'received_time') return row?.received_time ? new Date(row.received_time).getTime() : 0
    return (row?.[prop] ?? '').toString().toLowerCase()
  }
  records.sort((a, b) => {
    const va = getValue(a)
    const vb = getValue(b)
    if (va < vb) return -1 * direction
    if (va > vb) return 1 * direction
    return 0
  })
  return records
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

const syncEditorToForm = () => {
  composeForm.value.content = editorRef.value?.innerHTML || ''
}

const setEditorContent = async (html = '') => {
  await nextTick()
  if (editorRef.value) {
    editorRef.value.innerHTML = html
  }
  composeForm.value.content = html
}

const applyEditorCommand = (command, value = null) => {
  if (!editorRef.value) return
  editorRef.value.focus()
  document.execCommand(command, false, value)
  syncEditorToForm()
}

const onFontSizeChange = () => {
  applyEditorCommand('fontSize', fontSizeValue.value)
}

const triggerInlineImagePick = () => inlineImageInputRef.value?.click()
const triggerAttachmentPick = () => attachmentInputRef.value?.click()

const handleInlineImageChange = async (event) => {
  const files = Array.from(event.target.files || [])
  if (!files.length) return
  for (const file of files) {
    if (!file.type.startsWith('image/')) continue
    const contentBase64 = await fileToBase64(file)
    const dataUrl = `data:${file.type};base64,${contentBase64}`
    applyEditorCommand('insertHTML', `<img src="${dataUrl}" alt="${file.name}" style="max-width: 100%; height: auto;" />`)
  }
  event.target.value = ''
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

const normalizeSenderToEmail = (sender) => {
  if (!sender) return ''
  if (sender.includes('<') && sender.includes('>')) {
    return sender.split('<', 1)[1].split('>', 1)[0].trim()
  }
  return sender.trim()
}

const loadEmails = async () => {
  loading.value = true
  try {
    await emailsStore.fetchEmails()
    await loadMailRecords()
  } finally {
    loading.value = false
  }
}

const loadMailRecords = async () => {
  loadingMails.value = true
  try {
    if (selectedEmailId.value === 'all') {
      const responses = await Promise.all(
        emails.value.map((email) => api.emails.getRecords(email.id).catch(() => []))
      )
      mailRecordsData.value = responses.flat()
    } else {
      const res = await api.emails.getRecords(selectedEmailId.value)
      mailRecordsData.value = Array.isArray(res) ? res : []
    }
    if (!mailRecordsData.value.length) {
      activeMail.value = null
      activeAttachments.value = []
      detailVisible.value = false
    }
  } finally {
    loadingMails.value = false
  }
}

const handleSelectEmail = async (id) => {
  selectedEmailId.value = id === 'all' ? 'all' : Number(id)
  selectedMailIds.value = []
  await loadMailRecords()
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
  composeMode.value = 'new'
  replyAction.value = 'reply'
  composeForm.value = { to: '', cc: '', bcc: '', subject: '', content: '' }
  composeAttachments.value = []
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
  composeVisible.value = true
  setEditorContent('')
}

const sendCompose = async () => {
  if (!selectedEmailId.value || selectedEmailId.value === 'all') {
    ElMessage.warning('请先选择具体邮箱账号再发信')
    return
  }
  composeLoading.value = true
  try {
    if (composeMode.value === 'reply' && activeMail.value) {
      await api.emails.replyMail(activeMail.value.id, {
        action: replyAction.value,
        to: parseRecipients(composeForm.value.to),
        cc: parseRecipients(composeForm.value.cc),
        bcc: parseRecipients(composeForm.value.bcc),
        subject: composeForm.value.subject,
        content: composeForm.value.content,
        attachments: composeAttachments.value
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
        content: composeForm.value.content,
        attachments: composeAttachments.value
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
  await loadMailRecords()
}

onMounted(async () => {
  await loadEmails()
})
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

.email-type {
  font-size: 12px;
  color: var(--text-light);
}

.records-table {
  width: 100%;
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
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 8px;
  border-bottom: 1px solid var(--border-color, #dcdfe6);
  background: #fafafa;
}

.font-size-select {
  width: 88px;
}

.compose-editor {
  min-height: 280px;
  max-height: 420px;
  overflow: auto;
  padding: 10px;
  outline: none;
  line-height: 1.6;
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
