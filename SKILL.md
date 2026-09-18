---
name: wenshushu-transfer
description: "文叔叔网盘文件传输 - 通过 wenshushu.cn 在沙箱与用户之间中转文件。上传沙箱文件生成分享链接发给用户，或接收用户给的链接自动下载。关键词：文叔叔、wenshushu、传文件、分享链接、上传文件、下载文件、大文件中转、发给用户"
version: "1.0.0"
author: "CodeBuddy AI"
created: "2026-09-18"
updated: "2026-09-18"
---

# 文叔叔文件传输（wenshushu-transfer）

> **目标**：在**沙箱与用户之间**建立文件双向通道。
> 沙箱内的文件 → 上传到文叔叔 → 把分享链接发给用户；
> 用户给的文叔叔链接 → 自动下载到沙箱。

## When to Use

**当出现以下任意场景时触发：**

- 用户要求「把文件/这个文件夹发给我」「生成下载链接」「给我个链接我下载」
- 沙箱产出了交付物（报告、图片、安装包、大文件），但需要**经外部通道**交给用户
- 用户说「我上传好了，链接是 https://c.wss.ink/f/xxx」「从文叔叔下载」「用取件码取文件」
- 用户**明确点名**「文叔叔 / wenshushu」

## When NOT to Use

- 用户只是要**在沙箱里**查看文件 → 直接用 `present_files`
- 用户要的是**可在线预览的网页/HTML 应用** → 用「发布为应用」skill
- 用户要的是**长期托管的代码仓库** → 用 github / gongfeng connector
- 文件已经很方便地在 `/workspace` 里 → 优先 `present_files`，不要多绕一步

## 核心约束（重要）

| 项目 | 说明 |
|------|------|
| **免登录** | 使用匿名会话，不需要账号密码 |
| **单文件上限** | 5 GB（匿名 3 GB 左右，保守按 3 GB 处理） |
| **有效期** | 可选 1 / 2 / 3 / 7 天，**默认 1 天**，过期自动销毁 |
| **上传次数** | 匿名用户有配额限制，连续大量上传可能被限流 |
| **链接格式** | `https://c.wss.ink/f/<linkid>` |
| **技术实现** | Playwright 驱动真实浏览器（见下方「为什么不用纯 HTTP」） |

### 为什么不用纯 HTTP API

文叔叔的 `/ap/*` 接口启用了 **UA 指纹校验**，直接构造 HTTP 请求会被拒绝：

```
{"code":-1,"message":"user-agent error:-1"}
{"code":-2,"message":"user-agent error:-2"}   # 即使在浏览器内 fetch 也会被拒
```

必须走完整的前端签名链路。因此本 skill 用 **Playwright 驱动真实浏览器**完成全流程，
行为与用户在网页上手动操作完全一致，稳定可靠。

## 使用方式

脚本位置：`scripts/wss.py`

### 1. 上传文件（沙箱 → 用户）

```bash
# 单个文件，默认 1 天有效
python3 scripts/wss.py upload /workspace/report.pdf

# 多个文件（会自动打包成 zip，下载时自动解压）
python3 scripts/wss.py upload /workspace/a.txt /workspace/b.png

# 指定有效期 7 天
python3 scripts/wss.py upload /workspace/big.zip --expire 7
```

**输出示例：**

```
上传成功！
分享链接: https://c.wss.ink/f/kwmhh79vodh
文件: testA.bin
总大小: 0.08 MB
WSS_RESULT {"link": "https://c.wss.ink/f/kwmhh79vodh", ...}
```

拿到链接后，**直接把链接发给用户**即可（不要只贴 WSS_RESULT 那一行）。

### 2. 下载文件（用户 → 沙箱）

```bash
# 用户给了分享链接
python3 scripts/wss.py download "https://c.wss.ink/f/kwmhh79vodh" -o /workspace/incoming

# 只给取件码也可以
python3 scripts/wss.py download kwmhh79vodh -o /workspace/incoming
```

- 输出目录会自动创建
- 若下载结果是 zip，**会自动解压**并把原 zip 删除
- 用 `md5sum` 与用户核对可确认完整性

### 3. 查看链接信息

```bash
python3 scripts/wss.py info "https://c.wss.ink/f/kwmhh79vodh"
```

用于下载前确认文件列表、大小、是否已过期。

## 标准工作流

### 场景 A：把沙箱产物发给用户

```
1. 在 /workspace 生成好交付物
2. 执行 upload，拿到分享链接
3. 把链接发给用户，并说明：
   - 链接
   - 包含哪些文件
   - 有效期（提醒「过期自动销毁，请及时下载」）
```

### 场景 B：接收用户文件

```
1. 从用户消息中提取链接 / 取件码
2. （可选）先 info 确认内容
3. 执行 download -o /workspace/incoming
4. 处理文件；如需给用户看，用 present_files
```

## 依赖准备

首次使用若报缺依赖：

```bash
sudo pip3 install playwright
playwright install chromium
```

沙箱环境通常已预装，无需重复安装。

## 注意事项

- **有效期要主动提醒**：默认只有 1 天，过期链接自动销毁，务必告知用户尽快下载
- **谨慎处理敏感文件**：链接是公开的（带取件码的除外），不要上传含密码/密钥的文件
- **配额有限**：不要在同一轮里反复重复上传同一文件
- **文件名**：含中文/空格的文件名可以正常处理，无需改名
- **失败重试**：上传超时可重跑一次；若持续失败，可能是被限流，稍后再试
- **不要虚构链接**：链接必须来自脚本真实输出，绝不臆造

## 排障

| 现象 | 原因与处理 |
|------|-----------|
| `未获取到分享链接` | 页面结构变化或网络慢，重跑一次；必要时加 `--headful` 观察 |
| `选择文件失败` | 首屏未加载完，重跑；确认网络可达 wenshushu.cn |
| `分享已失效或过期` | 链接过期，请用户重新上传 |
| 上传很慢/中断 | 大文件正常现象，重跑或改用 `--expire` 拉长有效期后分卷 |
| 报缺 playwright | 按上文「依赖准备」安装 |

调试时可加 `--headful` 参数显示浏览器窗口。
