import { createApp } from 'vue';
import { createPinia } from 'pinia';
import ElementPlus from 'element-plus';
import 'element-plus/dist/index.css';
import zhCn from 'element-plus/es/locale/lang/zh-cn';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';

import App from './App.vue';
import router from './router';
import store from './store';
import './assets/main.css';
import WebSocketService from './services/websocket';
import logger from './utils/debugLogger';

const app = createApp(App);

window.addEventListener('error', (event) => {
  logger.error('app', 'window:error', {
    message: event?.message,
    filename: event?.filename,
    lineno: event?.lineno,
    colno: event?.colno
  });
});

window.addEventListener('unhandledrejection', (event) => {
  logger.error('app', 'window:unhandledrejection', {
    reason: String(event?.reason?.message || event?.reason || '')
  });
});

app.config.errorHandler = (err, vm, info) => {
  logger.error('app', 'vue:errorHandler', {
    info,
    message: err?.message
  });
  console.error('Vue global error:', err, info);
};

app.config.globalProperties.$webSocket = WebSocketService;

WebSocketService.onConnect(() => {
  logger.debug('ws', 'connected');
  store.commit('SET_WEBSOCKET_CONNECTED', true);
});

WebSocketService.onDisconnect(() => {
  logger.warn('ws', 'disconnected');
  store.commit('SET_WEBSOCKET_CONNECTED', false);
});

WebSocketService.onAuthSuccess(() => {
  logger.debug('ws', 'auth_success');
});

for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

app.use(createPinia());
app.use(router);
app.use(store);
app.use(ElementPlus, { locale: zhCn });

const bootstrap = async () => {
  try {
    await store.dispatch('auth/getConfig');
    logger.debug('app', 'bootstrap:config_loaded');
  } catch (error) {
    logger.error('app', 'bootstrap:getConfig_error', { message: error?.message });
  }

  app.mount('#app');

  if (store.getters['auth/isAuthenticated']) {
    logger.debug('app', 'bootstrap:connect_ws');
    WebSocketService.connect();
  } else {
    logger.debug('app', 'bootstrap:skip_ws_connect');
  }

  store.watch(
    (state, getters) => getters['auth/isAuthenticated'],
    (isAuthenticated) => {
      logger.debug('app', 'auth:changed', { isAuthenticated });
      if (isAuthenticated) {
        WebSocketService.connect();
      } else {
        WebSocketService.disconnect();
      }
    }
  );
};

bootstrap();
