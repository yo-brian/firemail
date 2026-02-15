import axios from 'axios';

// 获取API基础URL
const getBaseUrl = () => {
  console.group('API基础URL检测');

  // 优先使用全局配置的API_URL（由env-config.js设置）
  if (window.API_URL) {
    // 确保API_URL以/api结尾
    let baseUrl = window.API_URL;
    if (!baseUrl.endsWith('/api')) {
      baseUrl = baseUrl + '/api';
    }
    console.log('使用全局配置的API_URL:', baseUrl);
    console.groupEnd();
    return baseUrl;
  }

  // 回退方案：使用相对路径
  const url = '/api';
  console.log('使用相对路径API基础URL:', url);
  console.groupEnd();
  return url;
};

// 创建axios实例
const api = axios.create({
  baseURL: getBaseUrl(),
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json'
  }
});

// 输出API基础URL
console.log('API基础URL:', api.defaults.baseURL);

// 请求拦截器
api.interceptors.request.use(
  config => {
    console.log(`API请求: ${config.method.toUpperCase()} ${config.url}`);
    return config;
  },
  error => {
    console.error('API请求错误:', error);
    return Promise.reject(error);
  }
);

// 响应拦截器
api.interceptors.response.use(
  response => {
    console.log(`API响应: ${response.config.url}`, response.data);
    return response;
  },
  error => {
    if (error.response) {
      console.error('API响应错误:', error.response.status, error.response.data);

      // 特殊处理401未授权错误
      if (error.response.status === 401) {
        console.log('用户未认证，跳转到登录页面');
        // 清除本地存储的令牌
        localStorage.removeItem('token');
        // 如果不在登录页面，重定向到登录页面
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
        }
      }

      // 特殊处理409冲突错误
      else if (error.response.status === 409) {
        console.log('资源冲突:', error.response.data);
      }
    } else if (error.request) {
      console.error('API请求未收到响应:', error.request);
      // 服务器未响应的处理
      const errorMessage = '无法连接到服务器，请检查后端服务是否启动';
      error.response = { data: { message: errorMessage, error: 'Failed to fetch' } };

      // 创建自定义错误
      const fetchError = new Error(errorMessage);
      fetchError.name = 'fetchError';
      fetchError.isConnectionError = true;
      error.fetchError = fetchError;
    } else {
      console.error('API请求错误:', error.message);
      // 其他错误处理
      error.response = { data: { message: error.message || '请求出错' } };
    }
    return Promise.reject(error);
  }
);

// 认证相关API
export const setAuthHeader = (token) => {
  if (token) {
    api.defaults.headers.common['Authorization'] = `Bearer ${token}`;
  }
}

export const removeAuthHeader = () => {
  delete api.defaults.headers.common['Authorization'];
}

// API方法
const apiMethods = {
  // 系统配置
  getConfig: function(retryCount = 0, maxRetries = 3) {
    console.log(`尝试获取系统配置 (尝试 ${retryCount + 1}/${maxRetries + 1})`);
    return api.get('/config')
      .catch(error => {
        console.error('获取系统配置失败:', error);

        // 如果是网络错误且未超过最大重试次数，则进行重试
        if (error.request && retryCount < maxRetries) {
          const retryDelay = Math.min(1000 * Math.pow(2, retryCount), 5000); // 指数延迟，最大5秒
          console.log(`将在 ${retryDelay}ms 后重试获取系统配置`);

          return new Promise(resolve => {
            setTimeout(() => {
              resolve(this.getConfig(retryCount + 1, maxRetries));
            }, retryDelay);
          });
        }

        // 超过重试次数或其他错误，返回默认配置
        console.warn('无法获取系统配置，使用默认值（允许注册）');
        return Promise.resolve({
          data: {
            allow_register: true
          }
        });
      });
  },

  toggleRegistration: (allow) => {
    return api.post('/admin/config/registration', { allow });
  },

  // 认证相关
  login: (username, password) => {
    console.log('调用登录API...', username);

    // 增加对API_URL的检查
    console.log('当前API基础URL:', api.defaults.baseURL);

    return api.post('/auth/login', { username, password })
      .then(response => {
        // 检查响应数据格式，防止HTML响应导致错误
        if (typeof response.data === 'string' && response.data.includes('<!DOCTYPE html>')) {
          console.error('接收到HTML响应而非预期的JSON数据，这可能意味着API请求被路由到了前端应用');
          // 重新构建错误对象
          const error = new Error('登录失败：收到HTML响应，请检查后端服务配置');
          error.htmlResponse = true;
          error.responseData = response.data;
          return Promise.reject(error);
        }

        // 验证响应中包含预期的token和用户数据
        if (!response.data.token) {
          console.error('登录响应缺少token:', response.data);
          return Promise.reject(new Error('登录失败：响应缺少token'));
        }

        if (!response.data.user) {
          console.error('登录响应缺少user对象:', response.data);
          return Promise.reject(new Error('登录失败：响应缺少用户信息'));
        }

        return response;
      })
      .catch(error => {
        // 添加对特定错误的额外处理
        if (error.htmlResponse) {
          console.error('请求收到HTML而非JSON，尝试使用备用URL重试');
          // 这里可以尝试备用方式或显示更有用的错误信息
        }

        // 重新抛出错误供上层处理
        throw error;
      });
  },

  logout: () => {
    return api.post('/auth/logout');
  },

  register: (username, password) => {
    console.log('发送注册请求:', { username, password });
    return api.post('/auth/register', { username, password });
  },

  getCurrentUser: () => {
    return api.get('/auth/user');
  },

  changePassword: (oldPassword, newPassword) => {
    return api.post('/auth/change-password', { old_password: oldPassword, new_password: newPassword });
  },

  // 用户管理 (管理员)
  getAllUsers: () => {
    return api.get('/users');
  },

  createUser: (userData) => {
    return api.post('/users', userData);
  },

  deleteUser: (userId) => {
    return api.delete(`/users/${userId}`);
  },

  resetUserPassword: (userId, newPassword) => {
    return api.post(`/users/${userId}/reset-password`, { new_password: newPassword });
  },

  // 邮箱相关
  getAllEmails: () => {
    return api.get('/emails');
  },

  getEmailById: (id) => {
    return api.get(`/emails/${id}`);
  },

  addEmail: (email, password, clientId, refreshToken, mailType = 'outlook') => {
    return api.post('/emails', {
      email,
      password,
      client_id: clientId,
      refresh_token: refreshToken,
      mail_type: mailType
    });
  },

  deleteEmail: (id) => {
    return api.delete(`/emails/${id}`);
  },

  batchDeleteEmails: (ids) => {
    return api.post('/emails/batch_delete', { email_ids: ids });
  },

  checkEmail: (emailId) => {
    return api.post(`/emails/${emailId}/check`, null, { timeout: 60000 });
  },

  recheckEmailAll: (emailId) => {
    return api.post(`/emails/${emailId}/recheck_all`, null, { timeout: 60000 });
  },

  batchCheckEmails: (emailIds) => {
    return api.post('/emails/batch_check', { email_ids: emailIds }, { timeout: 60000 });
  },

  getMailRecords: (emailId) => {
    return api.get(`/emails/${emailId}/mail_records`);
  },

  getMailRecordsPage: ({ emailId = null, page = 1, pageSize = 20 } = {}) => {
    const params = { page, page_size: pageSize };
    if (emailId !== null && typeof emailId !== 'undefined') {
      params.email_id = emailId;
    }
    return api.get('/mail_records', { params });
  },

  getMailAttachments: (mailId) => {
    return api.get(`/mail_records/${mailId}/attachments`);
  },

  markMailRead: (mailId) => {
    return api.post(`/mail_records/${mailId}/mark-read`);
  },

  getMailTags: ({ emailId = null, limit = 200 } = {}) => {
    const params = { limit };
    if (emailId !== null && typeof emailId !== 'undefined') {
      params.email_id = emailId;
    }
    return api.get('/mail_records/tags', { params });
  },

  sendMail: (emailId, payload) => {
    return api.post(`/emails/${emailId}/send_mail`, payload);
  },

  replyMail: (mailId, payload) => {
    return api.post(`/mail_records/${mailId}/reply`, payload);
  },

  deleteMailRecord: (mailId) => {
    return api.delete(`/mail_records/${mailId}`);
  },
  batchDeleteMailRecords: (mailIds) => {
    return api.post('/mail_records/batch_delete', { mail_ids: mailIds });
  },

  getEmailPassword: (emailId) => {
    return api.get(`/emails/${emailId}/password`);
  },

  importEmails: (data, mailType) => {
    return api.post('/emails/import', { data, mail_type: mailType });
  },

  search: (query, searchIn = []) => {
    return api.post('/search', { query, search_in: searchIn });
  },

  // 邮箱相关接口
  emails: {
    getAll: () => api.get('/emails').then(res => res.data),
    getPassword: (emailId) => api.get(`/emails/${emailId}/password`).then(res => res.data),
    getRecords: (emailId) => api.get(`/emails/${emailId}/mail_records`).then(res => res.data),
    getRecordsPage: ({ emailId = null, page = 1, pageSize = 20 } = {}) => {
      const params = { page, page_size: pageSize };
      if (emailId !== null && typeof emailId !== 'undefined') {
        params.email_id = emailId;
      }
      return api.get('/mail_records', { params }).then(res => res.data);
    },
    getAttachments: (mailId) => api.get(`/mail_records/${mailId}/attachments`).then(res => res.data),
    markRead: (mailId) => api.post(`/mail_records/${mailId}/mark-read`).then(res => res.data),
    setTag: (mailId, tag) => api.post(`/mail_records/${mailId}/tag`, { tag }).then(res => res.data),
    getTags: ({ emailId = null, limit = 200 } = {}) => {
      const params = { limit };
      if (emailId !== null && typeof emailId !== 'undefined') {
        params.email_id = emailId;
      }
      return api.get('/mail_records/tags', { params }).then(res => res.data);
    },
    sendMail: (emailId, payload) => api.post(`/emails/${emailId}/send_mail`, payload).then(res => res.data),
    replyMail: (mailId, payload) => api.post(`/mail_records/${mailId}/reply`, payload).then(res => res.data),
    deleteMail: (mailId) => api.delete(`/mail_records/${mailId}`).then(res => res.data),
    batchDeleteMail: (mailIds) => api.post('/mail_records/batch_delete', { mail_ids: mailIds }).then(res => res.data),
    add: (emailData) => api.post('/emails', emailData),
    check: (emailIds) => {
      if (Array.isArray(emailIds) && emailIds.length === 1) {
        return api.post(`/emails/${emailIds[0]}/check`, null, { timeout: 60000 });
      } else {
        return api.post('/emails/batch_check', { email_ids: emailIds }, { timeout: 60000 });
      }
    },
    recheckAll: (emailId) => api.post(`/emails/${emailId}/recheck_all`, null, { timeout: 60000 }).then(res => res.data),
    delete: (emailIds) => {
      if (Array.isArray(emailIds) && emailIds.length === 1) {
        return api.delete(`/emails/${emailIds[0]}`);
      } else {
        return api.post('/emails/batch_delete', { email_ids: emailIds });
      }
    },
    import: (data) => api.post('/emails/import', data),
    initiateDeviceFlow: () => api.post('/outlook/graph/initiate'),
    checkDeviceFlow: (deviceCode) => api.get(`/outlook/graph/check/${deviceCode}`),
  },

  // 工具方法
  setAuthHeader,
  removeAuthHeader
}

// 从localStorage读取token并设置
const token = localStorage.getItem('token');
if (token) {
  setAuthHeader(token);
}

export default apiMethods;
