# 03｜资源 API 接口规范

## 一、用途

资源 API 仅在自己的夸克网盘中没有目标影片时调用。它必须由你维护，或是你有权使用的合法目录服务。

## 二、配置

```env
# 🔴【使用 API 时需要你填写】
PROVIDER_API_URLS=https://media.example.com/api/search

# 🟡【API 需要鉴权时填写】
PROVIDER_API_TOKEN=
```

多个 API：

```env
PROVIDER_API_URLS=https://a.example.com/search;https://b.example.com/search
```

## 三、请求契约

```http
GET 【PROVIDER_API_URLS】?q=星际穿越
Accept: application/json
Authorization: Bearer 【PROVIDER_API_TOKEN】
```

Token 为空时不会发送 Authorization 请求头。

建议：

- 响应时间不超过 20 秒；
- 使用 HTTPS；
- 对机器人服务器 IP 做访问限制；
- 设置鉴权、限流和审计；
- 不在错误信息中返回内部密钥。

## 四、响应契约

支持两种顶层格式。

格式 1：

```json
{
  "results": [
    {
      "title": "Interstellar 2014 2160p REMUX HDR Atmos 中英字幕",
      "share_url": "https://pan.quark.cn/s/xxxx",
      "quality": "2160p REMUX HDR Atmos",
      "size": "70GB",
      "source": "my-catalog"
    }
  ]
}
```

格式 2：

```json
[
  {
    "title": "Interstellar 2014 1080p WEB-DL 中字",
    "share_url": "https://pan.quark.cn/s/yyyy",
    "quality": "1080p WEB-DL",
    "size": "12GB"
  }
]
```

## 五、字段定义

| 字段 | 必填 | 说明 |
|---|---:|---|
| `title` | 是 | 完整资源名称，评分会读取其中的画质词 |
| `share_url` | 是 | 必须是 `https://pan.quark.cn/s/...` |
| `quality` | 建议 | 分辨率、片源、HDR、音轨等 |
| `size` | 可选 | 如 `25GB` |
| `source` | 可选 | 资源目录名称 |

## 六、过滤规则

以下结果会被丢弃：

- 非字典对象；
- 没有分享链接；
- 非夸克分享链接；
- 磁力链接；
- BT/Torrent 链接；
- 重复分享链接。

## 七、评分测试样例

API 可同时返回：

```json
{
  "results": [
    {
      "title": "影片 1080p WEB-DL 中字",
      "share_url": "https://pan.quark.cn/s/aaa",
      "quality": "1080p WEB-DL",
      "size": "10GB"
    },
    {
      "title": "影片 2160p REMUX HDR Atmos 中英字幕",
      "share_url": "https://pan.quark.cn/s/bbb",
      "quality": "2160p REMUX HDR Atmos",
      "size": "60GB"
    }
  ]
}
```

机器人应选择第二个候选。
