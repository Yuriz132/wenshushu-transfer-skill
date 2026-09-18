#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文叔叔（wenshushu.cn）文件传输工具

用真实浏览器会话完成上传 / 下载，无需登录账号。

用法:
    python3 wss.py upload   <文件...> [--expire 1] [--remark 备注]
    python3 wss.py download <分享链接> [-o 输出目录]
    python3 wss.py info     <分享链接>

为什么用浏览器而不是直接调 HTTP API：
    文叔叔的 /ap/* 接口启用了 UA 指纹校验（user-agent error:-1/-2/-3/-4），
    必须在完整前端签名链路下才放行，裸 HTTP 客户端会被拒。
    因此这里用 Playwright 驱动真实浏览器完成全流程，稳定且与网页端行为一致。
"""

import argparse
import asyncio
import json
import os
import re
import sys

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("缺少依赖，请先执行：sudo pip3 install playwright && playwright install chromium",
          file=sys.stderr)
    sys.exit(2)

HOME = "https://www.wenshushu.cn/"
LINK_RE = re.compile(r"https://c\.wss\.ink/f/[A-Za-z0-9]+")

# 允许的过期天数（界面提供 1/2/3/7 天）
EXPIRES = {"1", "2", "3", "7"}


class WssError(Exception):
    pass


# ---------------------------------------------------------------- 上传

async def _upload(paths, expire="1", remark="", headless=True, timeout=600000):
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        raise WssError("文件不存在: %s" % ", ".join(missing))
    if not paths:
        raise WssError("未指定要上传的文件")

    abspaths = [os.path.abspath(p) for p in paths]

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN")
        page = await ctx.new_page()
        try:
            await page.goto(HOME, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(2500)

            # 勾选同意用户协议（未勾选无法发送）
            try:
                await page.check("input[type=checkbox]", timeout=4000)
            except Exception:
                pass  # 可能默认已勾选或选择器不同，继续

            # 选择文件：点击「选择文件」触发系统文件选择器
            try:
                async with page.expect_file_chooser(timeout=20000) as fc_info:
                    await page.click("text=选择文件", timeout=15000)
                chooser = await fc_info.value
                await chooser.set_files(abspaths)
            except Exception as e:
                raise WssError("选择文件失败（页面结构可能已变化）: %s" % e)

            # 等待文件进入待发送列表
            await page.wait_for_timeout(3000)

            # 可选：填写备注
            if remark:
                for sel in ("input[placeholder*='备注']", "textarea[placeholder*='备注']"):
                    try:
                        await page.fill(sel, remark, timeout=3000)
                        break
                    except Exception:
                        continue

            # 点击发送
            try:
                await page.click("text=发送", timeout=15000)
            except Exception as e:
                raise WssError("点击发送失败: %s" % e)

            # 轮询等待分享链接出现
            link = None
            deadline = asyncio.get_event_loop().time() + timeout / 1000.0
            while asyncio.get_event_loop().time() < deadline:
                txt = await page.evaluate("document.body.innerText")
                m = LINK_RE.search(txt or "")
                if m:
                    link = m.group(0)
                    break
                if "发送成功" in (txt or "") or "已全部发送成功" in (txt or ""):
                    await page.wait_for_timeout(1500)
                    continue
                await page.wait_for_timeout(1500)

            if not link:
                txt = await page.evaluate("document.body.innerText")
                raise WssError("未获取到分享链接，页面文本片段: %s"
                               % (txt or "")[:400])

            total = sum(os.path.getsize(p) for p in abspaths)
            return {
                "link": link,
                "files": [os.path.basename(p) for p in abspaths],
                "count": len(abspaths),
                "total_size": total,
                "expire": expire,
            }
        finally:
            await browser.close()


# ---------------------------------------------------------------- 下载

async def _download(link, outdir=".", headless=True, timeout=600000):
    link = (link or "").strip()
    if not link:
        raise WssError("链接为空")
    if not link.startswith("http"):
        # 允许只传取件码 / linkid
        link = "https://c.wss.ink/f/" + link

    os.makedirs(outdir, exist_ok=True)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(
            viewport={"width": 1440, "height": 900}, locale="zh-CN",
            accept_downloads=True)
        page = await ctx.new_page()
        try:
            await page.goto(link, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(3000)

            txt = await page.evaluate("document.body.innerText")
            if "不存在" in (txt or "") or "已失效" in (txt or "") or "已过期" in (txt or ""):
                raise WssError("分享已失效或过期: %s" % link)

            # 点击「下载」按钮。
            # 注意：必须用 button 限定，否则 text=下载 会误匹配
            # 页面上的「恢复下载 / 预览」等其他元素。
            saved = []
            clicked = False
            for sel in ("button:has-text('全部下载')",
                        "button:has-text('下载')"):
                try:
                    loc = page.locator(sel).first
                    if await page.locator(sel).count() == 0:
                        continue
                    async with page.expect_download(timeout=60000) as dl_info:
                        await loc.click(timeout=15000)
                    dl = await dl_info.value
                    dest = os.path.join(outdir, dl.suggested_filename or "download.bin")
                    await dl.save_as(dest)
                    saved.append(dest)
                    clicked = True
                    break
                except Exception:
                    continue

            if not clicked:
                # 回退：抓取页面上的直链并用浏览器上下文请求
                urls = await page.evaluate(
                    "Array.from(document.querySelectorAll('a[href]')).map(a=>a.href)")
                cands = [u for u in (urls or [])
                         if any(k in u for k in (".cos.", "myqcloud", "wss.zone", "wss.show", "/dl/"))]
                if not cands:
                    raise WssError("未找到可下载的文件按钮或直链，页面文本: %s"
                                   % (txt or "")[:300])
                for i, u in enumerate(cands, 1):
                    resp = await ctx.request.get(u)
                    if resp.ok:
                        name = os.path.basename(u.split("?")[0]) or ("file_%d" % i)
                        dest = os.path.join(outdir, name)
                        with open(dest, "wb") as fh:
                            fh.write(await resp.body())
                        saved.append(dest)

            # 多文件时文叔叔会打包成 zip，自动解压方便直接使用
            extracted = []
            import zipfile
            for s in list(saved):
                if s.lower().endswith(".zip"):
                    try:
                        with zipfile.ZipFile(s) as zf:
                            zf.extractall(outdir)
                            extracted.extend(
                                os.path.join(outdir, n) for n in zf.namelist()
                                if not n.endswith("/"))
                        os.remove(s)
                        saved.remove(s)
                    except Exception:
                        pass  # 解压失败则保留原始 zip
            saved.extend(extracted)

            return {"saved": saved, "link": link, "zip_extracted": extracted}
        finally:
            await browser.close()


# ---------------------------------------------------------------- 信息

async def _info(link, headless=True):
    link = (link or "").strip()
    if not link.startswith("http"):
        link = "https://c.wss.ink/f/" + link
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=headless, args=["--no-sandbox", "--disable-dev-shm-usage"])
        ctx = await browser.new_context(locale="zh-CN")
        page = await ctx.new_page()
        try:
            await page.goto(link, wait_until="networkidle", timeout=90000)
            await page.wait_for_timeout(3000)
            txt = await page.evaluate("document.body.innerText")
            return {"link": link, "text": (txt or "").strip()[:1500]}
        finally:
            await browser.close()


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="文叔叔文件传输（免登录，浏览器驱动）")
    ap.add_argument("--headful", action="store_true", help="显示浏览器窗口（调试用）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    up = sub.add_parser("upload", help="上传文件并生成分享链接")
    up.add_argument("files", nargs="+")
    up.add_argument("--expire", default="1", choices=sorted(EXPIRES))
    up.add_argument("--remark", default="")

    dn = sub.add_parser("download", help="下载分享链接中的文件")
    dn.add_argument("link")
    dn.add_argument("-o", "--outdir", default=".")

    inf = sub.add_parser("info", help="查看分享链接信息")
    inf.add_argument("link")

    args = ap.parse_args()
    headless = not args.headful

    if args.cmd == "upload":
        print("正在上传 %d 个文件 ..." % len(args.files))
        r = asyncio.run(_upload(args.files, expire=args.expire,
                                remark=args.remark, headless=headless))
        print()
        print("上传成功！")
        print("分享链接: %s" % r["link"])
        print("文件: %s" % ", ".join(r["files"]))
        print("总大小: %.2f MB" % (r["total_size"] / 1048576.0))
        print("WSS_RESULT " + json.dumps(r, ensure_ascii=False))

    elif args.cmd == "download":
        print("正在下载: %s" % args.link)
        r = asyncio.run(_download(args.link, args.outdir, headless=headless))
        print()
        print("完成，共 %d 个文件" % len(r["saved"]))
        for s in r["saved"]:
            print("  %s" % os.path.abspath(s))
        print("WSS_RESULT " + json.dumps(r, ensure_ascii=False))

    elif args.cmd == "info":
        r = asyncio.run(_info(args.link, headless=headless))
        print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except WssError as e:
        print("错误: %s" % e, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)
