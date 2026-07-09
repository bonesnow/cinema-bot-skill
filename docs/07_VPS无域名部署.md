# 07｜只有 VPS、没有域名时部署

推荐方案：**DuckDNS 免费子域名 + Caddy 自动 HTTPS**。

你不需要购买域名。DuckDNS 会给你一个：

```text
🔴【需要你填写】你的名字.duckdns.org
```

Caddy 会为该地址自动申请和续期 HTTPS 证书。

---

## 一、VPS 必须满足

```text
🔴 VPS 有公网 IPv4
🔴 防火墙放行 TCP 80
🔴 防火墙放行 TCP 443
🟡 建议同时放行 UDP 443，用于 HTTP/3；不放也能使用 HTTPS
```

应用的 8000 端口仍只绑定本机，不直接暴露公网。

---

## 二、申请 DuckDNS 免费地址

打开 DuckDNS，登录后创建一个子域名，例如：

```text
cinema-demo.duckdns.org
```

记录两项内容：

```text
🔴【需要你填写】DUCKDNS_SUBDOMAIN=cinema-demo
🔴【需要你填写】DUCKDNS_TOKEN=DuckDNS 页面显示的 token
```

注意：`DUCKDNS_SUBDOMAIN` 只填写前半段，不要填写 `.duckdns.org`。

---

## 三、填写 `.env`

```env
# 🔴【需要你填写】DuckDNS 子域名，不带 .duckdns.org
DUCKDNS_SUBDOMAIN=__FILL_DUCKDNS_SUBDOMAIN__

# 🔴【需要你填写】DuckDNS Token
DUCKDNS_TOKEN=__FILL_DUCKDNS_TOKEN__

# 🔴【需要你填写】完整公网主机名
PUBLIC_HOST=__FILL_DUCKDNS_SUBDOMAIN__.duckdns.org
```

例如：

```env
DUCKDNS_SUBDOMAIN=cinema-demo
DUCKDNS_TOKEN=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PUBLIC_HOST=cinema-demo.duckdns.org
```

---

## 四、一键部署

推荐直接执行：

```bash
./scripts/deploy_vps.sh
```

脚本会检查 Docker、读取 `.env`、构建镜像、启动服务，并输出健康检查地址和飞书回调地址。

## 五、手动检查 VPS 配置

```bash
chmod +x scripts/vps_check.sh
./scripts/vps_check.sh
```

成功后会显示：

```text
飞书回调地址：https://你的名字.duckdns.org/webhooks/feishu
健康检查地址：https://你的名字.duckdns.org/healthz
```

---

## 六、开放 VPS 防火墙

Ubuntu/UFW：

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw allow 443/udp
sudo ufw enable
sudo ufw status
```

还需要在 VPS 服务商的安全组中放行：

```text
TCP 80
TCP 443
UDP 443（可选）
```

---

## 七、手动启动完整服务

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml up -d --build
```

查看状态：

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml ps
docker compose -f docker-compose.yml -f docker-compose.vps.yml logs --tail=100 duckdns
docker compose -f docker-compose.yml -f docker-compose.vps.yml logs --tail=100 caddy
```

验证 HTTPS：

```bash
curl "https://${PUBLIC_HOST}/healthz"
```

也可以直接在浏览器打开：

```text
https://🔴【你的 DuckDNS 地址】/healthz
```

---

## 八、填写飞书回调

飞书开放平台的事件回调地址填写：

```text
https://🔴【你的 DuckDNS 地址】/webhooks/feishu
```

例如：

```text
https://cinema-demo.duckdns.org/webhooks/feishu
```

---

## 九、扫码登录夸克

启动完成后，给飞书机器人发送：

```text
夸克登录
```

机器人返回二维码后，用夸克 App 扫码确认。

---

## 十、常见问题

### HTTPS 证书申请失败

检查：

```bash
getent hosts "$PUBLIC_HOST"
sudo ss -lntup | grep -E ':80|:443'
docker compose -f docker-compose.yml -f docker-compose.vps.yml logs caddy
```

确认 DuckDNS 已指向当前 VPS 公网 IP，并且 80、443 没有被其他程序占用。

### DuckDNS 地址没有更新

查看：

```bash
docker compose -f docker-compose.yml -f docker-compose.vps.yml logs duckdns
```

正常结果应包含：

```text
DuckDNS update: OK
```

### VPS 有固定公网 IP，还需要 DuckDNS 更新服务吗

建议保留。它每 5 分钟同步一次，不会影响固定 IP，也能在 VPS IP 以后变化时自动恢复。

---

## 临时测试方案

只想快速测试飞书回调，可以使用 Cloudflare Quick Tunnel：

```bash
cloudflared tunnel --url http://127.0.0.1:8000
```

它会生成随机的 `trycloudflare.com` HTTPS 地址。该地址重启后通常会变化，只适合测试，不适合作为长期飞书回调。
