# -*- coding: utf-8 -*-
"""
练习三 · 动态页：内容"等一等才出现"（quotes.toscrape.com）

两个练习网址：
  1) https://quotes.toscrape.com/js       —— 名言内容通过脚本在页面打开后才填充
  2) https://quotes.toscrape.com/scroll   —— 向下滚动才继续加载的"无限滚动"页面

本脚本演示三件事：
  (A) "普通方法"为什么抓不到 —— requests 拿到的是"空房间"，找不到 .quote 元素；
  (B) 内容到底从哪里来 —— 读页面里的 <script>，找到真正数据源（/js 是内嵌 JS 数组、
      /scroll 是 XHR 请求 /api/quotes?page=N）；
  (C) 用"更聪明的做法"直接拿数据接口，跳过浏览器渲染，把所有名言 + 作者抓全。
"""

import json
import re
import csv
import time
import urllib.request

BASE = "https://quotes.toscrape.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}


def fetch(url, timeout=30, tries=5):
    """带重试的 GET，返回解码后的文本。"""
    last = None
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        except Exception as e:  # noqa: BLE001 —— 网络抖动就重试
            last = e
            time.sleep(1.5)
    raise RuntimeError(f"fetch failed: {url} -> {last}")


# ----------------------------------------------------------------------
# (A) 先证明"普通方法抓不到"：requests 拿到的 HTML 里根本没有 .quote
# ----------------------------------------------------------------------
print("=" * 70)
print("(A) 普通方法为什么抓不到？—— 空房间实验")
print("=" * 70)

for path in ("/js", "/scroll"):
    html = fetch(BASE + path)
    n_quote = html.count('class="quote"')          # 真正的 .quote 元素个数
    n_text = html.count('class="text"')            # 真正的 .text 元素个数
    print(f"\n  {path:<10} 返回 HTML 长度 {len(html):>6} 字符")
    print(f"     HTML 里 <div class=\"quote\"> 出现次数 : {n_quote}")
    print(f"     HTML 里 <span class=\"text\"> 出现次数 : {n_text}")
    print(f"     => 用 BeautifulSoup 找 .quote/.text 会得到空列表（内容还没被 JS 摆进房间）")

# ----------------------------------------------------------------------
# (B) 找到内容"实际从哪里来"
# ----------------------------------------------------------------------
print("\n" + "=" * 70)
print("(B) 内容实际从哪里来？—— 读 <script> 找真相")
print("=" * 70)

# B1: /js 页面 —— 数据内嵌在 <script> 的 var data = [...] 里
html_js = fetch(BASE + "/js")
m = re.search(r"var data = (\[.*?\]);", html_js, re.S)
if m:
    embedded = json.loads(m.group(1))
    print(f"\n  [/js] 数据来源：内嵌在 <script> 标签里的 JS 数组 var data = [...]")
    print(f"         直接正则+JSON 解析出 {len(embedded)} 条名言，例如：")
    print(f"         \"{embedded[0]['text'][:40]}...\" —— {embedded[0]['author']['name']}")
else:
    print("\n  [/js] 未匹配到内嵌数组（站点结构可能已更新）")

# B2: /scroll 页面 —— JS 用 $.get('/api/quotes', {page:page}) 走 XHR
html_scroll = fetch(BASE + "/scroll")
api_hit = "/api/quotes" in html_scroll
print(f"\n  [/scroll] 数据来源：<script> 里写着 $.get('/api/quotes', {{page: page}})")
print(f"           （在浏览器 F12 → Network → XHR/Fetch 也能看到这个请求）")
print(f"           页面源码里出现 '/api/quotes' 字样 : {api_hit}")
print(f"           这就是我们要直接调用的『数据接口』，跳过渲染。")

# ----------------------------------------------------------------------
# (C) 更聪明的做法：直接请求 /api/quotes?page=N，翻页直到 has_next=False
# ----------------------------------------------------------------------
print("\n" + "=" * 70)
print("(C) 直接调数据接口，抓全所有名言 + 作者")
print("=" * 70)

quotes_all = []
page = 1
while True:
    data = json.loads(fetch(f"{BASE}/api/quotes?page={page}"))
    batch = data.get("quotes", [])
    quotes_all.extend(batch)
    print(f"  page {page:>2}: 抓到 {len(batch):>2} 条，累计 {len(quotes_all):>3} 条，has_next={data.get('has_next')}")
    if not data.get("has_next"):
        break
    page += 1
    time.sleep(0.5)   # 礼貌延时，控制请求频率（课程 3.5 底线）

# 去重（同一名言只保留一次）
seen, unique = set(), []
for q in quotes_all:
    key = (q["text"], q["author"]["name"])
    if key not in seen:
        seen.add(key)
        unique.append(q)

print(f"\n  共抓到 {len(unique)} 条名言，作者 {len({q['author']['name'] for q in unique})} 位")

# 写 CSV（名言 + 作者 + 标签）
out_csv = "quotes_toscrape.csv"
with open(out_csv, "w", newline="", encoding="utf-8-sig") as f:
    w = csv.writer(f)
    w.writerow(["author", "text", "tags"])
    for q in unique:
        w.writerow([q["author"]["name"], q["text"], "|".join(q["tags"])])

# 简单统计：发表名言最多的前 5 位作者
from collections import Counter
top = Counter(q["author"]["name"] for q in unique).most_common(5)

print("\n  ===== 发表名言最多的前 5 位作者 =====")
for name, cnt in top:
    print(f"    {name:<20} {cnt} 条")

print(f"\n  结果已保存到 {out_csv}")

# ----------------------------------------------------------------------
# 一句话讲清加载机制
# ----------------------------------------------------------------------
print("\n" + "=" * 70)
print("一句话总结（过关标准）")
print("=" * 70)
print("  浏览器会执行 JavaScript，而 requests 不会：名言不是一开始就写在 HTML 里，")
print("  而是页面打开后由 JS 从数据接口（/api/quotes?page=N，/js 则是内嵌数组）补进去的，")
print("  所以直接请求网页拿到的是'空壳'，直接请求数据接口就能拿到真正的 JSON。")
