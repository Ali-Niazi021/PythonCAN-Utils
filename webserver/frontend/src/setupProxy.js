const { createProxyMiddleware } = require('http-proxy-middleware');

module.exports = function setupProxy(app) {
  app.use(
    '/api/ws',
    createProxyMiddleware({
      target: 'http://127.0.0.1:8000',
      ws: true,
      changeOrigin: true,
    })
  );
};