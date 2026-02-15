import logger from '@/utils/debugLogger';

const MessageTypes = {
  AUTHENTICATE: 'authenticate',
  AUTH_RESULT: 'auth_result',
  CONNECTION_ESTABLISHED: 'connection_established',

  GET_ALL_EMAILS: 'get_all_emails',
  CHECK_EMAILS: 'check_emails',
  DELETE_EMAILS: 'delete_emails',
  ADD_EMAIL: 'add_email',
  GET_MAIL_RECORDS: 'get_mail_records',
  IMPORT_EMAILS: 'import_emails',

  EMAILS_LIST: 'emails_list',
  CHECK_PROGRESS: 'check_progress',
  EMAILS_IMPORTED: 'emails_imported',
  EMAILS_DELETED: 'emails_deleted',
  EMAIL_ADDED: 'email_added',
  MAIL_RECORDS: 'mail_records',

  INFO: 'info',
  SUCCESS: 'success',
  WARNING: 'warning',
  ERROR: 'error'
};

class WebSocketService {
  constructor() {
    this.socket = null;
    this.isConnected = false;
    this.isAuthenticated = false;
    this.authAttempted = false;

    this.reconnectAttempts = 0;
    this.maxReconnectAttempts = 5;
    this.reconnectTimeoutId = null;
    this.baseDelay = 1000;

    this.messageHandlers = {};
    this.connectHandlers = [];
    this.disconnectHandlers = [];
    this.authSuccessHandlers = [];
    this.pendingRequests = [];

    this.heartbeatInterval = null;
    this.heartbeatTimeout = null;
    this.lastHeartbeatReceived = 0;

    this.url = this.getWebSocketUrl();
    console.log(`WebSocket service URL: ${this.url}`);
  }

  getWebSocketUrl() {
    if (window.WS_URL && typeof window.WS_URL === 'string') {
      if (window.WS_URL.startsWith('ws://') || window.WS_URL.startsWith('wss://')) {
        return window.WS_URL;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const hostname = window.location.hostname;
      const port = window.location.port;
      const host = port ? `${hostname}:${port}` : hostname;
      return `${protocol}//${host}${window.WS_URL}`;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const hostname = window.location.hostname;
    const wsPort = '8765';
    return `${protocol}//${hostname}:${wsPort}`;
  }

  connect() {
    logger.debug('ws-service', 'connect:called', {
      hasSocket: Boolean(this.socket),
      readyState: this.socket?.readyState,
      isConnected: this.isConnected,
      isAuthenticated: this.isAuthenticated
    });
    if (this.socket && (this.socket.readyState === WebSocket.CONNECTING || this.socket.readyState === WebSocket.OPEN)) {
      logger.debug('ws-service', 'connect:skip_existing_socket');
      return;
    }

    this.clearHeartbeat();
    this.isAuthenticated = false;
    this.authAttempted = false;

    const token = localStorage.getItem('token');
    if (!token) {
      logger.warn('ws-service', 'connect:skip_no_token');
      console.error('WebSocket connect skipped: token not found');
      return;
    }

    try {
      this.socket = new WebSocket(this.url);

      const connectionTimeout = setTimeout(() => {
        if (this.socket && this.socket.readyState !== WebSocket.OPEN) {
          this.socket.close();
        }
      }, 10000);

      this.socket.onopen = () => {
        logger.debug('ws-service', 'socket:onopen');
        clearTimeout(connectionTimeout);
        this.isConnected = true;
        this.reconnectAttempts = 0;

        setTimeout(() => this.sendAuthMessage(token), 200);
        this.startHeartbeat();
      };

      this.socket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          logger.debug('ws-service', 'socket:onmessage', { type: message?.type });
          if (message.type === 'heartbeat_response') {
            this.handleHeartbeatResponse();
            return;
          }
          this.handleMessage(message);
        } catch (error) {
          console.error('WebSocket message parse error:', error);
        }
      };

      this.socket.onclose = (event) => {
        logger.warn('ws-service', 'socket:onclose', {
          code: event?.code,
          reason: event?.reason
        });
        clearTimeout(connectionTimeout);
        this.isConnected = false;
        this.isAuthenticated = false;
        this.clearHeartbeat();
        this.notifyDisconnect();

        if (event.code !== 1000) {
          this.scheduleReconnect();
        }
      };

      this.socket.onerror = (error) => {
        console.error('WebSocket error:', error);
      };
    } catch (error) {
      console.error('Create WebSocket failed:', error);
    }
  }

  sendAuthMessage(token) {
    if (!this.isConnected || !this.socket) return;
    try {
      this.socket.send(JSON.stringify({ type: MessageTypes.AUTHENTICATE, token }));
      this.authAttempted = true;
    } catch (error) {
      console.error('Send auth message failed:', error);
      this.reconnect();
    }
  }

  scheduleReconnect() {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      (this.messageHandlers[MessageTypes.ERROR] || []).forEach((handler) => {
        try {
          handler({ type: MessageTypes.ERROR, message: '无法连接到 WebSocket 服务' });
        } catch {}
      });
      return;
    }

    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
    }

    const delay = Math.min(this.baseDelay * Math.pow(2, this.reconnectAttempts), 30000);
    this.reconnectTimeoutId = setTimeout(() => {
      this.reconnectAttempts += 1;
      this.connect();
    }, delay);
  }

  send(type, data = {}) {
    logger.debug('ws-service', 'send:called', {
      type,
      isConnected: this.isConnected,
      isAuthenticated: this.isAuthenticated
    });
    if (!this.isConnected) {
      this.connect();
      return false;
    }

    if (type !== MessageTypes.AUTHENTICATE && !this.isAuthenticated) {
      const token = localStorage.getItem('token');
      if (token) {
        setTimeout(() => this.sendAuthMessage(token), 200);
        this.pendingRequests.push({ type, data });
      }
      return false;
    }

    return this.doSend(type, data);
  }

  doSend(type, data = {}) {
    if (!this.socket) return false;
    try {
      this.socket.send(JSON.stringify({ type, ...data }));
      return true;
    } catch (error) {
      console.error('Send WebSocket message failed:', error);
      this.isConnected = false;
      this.isAuthenticated = false;
      this.scheduleReconnect();
      return false;
    }
  }

  handleMessage(message) {
    const type = message.type || 'unknown';

    if (type === MessageTypes.AUTH_RESULT) {
      if (message.success) {
        this.isAuthenticated = true;
        this.notifyAuthSuccess();
        this.notifyConnect();

        if (this.pendingRequests.length) {
          const pending = [...this.pendingRequests];
          this.pendingRequests = [];
          pending.forEach((req) => this.doSend(req.type, req.data));
        }
      } else {
        this.isAuthenticated = false;
      }
      return;
    }

    if (type === MessageTypes.ERROR && message.message === '请先进行认证') {
      this.isAuthenticated = false;
      const token = localStorage.getItem('token');
      if (token) {
        setTimeout(() => this.sendAuthMessage(token), 200);
      }
      return;
    }

    if (type === MessageTypes.CONNECTION_ESTABLISHED) {
      return;
    }

    const handlers = this.messageHandlers[type] || [];
    handlers.forEach((handler) => {
      try {
        handler(message);
      } catch (error) {
        console.error(`Handle message ${type} failed:`, error);
      }
    });
  }

  onMessage(type, handler) {
    if (!this.messageHandlers[type]) {
      this.messageHandlers[type] = [];
    }
    this.messageHandlers[type].push(handler);
  }

  offMessage(type, handler) {
    if (!this.messageHandlers[type]) return;
    if (handler) {
      this.messageHandlers[type] = this.messageHandlers[type].filter((h) => h !== handler);
    } else {
      delete this.messageHandlers[type];
    }
  }

  onConnect(handler) {
    this.connectHandlers.push(handler);
    if (this.isConnected && this.isAuthenticated) {
      handler();
    }
  }

  offConnect(handler) {
    this.connectHandlers = this.connectHandlers.filter((h) => h !== handler);
  }

  onDisconnect(handler) {
    this.disconnectHandlers.push(handler);
  }

  offDisconnect(handler) {
    this.disconnectHandlers = this.disconnectHandlers.filter((h) => h !== handler);
  }

  onAuthSuccess(handler) {
    this.authSuccessHandlers.push(handler);
    if (this.isAuthenticated) {
      handler();
    }
  }

  offAuthSuccess(handler) {
    this.authSuccessHandlers = this.authSuccessHandlers.filter((h) => h !== handler);
  }

  notifyConnect() {
    this.connectHandlers.forEach((handler) => {
      try {
        handler();
      } catch (error) {
        console.error('Run connect handler failed:', error);
      }
    });
  }

  notifyDisconnect() {
    this.disconnectHandlers.forEach((handler) => {
      try {
        handler();
      } catch (error) {
        console.error('Run disconnect handler failed:', error);
      }
    });
  }

  notifyAuthSuccess() {
    this.authSuccessHandlers.forEach((handler) => {
      try {
        handler();
      } catch (error) {
        console.error('Run auth success handler failed:', error);
      }
    });
  }

  async waitUntilReady(timeoutMs = 10000) {
    if (this.isConnected && this.isAuthenticated) return true;
    this.connect();

    const start = Date.now();
    while (Date.now() - start < timeoutMs) {
      if (this.isConnected && this.isAuthenticated) return true;
      await new Promise((resolve) => setTimeout(resolve, 100));
    }
    throw new Error('WebSocket未就绪');
  }

  async requestResponse({ sendType, payload = {}, responseType, match = null, timeoutMs = 10000 }) {
    logger.debug('ws-service', 'requestResponse:start', {
      sendType,
      responseType,
      timeoutMs
    });
    await this.waitUntilReady(timeoutMs);

    return new Promise((resolve, reject) => {
      let timeoutId = null;

      const cleanup = () => {
        if (timeoutId) clearTimeout(timeoutId);
        this.offMessage(responseType, onResponse);
        this.offMessage(MessageTypes.ERROR, onError);
      };

      const onResponse = (message) => {
        try {
          if (typeof match === 'function' && !match(message)) return;
          logger.debug('ws-service', 'requestResponse:success', {
            sendType,
            responseType
          });
          cleanup();
          resolve(message);
        } catch (err) {
          cleanup();
          reject(err);
        }
      };

      const onError = (message) => {
        logger.error('ws-service', 'requestResponse:error', {
          sendType,
          responseType,
          message: message?.message
        });
        cleanup();
        reject(new Error(message?.message || 'WebSocket请求失败'));
      };

      this.onMessage(responseType, onResponse);
      this.onMessage(MessageTypes.ERROR, onError);

      const sent = this.send(sendType, payload);
      if (!sent) {
        logger.error('ws-service', 'requestResponse:send_failed', {
          sendType,
          responseType
        });
        cleanup();
        reject(new Error('WebSocket发送失败'));
        return;
      }

      timeoutId = setTimeout(() => {
        logger.error('ws-service', 'requestResponse:timeout', {
          sendType,
          responseType,
          timeoutMs
        });
        cleanup();
        reject(new Error(`WebSocket请求超时: ${sendType}`));
      }, timeoutMs);
    });
  }

  getEmails() {
    return this.send(MessageTypes.GET_ALL_EMAILS);
  }

  checkEmails(emailIds) {
    return this.send(MessageTypes.CHECK_EMAILS, { email_ids: emailIds });
  }

  deleteEmails(emailIds) {
    return this.send(MessageTypes.DELETE_EMAILS, { email_ids: emailIds });
  }

  addEmail(emailData) {
    return this.send(MessageTypes.ADD_EMAIL, emailData);
  }

  getMailRecords(emailId) {
    return this.send(MessageTypes.GET_MAIL_RECORDS, { email_id: emailId });
  }

  importEmails(data) {
    if (typeof data === 'string') {
      return this.send(MessageTypes.IMPORT_EMAILS, { data });
    }
    if (typeof data === 'object' && data && data.data) {
      const payload = {
        data: data.data,
        mail_type: data.mailType || data.mail_type || 'outlook'
      };
      return this.send(MessageTypes.IMPORT_EMAILS, payload);
    }
    return false;
  }

  startHeartbeat() {
    this.lastHeartbeatReceived = Date.now();
    this.heartbeatInterval = setInterval(() => {
      if (!this.isConnected || !this.socket) return;
      try {
        this.socket.send(JSON.stringify({ type: 'heartbeat' }));
        this.heartbeatTimeout = setTimeout(() => {
          const elapsed = Date.now() - this.lastHeartbeatReceived;
          if (elapsed > 30000) {
            this.disconnect();
            this.connect();
          }
        }, 10000);
      } catch {
        this.clearHeartbeat();
        this.disconnect();
        this.connect();
      }
    }, 20000);
  }

  handleHeartbeatResponse() {
    this.lastHeartbeatReceived = Date.now();
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }

  clearHeartbeat() {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
    if (this.heartbeatTimeout) {
      clearTimeout(this.heartbeatTimeout);
      this.heartbeatTimeout = null;
    }
  }

  resetState() {
    this.clearHeartbeat();
    this.isConnected = false;
    this.isAuthenticated = false;
    this.authAttempted = false;

    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
  }

  reconnect() {
    this.disconnect();
    setTimeout(() => {
      const token = localStorage.getItem('token');
      if (token) {
        this.connect();
      }
    }, 500);
  }

  disconnect() {
    this.resetState();
    if (this.socket) {
      try {
        this.socket.close(1000, 'normal close');
      } catch {}
      this.socket = null;
    }
  }
}

export default new WebSocketService();
