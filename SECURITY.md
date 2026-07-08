# 安全说明

## 不要提交的内容

以下内容只能存在于部署机器本地，不能提交到 GitHub，也不要发到聊天或截图里：

- `.env`
- `.env.*`，但 `.env.example` 除外
- `data/quark_auth.json`
- `data/websites.yaml`
- `data/site-auth/`
- 飞书 `App Secret` 和 `Verification Token`
- 企业微信 Secret、Token、EncodingAESKey
- 夸克 Cookie、扫码登录态
- 资源站 Cookie、账号、Token、私有 URL
- OMDb API Key
- VPS IP、域名、证书私钥、SSH 私钥

## 公开仓库原则

- 只提交代码、测试、文档和占位示例。
- 资源站配置只提供变量名和通用示例，不提交真实地址或登录信息。
- 自定义网站配置放在 `data/websites.yaml`，该路径已被 `.gitignore` 排除。
- 配置检查命令不会打印密钥内容。

## 泄露后的处理

如果密钥、Cookie 或登录态已经进入公开仓库：

1. 立即在对应平台重置或吊销该凭证。
2. 删除部署机器上的旧登录态，例如 `data/quark_auth.json`。
3. 从 Git 历史中清除泄露文件后再重新推送。
4. 重新部署并重新扫码登录。
