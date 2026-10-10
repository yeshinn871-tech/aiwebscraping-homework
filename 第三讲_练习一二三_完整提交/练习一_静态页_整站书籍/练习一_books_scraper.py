# -*- coding: utf-8 -*-
"""
第三讲 · 练习项目一：静态页 —— 把整站内容整理成表格
站点：https://books.toscrape.com  （合法的爬虫教学沙盒站）
需提取字段：书名、价格、评分、库存、详情页链接
过关标准：抓取条数与站点总书量（约 1000 条）一致，表格无乱码、无缺失单元格。
"""

import time
import re
import urllib.request
from urllib.parse import urljoin
import pandas as pd
from lxml import html as lxml_html

BASE = "https://books.toscrape.com"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

# 评分等级 → 数字（One..Five -> 1..5）
RATING_MAP = {"One": 1, "Two": 2, "Three": 3, "Four": 4, "Five": 5}


def fetch(url: str) -> str:
    """礼貌抓取：带 UA，且每两次请求间延时，避免压垮站点。

    带重试：网络抖动（如 VPN 下 SSL 偶发断开）时自动重试，避免中途失败。
    """
    req = urllib.request.Request(url, headers=HEADERS)
    last = None
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read().decode("utf-8")
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise last


def parse_page(page_html: str, page_url: str) -> list:
    """从一页 HTML 中解析出该页全部书籍的 5 个字段。

    page_url：当前页面的完整地址，用于把详情页的相对链接正确拼接成绝对地址。
    （注意：首页 /index.html 里的链接是 catalogue/...，而 /catalogue/page-N.html
    里的链接是相对 /catalogue/ 的裸文件名，必须用 urljoin 按页面基准拼接。）
    """
    tree = lxml_html.fromstring(page_html)
    rows = []
    for pod in tree.xpath('//article[@class="product_pod"]'):
        # 书名：<h3><a title="完整书名">…</a></h3>，title 属性里是完整书名（含省略号截断）
        a_tag = pod.xpath(".//h3/a")[0]
        title = (a_tag.get("title") or "").strip()

        # 价格：<p class="price_color">£51.77</p>
        price_tag = pod.xpath('.//p[@class="price_color"]')[0]
        price_raw = price_tag.text_content().strip()
        price = float(re.sub(r"[^0-9.]", "", price_raw))  # 去掉 £ 等符号再转数字

        # 评分：<p class="star-rating Three">
        rating_tag = pod.xpath('.//p[contains(@class,"star-rating")]')[0]
        rating_cls = rating_tag.get("class", "")
        rating = None
        for cls in rating_cls.split():
            if cls in RATING_MAP:
                rating = RATING_MAP[cls]

        # 库存：<p class="instock availability">In stock</p>
        stock_tag = pod.xpath('.//p[contains(@class,"instock") and contains(@class,"availability")]')[0]
        stock = stock_tag.text_content().strip()

        # 详情页链接：相对路径 -> 绝对地址（按当前页 URL 拼接，正确处理相对链接）
        href = a_tag.get("href", "")
        detail_url = urljoin(page_url, href)

        rows.append({
            "书名": title,
            "价格": price,
            "评分": rating,
            "库存": stock,
            "详情页链接": detail_url,
        })
    return rows


def find_page_count(home_html: str) -> int:
    """从首页分页区解析总页数（Page 1 of 50 -> 50），避免写死。"""
    m = re.search(r"Page\s+\d+\s+of\s+(\d+)", home_html)
    return int(m.group(1)) if m else 1


def main():
    print("抓取首页，识别总页数…")
    home = fetch(BASE + "/index.html")
    total_pages = find_page_count(home)
    print(f"共 {total_pages} 页")

    all_rows = []
    for p in range(1, total_pages + 1):
        url = f"{BASE}/catalogue/page-{p}.html"
        html = fetch(url)
        rows = parse_page(html, url)
        all_rows.extend(rows)
        print(f"  page-{p}.html  -> {len(rows)} 条（累计 {len(all_rows)}）")
        time.sleep(0.3)  # 控制请求频率

    df = pd.DataFrame(all_rows)

    # —— 过关自检 ——
    total = len(df)
    missing = int(df.isna().sum().sum()) + int((df.astype(str) == "").sum().sum())
    print("\n========== 过关自检 ==========")
    print(f"抓取条数：{total} 条")
    print(f"缺失/空白单元格：{missing} 个")
    print(f"评分取值范围：{sorted(df['评分'].unique())}")
    print(f"价格范围：{df['价格'].min()} ~ {df['价格'].max()}")

    # 乱码检查：中文环境常见的乱码字符，若出现说明编码处理有误
    garbled = df.astype(str).apply(lambda s: s.str.contains("�|锟|烫烫|Ã|â€|æ»", regex=True)).any().any()
    print(f"是否存在乱码：{'是（有问题！）' if garbled else '否'}")

    # 输出表格
    csv_path = "books_结果.csv"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")  # utf-8-sig 便于 Excel 直接打开不乱码
    print(f"\n已保存：{csv_path}（{total} 行 × {len(df.columns)} 列）")

    if total == 1000 and missing == 0 and not garbled:
        print("✅ 达标：条数与站点总书量一致、无缺失、无乱码。")
    else:
        print("⚠️ 未达标，请检查上述自检项。")
    print(df.head(10).to_string())


if __name__ == "__main__":
    main()
