const { defineConfig } = require('@vue/cli-service')

module.exports = defineConfig({
  transpileDependencies: true,
  devServer: {
    port: 3000,
    proxy: {
      '/api/tif': {
        target: 'http://localhost:8001',
        changeOrigin: true,
        pathRewrite: { '^/api/tif': '' }
      },
      '/api/ia': {
        target: 'http://localhost:8002',
        changeOrigin: true,
        pathRewrite: { '^/api/ia': '' }
      }
    }
  }
})
