<template>
  <div class="search-component">
    <div class="search-container">
      <el-input
        v-model="searchQuery"
        placeholder="搜索邮件..."
        clearable
        :prefix-icon="Search"
        @keyup.enter="handleSearch"
      >
        <template #append>
          <el-button :icon="Search" @click="handleSearch">搜索</el-button>
        </template>
      </el-input>

      <div class="search-options">
        <span class="search-in-label">搜索范围:</span>
        <el-checkbox-group v-model="searchIn">
          <el-checkbox label="subject">标题</el-checkbox>
          <el-checkbox label="sender">发件人</el-checkbox>
          <el-checkbox label="recipient">收件人</el-checkbox>
          <el-checkbox label="content">正文</el-checkbox>
        </el-checkbox-group>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { Search } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import logger from '@/utils/debugLogger';

const router = useRouter();
const route = useRoute();

const DEFAULT_SEARCH_IN = ['subject', 'sender', 'content'];
const searchQuery = ref('');
const searchIn = ref([...DEFAULT_SEARCH_IN]);

const normalizeQueryValue = (value) => {
  if (Array.isArray(value)) {
    return value[0] ?? '';
  }
  return typeof value === 'string' ? value : '';
};

const handleSearch = async () => {
  const keyword = String(searchQuery.value || '').trim();
  logger.debug('search-component', 'handleSearch:click', {
    keyword,
    fields: searchIn.value
  });
  if (!keyword) {
    ElMessage.warning('请输入搜索关键词');
    return;
  }

  if (!Array.isArray(searchIn.value) || searchIn.value.length === 0) {
    ElMessage.warning('请至少选择一个搜索范围');
    return;
  }

  try {
    await router.push({
      name: 'search',
      query: {
        q: keyword,
        in: searchIn.value.join(',')
      }
    });
  } catch (error) {
    logger.error('search-component', 'handleSearch:navigation_error', { message: error?.message });
    // Ignore duplicate navigation errors, surface others.
    if (!String(error?.message || '').includes('Avoided redundant navigation')) {
      ElMessage.error('跳转搜索页失败');
      console.error('跳转搜索页失败:', error);
    }
  }
};

onMounted(() => {
  const queryText = normalizeQueryValue(route.query.q);
  const inText = normalizeQueryValue(route.query.in);

  if (queryText) {
    searchQuery.value = queryText;
  }

  if (inText) {
    const parsed = inText.split(',').map((item) => item.trim()).filter(Boolean);
    searchIn.value = parsed.length > 0 ? parsed : [...DEFAULT_SEARCH_IN];
  }
});
</script>

<style scoped>
.search-component {
  width: 100%;
  max-width: 800px;
  margin: 0 auto;
}

.search-container {
  background-color: #fff;
  border-radius: 12px;
  padding: 20px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08);
  transition: all 0.3s ease;
}

.search-container:hover {
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.12);
}

:deep(.el-input__wrapper) {
  padding: 0 10px;
  height: 46px;
}

:deep(.el-input__inner) {
  font-size: 16px;
}

:deep(.el-button) {
  height: 46px;
  font-size: 16px;
  padding: 0 20px;
}

.search-options {
  margin-top: 16px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  padding: 5px 0;
}

.search-in-label {
  margin-right: 16px;
  color: #606266;
  font-size: 14px;
  font-weight: 600;
}

:deep(.el-checkbox__label) {
  font-size: 14px;
  padding-left: 6px;
}

:deep(.el-checkbox) {
  margin-right: 16px;
  margin-top: 5px;
  margin-bottom: 5px;
}

@media (max-width: 768px) {
  .search-options {
    flex-direction: column;
    align-items: flex-start;
  }

  .search-in-label {
    margin-bottom: 10px;
  }

  .search-container {
    padding: 16px;
  }
}
</style>
