// 学在华邮件助手环境配置
// 此文件被前端 index.html 引用，用于配置 API/WS 地址
(function () {
  var hostname = window.location.hostname || 'localhost';

  // 若外部已注入配置，则不覆盖；否则按当前主机名直连后端端口
  if (!window.API_URL) {
    window.API_URL = 'http://' + hostname + ':5000';
  }
  if (!window.WS_URL) {
    window.WS_URL = 'ws://' + hostname + ':8765';
  }

  console.log('env-config.js已加载，API_URL:', window.API_URL, 'WS_URL:', window.WS_URL);
})();
