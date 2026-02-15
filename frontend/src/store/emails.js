import { defineStore } from 'pinia';
import api from '@/services/api';
import websocket from '@/services/websocket';
import logger from '@/utils/debugLogger';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export const useEmailsStore = defineStore('emails', {
  state: () => ({
    emails: [],
    loading: false,
    error: null,
    selectedEmails: [],
    processingEmails: {},
    currentMailRecords: [],
    currentEmailId: null,
    isConnected: false,
    listenersInitialized: false
  }),

  getters: {
    getEmailById: (state) => (id) => state.emails.find((email) => email.id === id),
    getProcessingStatus: (state) => (id) => state.processingEmails[id] || null,
    hasSelectedEmails: (state) => Array.isArray(state.selectedEmails) && state.selectedEmails.length > 0,
    selectedEmailsCount: (state) => (Array.isArray(state.selectedEmails) ? state.selectedEmails.length : 0),
    isAllSelected: (state) => state.emails.length > 0
      && Array.isArray(state.selectedEmails)
      && state.selectedEmails.length === state.emails.length
  },

  actions: {
    initWebSocketListeners() {
      logger.debug('emails-store', 'initWebSocketListeners:start', { initialized: this.listenersInitialized });
      if (this.listenersInitialized) return;
      this.listenersInitialized = true;

      websocket.onConnect(() => {
        logger.debug('emails-store', 'ws:onConnect');
        this.isConnected = true;
        this.fetchEmails().catch((e) => console.error('fetchEmails on connect failed:', e));
      });

      websocket.onDisconnect(() => {
        logger.warn('emails-store', 'ws:onDisconnect');
        this.isConnected = false;
      });

      websocket.onMessage('emails_list', (data) => {
        logger.debug('emails-store', 'ws:emails_list', { count: Array.isArray(data?.data) ? data.data.length : -1 });
        if (data && Array.isArray(data.data)) {
          this.emails = data.data;
        }
      });

      websocket.onMessage('email_added', () => {
        this.fetchEmails().catch((e) => console.error('fetchEmails after email_added failed:', e));
      });

      websocket.onMessage('emails_deleted', (data) => {
        if (!data || !Array.isArray(data.email_ids)) return;
        this.emails = this.emails.filter((email) => !data.email_ids.includes(email.id));
        this.selectedEmails = this.selectedEmails.filter((id) => !data.email_ids.includes(id));
      });

      websocket.onMessage('emails_imported', () => {
        this.fetchEmails().catch((e) => console.error('fetchEmails after emails_imported failed:', e));
      });

      websocket.onMessage('check_progress', (data) => {
        const { email_id, progress, message } = data || {};
        if (typeof email_id === 'undefined') return;
        this.processingEmails[email_id] = { progress, message };

        if (progress === 100) {
          setTimeout(() => {
            this.fetchEmails().catch((e) => console.error('fetchEmails after check_progress failed:', e));
            if (this.currentEmailId === email_id) {
              this.fetchMailRecords(email_id).catch((e) => console.error('fetchMailRecords after check_progress failed:', e));
            }
          }, 1000);
        }
      });

      websocket.onMessage('mail_records', (data) => {
        if (!data || Number(data.email_id) !== Number(this.currentEmailId)) return;
        const records = Array.isArray(data.data) ? data.data : [];
        this.currentMailRecords = records.map((record) => ({
          id: record.id || Date.now() + Math.random().toString(36).slice(2, 10),
          subject: record.subject || '(无主题)',
          sender: record.sender || '(未知发件人)',
          received_time: record.received_time || new Date().toISOString(),
          content: record.content || '(无内容)',
          folder: record.folder || 'INBOX',
          is_read: typeof record.is_read !== 'undefined' ? record.is_read : 1,
          graph_message_id: record.graph_message_id || null
        }));
      });

      websocket.onMessage('error', (data) => {
        this.error = data?.message || 'WebSocket 错误';
        console.error('WebSocket error:', data?.message || data);
      });
    },

    async addEmail(emailData) {
      this.loading = true;
      this.error = null;
      try {
        if (!websocket.isConnected) {
          await api.emails.add(emailData);
        } else {
          websocket.send('add_email', {
            ...emailData,
            mail_type: emailData.mail_type || 'imap'
          });
        }
      } catch (error) {
        this.error = '添加邮箱失败';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    async importEmails(importData) {
      this.loading = true;
      this.error = null;
      try {
        if (!websocket.isConnected) {
          await api.emails.import(importData);
        } else {
          websocket.send('import_emails', importData);
        }
      } catch (error) {
        this.error = '导入邮箱失败';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    async fetchEmails() {
      const startedAt = Date.now();
      logger.debug('emails-store', 'fetchEmails:start', {
        wsConnected: websocket.isConnected,
        wsAuthenticated: websocket.isAuthenticated
      });
      this.loading = true;
      this.error = null;
      try {
        let lastError = null;
        for (let attempt = 1; attempt <= 3; attempt += 1) {
          try {
            logger.debug('emails-store', 'fetchEmails:ws_attempt', { attempt });
            const response = await websocket.requestResponse({
              sendType: 'get_all_emails',
              responseType: 'emails_list',
              timeoutMs: 10000
            });
            if (response && Array.isArray(response.data)) {
              this.emails = response.data;
              lastError = null;
              break;
            }
            throw new Error('emails_list 响应格式无效');
          } catch (error) {
            lastError = error;
            logger.warn('emails-store', 'fetchEmails:ws_attempt_failed', { attempt, message: error?.message });
            websocket.reconnect();
            await sleep(300);
          }
        }

        if (lastError) {
          logger.warn('emails-store', 'fetchEmails:http_fallback');
          const response = await api.emails.getAll();
          if (Array.isArray(response)) {
            this.emails = response;
            lastError = null;
          } else {
            throw lastError;
          }
        }
      } catch (error) {
        this.error = '获取邮箱列表失败';
        logger.error('emails-store', 'fetchEmails:error', { message: error?.message });
        console.error(error);
      } finally {
        this.loading = false;
        logger.debug('emails-store', 'fetchEmails:end', {
          durationMs: Date.now() - startedAt,
          count: Array.isArray(this.emails) ? this.emails.length : -1,
          error: this.error
        });
      }
    },

    async deleteEmail(emailId) {
      this.loading = true;
      this.error = null;
      try {
        if (!websocket.isConnected) {
          await api.emails.delete([emailId]);
        } else {
          websocket.send('delete_emails', { email_ids: [emailId] });
        }
        this.emails = this.emails.filter((email) => email.id !== emailId);
        this.selectedEmails = this.selectedEmails.filter((id) => id !== emailId);
      } catch (error) {
        this.error = '删除邮箱失败';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    async deleteEmails(emailIds) {
      if (!Array.isArray(emailIds) || emailIds.length === 0) return;

      this.loading = true;
      this.error = null;
      try {
        if (!websocket.isConnected) {
          await api.emails.delete(emailIds);
        } else {
          websocket.send('delete_emails', { email_ids: emailIds });
        }
        this.emails = this.emails.filter((email) => !emailIds.includes(email.id));
        this.selectedEmails = this.selectedEmails.filter((id) => !emailIds.includes(id));
      } catch (error) {
        this.error = '删除邮箱失败';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    async checkEmail(emailId) {
      try {
        const response = await api.emails.check([emailId]);
        if (response.status === 409) {
          return { success: false, message: response.data.message, status: 'processing' };
        }
        return true;
      } catch (error) {
        if (error.response && error.response.status === 409) {
          return { success: false, message: error.response.data.message, status: 'processing' };
        }
        throw error;
      }
    },

    async checkEmails(emailIds) {
      if (!Array.isArray(emailIds) || emailIds.length === 0) return;

      this.loading = true;
      this.error = null;
      try {
        if (!websocket.isConnected) {
          await api.emails.check(emailIds);
        } else {
          websocket.send('check_emails', { email_ids: emailIds });
        }
      } catch (error) {
        this.error = '检查邮箱失败';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    async fetchMailRecords(emailId) {
      const startedAt = Date.now();
      logger.debug('emails-store', 'fetchMailRecords:start', {
        emailId,
        wsConnected: websocket.isConnected,
        wsAuthenticated: websocket.isAuthenticated
      });
      this.loading = true;
      this.error = null;
      try {
        this.currentEmailId = emailId;
        let response = null;
        let lastError = null;
        for (let attempt = 1; attempt <= 3; attempt += 1) {
          try {
            logger.debug('emails-store', 'fetchMailRecords:ws_attempt', { attempt, emailId });
            response = await websocket.requestResponse({
              sendType: 'get_mail_records',
              payload: { email_id: emailId },
              responseType: 'mail_records',
              match: (msg) => Number(msg?.email_id) === Number(emailId),
              timeoutMs: 15000
            });
            lastError = null;
            break;
          } catch (error) {
            lastError = error;
            logger.warn('emails-store', 'fetchMailRecords:ws_attempt_failed', {
              attempt,
              emailId,
              message: error?.message
            });
            websocket.reconnect();
            await sleep(300);
          }
        }

        if (lastError) {
          logger.warn('emails-store', 'fetchMailRecords:http_fallback', { emailId });
          const response = await api.emails.getRecords(emailId);
          const records = Array.isArray(response) ? response : [];
          this.currentMailRecords = records.map((record) => ({
            id: record.id || Date.now() + Math.random().toString(36).slice(2, 10),
            subject: record.subject || '(无主题)',
            sender: record.sender || '(未知发件人)',
            received_time: record.received_time || new Date().toISOString(),
            content: record.content || '(无内容)',
            folder: record.folder || 'INBOX',
            is_read: typeof record.is_read !== 'undefined' ? record.is_read : 1,
            graph_message_id: record.graph_message_id || null
          }));
          return;
        }

        const records = Array.isArray(response?.data) ? response.data : [];
        this.currentMailRecords = records.map((record) => ({
          id: record.id || Date.now() + Math.random().toString(36).slice(2, 10),
          subject: record.subject || '(无主题)',
          sender: record.sender || '(未知发件人)',
          received_time: record.received_time || new Date().toISOString(),
          content: record.content || '(无内容)',
          folder: record.folder || 'INBOX',
          is_read: typeof record.is_read !== 'undefined' ? record.is_read : 1,
          graph_message_id: record.graph_message_id || null
        }));
      } catch (error) {
        this.error = '获取邮件记录失败';
        console.error(error);
      } finally {
        this.loading = false;
      }
    },

    async recheckEmailAll(emailId) {
      return api.emails.recheckAll(emailId);
    },

    async markMailRead(mailId) {
      await api.emails.markRead(mailId);
      const record = this.currentMailRecords.find((item) => item.id === mailId);
      if (record) record.is_read = 1;

      if (this.currentEmailId) {
        const email = this.emails.find((item) => item.id === this.currentEmailId);
        if (email && typeof email.unread_count === 'number' && email.unread_count > 0) {
          email.unread_count -= 1;
        }
      }
      return true;
    },

    async getEmailPassword(emailId) {
      return api.emails.getPassword(emailId);
    },

    toggleSelectEmail(emailId) {
      if (!Array.isArray(this.selectedEmails)) {
        this.selectedEmails = [];
      }
      const index = this.selectedEmails.indexOf(emailId);
      if (index === -1) this.selectedEmails.push(emailId);
      else this.selectedEmails.splice(index, 1);
    },

    selectAllEmails() {
      if (!Array.isArray(this.emails)) {
        this.selectedEmails = [];
        return;
      }
      this.selectedEmails = this.emails.map((email) => email.id);
    },

    resetState() {
      this.emails = [];
      this.loading = false;
      this.error = null;
      this.selectedEmails = [];
      this.processingEmails = {};
      this.currentMailRecords = [];
      this.currentEmailId = null;
      this.isConnected = false;
      this.listenersInitialized = false;
    },

    async updateEmail(email) {
      const emailData = { ...email };
      if (emailData.mail_type === 'imap' && 'use_ssl' in emailData) {
        emailData.use_ssl = Boolean(emailData.use_ssl);
      }

      await api.put(`/emails/${emailData.id}`, emailData);

      const index = this.emails.findIndex((e) => e.id === emailData.id);
      if (index !== -1) {
        this.emails[index] = { ...this.emails[index], ...emailData };
      }
      return true;
    }
  }
});
