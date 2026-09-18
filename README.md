# wenshushu-transfer-skill

给 CodeBuddy / AI Agent 用的**文叔叔（wenshushu.cn）文件传输技能**。

让 AI 能在**沙箱与用户之间**双向中转文件：

- **上传** —— 把沙箱里的文件传到文叔叔，生成分享链接发给你
- **下载** —— 你给一个文叔叔链接/取件码，AI 自动下载到沙箱

无需登录、无需账号，即装即用。

## 核心行为：你说「发给我」，AI 就给链接

装上这个技能后，只要你说出**任何索取文件的话**，AI 会自动上传并返回下载链接：

| 你说 | AI 的动作 |
|------|----------|
| 「把 xxx 发给我」 | 上传 xxx → 返回分享链接 |
| 「发我一份」 | 上传对应文件 → 返回分享链接 |
| 「传给我」「给我」「发过来」 | 同上 |
| 「给我个下载链接」 | 同上 |
| 「把刚才那些都发我」 | 打包上传 → 返回分享链接 |

AI 的回复会包含三样东西：**链接**、**文件列表**、**有效期提醒**。

## 功能

| 命令 | 作用 |
|------|------|
| `upload <文件...>` | 上传文件，返回 `https://c.wss.ink/f/xxx` 分享链接 |
| `download <链接>` | 下载分享链接里的全部文件（自动解压 zip） |
| `info <链接>` | 查看分享的文件列表、大小、是否过期 |

## 安装

### 1. 添加技能

在 CodeBuddy 里用「从 GitHub 添加技能」，填入本仓库地址：

```
https://github.com/Yuriz132/wenshushu-transfer-skill
```

### 2. 安装依赖

本技能用 **Playwright 驱动真实浏览器**完成任务，需要先装依赖：

```bash
sudo pip3 install playwright
playwright install chromium
```

> **为什么必须用浏览器？** 见下文「技术说明」。

## 使用

```bash
S=scripts/wss.py

# 上传单个文件（默认 1 天有效）
python3 $S upload /workspace/report.pdf

# 上传多个文件（自动打包，下载时自动解压）
python3 $S upload /workspace/a.txt /workspace/b.png

# 指定有效期 7 天
python3 $S upload /workspace/big.zip --expire 7

# 下载（链接或取件码都行）
python3 $S download "https://c.wss.ink/f/kwmhh79vodh" -o /workspace/incoming
python3 $S download kwmhh79vodh -o /workspace/incoming

# 查看链接信息
python3 $S info "https://c.wss.ink/f/kwmhh79vodh"
```

脚本会输出一行机器可读结果，方便上层程序解析：

```
WSS_RESULT {"link": "https://c.wss.ink/f/kwmhh79vodh", "files": ["a.txt"], "count": 1, "total_size": 87654, "expire": "1"}
```

## 限制

| 项目 | 说明 |
|------|------|
| 单文件上限 | 约 3 GB（匿名） |
| 有效期 | 1 / 2 / 3 / 7 天，**默认 1 天，过期自动销毁** |
| 上传配额 | 匿名用户有限额，连续大批量上传可能被限流 |
| 链接可见性 | **公开链接，无需密码即可下载** |

> ⚠️ **不要用它传密钥、密码等敏感文件** —— 分享链接是公开的。

## 技术说明

### 为什么不用 HTTP API

文叔叔的 `/ap/*` 接口启用了 **UA 指纹校验**，直接构造 HTTP 请求会被拒绝：

```json
{"code":-1,"message":"user-agent error:-1"}
{"code":-2,"message":"user-agent error:-2"}
```

实测补齐 `prod`、`req-time`、`sec-ch-ua` 等全套请求头后，错误码只是从 `-1` 递进到 `-3`、`-4`；
**即使在真实浏览器上下文内用 `fetch` 调用同样被拒**（`-2`）。必须走完整前端签名链路。

因此本技能用 Playwright 驱动真实浏览器完成全流程，行为与手动操作网页完全一致。

### 完整流程（逆向所得）

上传经过以下接口，全部在浏览器会话内自动完成：

```
task/addsend         创建发送任务  → linkid / boxid / preid
uploadv2/getupid     申请上传 ID
uploadv2/fast        秒传探测（命中则跳过真实上传）
uploadv2/psurl       申请腾讯 COS 预签名 PUT 地址
PUT <cos-url>        上传字节
uploadv2/complete    登记文件
task/copysend        生成公开分享链接
```

## 已验证

2026-09-18 实测通过：

- 单文件 / 多文件上传 ✅
- 中文文件名 ✅
- 下载往返 MD5 逐字节一致 ✅
- 多文件自动解压 ✅

```
原始  中文测试.txt  c4f51ee1170a78df194be3330817146a
下载  中文测试.txt  c4f51ee1170a78df194be3330817146a
原始  payload.bin   9d3b715f967a84e7b500706c69ed3336
下载  payload.bin   9d3b715f967a84e7b500706c69ed3336
```

## 排障

| 现象 | 处理 |
|------|------|
| `未获取到分享链接` | 页面结构变化或网络慢，重跑一次；加 `--headful` 观察 |
| `选择文件失败` | 首屏未加载完，重跑；确认能访问 wenshushu.cn |
| `分享已失效或过期` | 链接过期，需重新上传 |
| 报缺 playwright | 按上文「安装依赖」处理 |

调试时加 `--headful` 可显示浏览器窗口。

## License

MIT
