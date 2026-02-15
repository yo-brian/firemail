<template>
  <div class="search-view">
    <h1 class="page-title">搜索邮件</h1>

    <div class="search-bar">
      <SearchComponent />
    </div>

    <el-card class="search-results-card" v-loading="loading">
      <template #header>
        <div class="card-header">
          <h2>搜索结果</h2>
          <div class="result-info" v-if="!loading">
            找到 {{ searchResults.length }} 条结果
          </div>
        </div>
      </template>

      <div v-if="searchResults.length > 0">
        <el-table :data="searchResults" style="width: 100%" stripe border>
          <el-table-column prop="subject" label="标题" min-width="250" show-overflow-tooltip>
            <template #default="scope">
              <a href="#" @click.prevent="viewMailContent(scope.row)" class="mail-link">
                {{ scope.row.subject }}
              </a>
            </template>
          </el-table-column>
          <el-table-column prop="sender" label="发件人" min-width="200" show-overflow-tooltip>
            <template #default="scope">
              <a href="#" @click.prevent="searchBySender(scope.row.sender)" class="mail-link">
                {{ scope.row.sender }}
              </a>
            </template>
          </el-table-column>
          <el-table-column prop="email_address" label="收件邮箱" min-width="180" show-overflow-tooltip>
            <template #default="scope">
              <a href="#" @click.prevent="viewAllMailsByEmail(scope.row.email_id)" class="mail-link">
                {{ scope.row.email_address }}
              </a>
            </template>
          </el-table-column>
          <el-table-column prop="received_time" label="接收时间" width="180">
            <template #default="scope">
              {{ formatDate(scope.row.received_time) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="120" fixed="right">
            <template #default="scope">
              <el-button type="primary" size="small" @click="viewMailContent(scope.row)" :icon="Document">
                查看
              </el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <div v-else-if="hasSearched && !loading" class="no-results">
        <el-empty description="未找到符合条件的邮件" />
      </div>

      <div v-else-if="!hasSearched && !loading" class="search-tip">
        请在上方输入关键词开始搜索
      </div>
    </el-card>

    <el-dialog
      v-model="mailContentDialogVisible"
      :title="selectedMail ? selectedMail.subject : '邮件内容'"
      width="70%"
      top="5vh"
      class="mail-content-dialog"
    >
      <div v-if="selectedMail" class="mail-detail">
        <EmailContentViewer
          :mail="selectedMail"
          :attachments="selectedMail.attachments || []"
          :loading-attachments="false"
        />
      </div>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Document } from '@element-plus/icons-vue';
import SearchComponent from '@/components/SearchComponent.vue';
import EmailContentViewer from '@/components/EmailContentViewer.vue';
import api from '@/services/api';
import logger from '@/utils/debugLogger';

const router = useRouter();
const route = useRoute();

const loading = ref(false);
const searchResults = ref([]);
const hasSearched = ref(false);
const mailContentDialogVisible = ref(false);
const selectedMail = ref(null);
const latestRequestId = ref(0);

const normalizeQueryValue = (value) => {
  if (Array.isArray(value)) {
    return value[0] ?? '';
  }
  return typeof value === 'string' ? value : '';
};

const formatDate = (dateString) => {
  if (!dateString) return '未知';
  const date = new Date(dateString);
  if (Number.isNaN(date.getTime())) return String(dateString);
  return date.toLocaleString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  });
};

const performSearch = async (query, searchInFields) => {
  logger.debug('search-view', 'performSearch:start', { query, fields: searchInFields });
  if (!query || !Array.isArray(searchInFields) || searchInFields.length === 0) {
    return;
  }

  const requestId = ++latestRequestId.value;
  loading.value = true;
  hasSearched.value = true;

  try {
    const response = await api.search(query, searchInFields);

    if (requestId !== latestRequestId.value) {
      return;
    }

    searchResults.value = response?.data?.results || [];
    if (searchResults.value.length === 0) {
      ElMessage.info('未找到符合条件的邮件');
    }
  } catch (error) {
    logger.error('search-view', 'performSearch:error', { message: error?.message, query, fields: searchInFields });
    if (requestId !== latestRequestId.value) {
      return;
    }
    console.error('搜索失败:', error);
    ElMessage.error(error?.response?.data?.error || '搜索失败，请稍后重试');
    searchResults.value = [];
  } finally {
    logger.debug('search-view', 'performSearch:end', {
      query,
      resultCount: searchResults.value.length,
      loading: loading.value
    });
    if (requestId === latestRequestId.value) {
      loading.value = false;
    }
  }
};

const viewMailContent = (mail) => {
  selectedMail.value = mail;
  mailContentDialogVisible.value = true;
};

const searchBySender = async (sender) => {
  try {
    await router.push({
      name: 'search',
      query: { q: sender, in: 'sender' }
    });
  } catch (error) {
    console.error('按发件人搜索跳转失败:', error);
  }
};

const viewAllMailsByEmail = async (emailId) => {
  try {
    await router.push({
      name: 'email-detail',
      params: { id: emailId }
    });
  } catch (error) {
    console.error('跳转邮箱详情失败:', error);
  }
};

watch(
  () => route.query,
  (newQuery) => {
    logger.debug('search-view', 'route-query:changed', { query: newQuery });
    const q = normalizeQueryValue(newQuery.q).trim();
    const inText = normalizeQueryValue(newQuery.in);

    if (!q) {
      loading.value = false;
      searchResults.value = [];
      hasSearched.value = false;
      return;
    }

    const fields = (inText || 'subject,sender,content')
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);

    performSearch(q, fields.length > 0 ? fields : ['subject', 'sender', 'content']);
  },
  { immediate: true }
);
</script>

<style scoped>
.search-view {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  min-height: calc(100vh - 180px);
}

.page-title {
  font-size: 26px;
  margin-bottom: 20px;
  color: #303133;
  text-align: center;
  font-weight: 600;
}

.search-bar {
  margin-bottom: 30px;
}

.search-results-card {
  background-color: #fff;
  border-radius: 12px;
  min-height: 300px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  margin-bottom: 30px;
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 0;
}

.card-header h2 {
  font-size: 18px;
  margin: 0;
  color: #303133;
  font-weight: 600;
}

.result-info {
  color: #909399;
  font-size: 14px;
  background-color: #f2f6fc;
  padding: 4px 10px;
  border-radius: 4px;
}

.no-results,
.search-tip {
  text-align: center;
  padding: 60px 0;
  color: #909399;
  font-size: 16px;
}

.mail-link {
  color: #409eff;
  text-decoration: none;
  transition: color 0.2s;
}

.mail-link:hover {
  text-decoration: underline;
  color: #66b1ff;
}

.mail-detail {
  padding: 0 20px;
}

:deep(.el-table) {
  border-radius: 8px;
  overflow: hidden;
}

:deep(.el-table th) {
  background-color: #f5f7fa;
  font-weight: 600;
}

:deep(.el-table .cell) {
  padding: 12px 8px;
}

:deep(.el-button) {
  padding: 8px 15px;
}

@media (max-width: 768px) {
  .search-view {
    padding: 10px;
  }

  .mail-detail {
    padding: 0 10px;
  }

  .page-title {
    font-size: 22px;
  }
}
</style>
