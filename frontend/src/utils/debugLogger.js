let seq = 0;

const getRuntimeFlag = () => {
  try {
    if (typeof window !== 'undefined' && typeof window.__FIREMAIL_DEBUG__ !== 'undefined') {
      return Boolean(window.__FIREMAIL_DEBUG__);
    }
    const value = localStorage.getItem('FIREMAIL_DEBUG_LOG');
    if (value === null) return true;
    return value !== '0' && value !== 'false';
  } catch {
    return true;
  }
};

const write = (level, scope, message, payload) => {
  if (!getRuntimeFlag()) return;
  const id = ++seq;
  const timestamp = new Date().toISOString();
  const prefix = `[FM][${id}][${timestamp}][${scope}] ${message}`;

  if (typeof payload === 'undefined') {
    console[level](prefix);
  } else {
    console[level](prefix, payload);
  }

  try {
    if (typeof window !== 'undefined') {
      if (!Array.isArray(window.__firemailLogs)) {
        window.__firemailLogs = [];
      }
      window.__firemailLogs.push({
        id,
        level,
        scope,
        message,
        payload,
        timestamp
      });
      if (window.__firemailLogs.length > 800) {
        window.__firemailLogs.splice(0, window.__firemailLogs.length - 800);
      }
    }
  } catch {
    // ignore
  }
};

const logger = {
  debug(scope, message, payload) {
    write('log', scope, message, payload);
  },
  info(scope, message, payload) {
    write('info', scope, message, payload);
  },
  warn(scope, message, payload) {
    write('warn', scope, message, payload);
  },
  error(scope, message, payload) {
    write('error', scope, message, payload);
  }
};

export default logger;
