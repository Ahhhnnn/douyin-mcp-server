# 抖音文案提取 API 文档

## 环境配置

| 环境 | Base URL | 说明 |
|------|----------|------|
| **本地开发** | `http://localhost:8080` | 开发调试使用 |
| **生产环境** | `https://your-domain.com` | 需配置 HTTPS 和域名白名单 |

---

## 接口1：获取视频信息

`POST /api/video/info`

### 请求参数

```json
{
  "url": "抖音分享链接"
}
```

### 响应

```json
{
  "success": true,
  "video_id": "视频ID",
  "title": "视频标题",
  "download_url": "无水印下载链接"
}
```

### 小程序调用示例

```javascript
wx.request({
  url: `${API_BASE_URL}/api/video/info`,
  method: 'POST',
  data: { url: 'https://v.douyin.com/xxxxx/' },
  success(res) {
    if (res.data.success) {
      console.log('标题:', res.data.title);
      console.log('下载链接:', res.data.download_url);
    }
  }
})
```

---

## 接口2：提取视频文案

`POST /api/video/extract`

### 请求参数

```json
{
  "url": "抖音分享链接"
}
```

### 响应

```json
{
  "success": true,
  "video_id": "视频ID",
  "title": "视频标题",
  "text": "提取的文案内容",
  "download_url": "无水印下载链接"
}
```

### 小程序调用示例

```javascript
wx.request({
  url: `${API_BASE_URL}/api/video/extract`,
  method: 'POST',
  data: { url: 'https://v.douyin.com/xxxxx/' },
  success(res) {
    if (res.data.success) {
      console.log('文案:', res.data.text);
    } else {
      wx.showToast({ title: res.data.error, icon: 'none' });
    }
  }
})
```

---

## 错误处理

所有接口通过 `success` 字段判断成功/失败：

```json
// 失败响应
{
  "success": false,
  "error": "错误信息"
}
```

### 常见错误

| 错误信息 | 原因 |
|----------|------|
| `请先配置 API Key` | 服务端未配置 |
| `无法解析视频链接` | 链接无效 |
| `文案提取失败` | API 调用失败 |

---

## 小程序配置

### 1. 域名白名单

在微信公众平台配置：

```
request合法域名：https://your-domain.com
```

### 2. 封装调用

```javascript
// config.js
const ENV = 'production'; // 'development' | 'production'

const CONFIG = {
  development: 'http://localhost:8080',
  production: 'https://your-domain.com'
};

module.exports = {
  API_BASE_URL: CONFIG[ENV]
};

// api.js
const { API_BASE_URL } = require('./config');

function getVideoInfo(url) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}/api/video/info`,
      method: 'POST',
      data: { url },
      success: resolve,
      fail: reject
    });
  });
}

function extractText(url) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: `${API_BASE_URL}/api/video/extract`,
      method: 'POST',
      data: { url },
      success: resolve,
      fail: reject
    });
  });
}

module.exports = { getVideoInfo, extractText };
```

### 3. 使用示例

```javascript
const { getVideoInfo, extractText } = require('./api');

// 获取视频信息
async function handleGetInfo() {
  wx.showLoading({ title: '加载中...' });
  try {
    const res = await getVideoInfo('https://v.douyin.com/xxxxx/');
    if (res.data.success) {
      this.setData({ videoInfo: res.data });
    }
  } catch (e) {
    wx.showToast({ title: '请求失败', icon: 'none' });
  } finally {
    wx.hideLoading();
  }
}

// 提取文案
async function handleExtract() {
  wx.showLoading({ title: '识别中...' });
  try {
    const res = await extractText('https://v.douyin.com/xxxxx/');
    if (res.data.success) {
      this.setData({ text: res.data.text });
    } else {
      wx.showToast({ title: res.data.error, icon: 'none' });
    }
  } catch (e) {
    wx.showToast({ title: '请求失败', icon: 'none' });
  } finally {
    wx.hideLoading();
  }
}
```

---

## 注意事项

- ⏱️ 文案提取需要 10-30 秒，建议显示加载提示
- 🔒 生产环境必须使用 HTTPS
- 📱 需在微信公众平台配置服务器域名白名单
- 💰 API Key 在服务端配置，前端无需传递
