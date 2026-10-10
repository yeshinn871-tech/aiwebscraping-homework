# -*- coding: utf-8 -*-
"""
练习二 · 脏数据清洗 + 入库 + 分析（Wikipedia 各国人口）

练习网址（任选其一，本脚本优先英文、失败回退中文）：
  ‣ https://en.wikipedia.org/wiki/List_of_sovereign_states_by_population
  ‣ https://zh.wikipedia.org/wiki/各国人口列表

核心思想：重点在"洗"不在"抓"。原始表格里的数字都只是"像数字的文字"：
  1. 千分位逗号        "1,429,404,000"
  2. 脚注              "UN projection[1][3]"
  3. 不可见空格        \\u00a0（不换行空格）、\\u202f（窄不换行空格）
  4. 数字中混杂的单位  "17.3%"（百分比符号）
  5. 缺失值            ""、"—"、空单元格
  不清洗干净，这些列就无法参与计算。

本脚本流程：抓取（lxml 取原始单元格文本，保留脏数据）→ 清洗（文字/整数/小数
分开）→ 按类型写入 SQLite → 读取分析（排序 / 求和 / 取前十 / 缺失值）。

注意：本机无法直连 Wikipedia 时会回退到内置"模拟脏数据样本"（格式与真实表格
一致），保证整条链路可运行、可验证；连上 VPN 后自动走真实抓取（约 240 行）。
"""

import io
import re
import sqlite3
import urllib.request

# ----------------------------------------------------------------------
# 一、数据获取
# ----------------------------------------------------------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}


def _fetch(url, timeout=20, tries=2):
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            return urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8")
        except Exception:
            continue
    return None


def fetch_from_wikipedia():
    """真实抓取 Wikipedia 表格，返回 [(国家原始串, 人口原始串, 占比原始串), ...]。

    关键：用 lxml 提取"原始单元格文本"，保留千分位逗号、脚注、% 单位等脏数据，
    而不是用 pd.read_html（它会偷偷把数字洗成 float，失去练习意义）。
    """
    import lxml.html

    urls = [
        "https://en.wikipedia.org/wiki/List_of_sovereign_states_by_population",
        "https://zh.wikipedia.org/wiki/%E5%90%84%E5%9B%BD%E4%BA%BA%E5%8F%A3%E5%88%97%E8%A1%A8",
    ]
    for url in urls:
        html = _fetch(url)
        if not html:
            continue
        try:
            doc = lxml.html.fromstring(html)
        except Exception:
            continue

        # 找最大那张 wikitable（主数据表约 240+ 行）
        best = None
        for tbl in doc.xpath('//table[contains(@class, "wikitable")]'):
            n = len(tbl.xpath('.//tr'))
            if best is None or n > best[0]:
                best = (n, tbl)
        if not best:
            continue
        tbl = best[1]
        trs = tbl.xpath('.//tr')
        if len(trs) < 50:               # 主表一定很大，太小说明找错了
            continue

        # 表头 -> 定位 国家/人口/占比 三列的序号
        headers = [c.text_content().strip() for c in trs[0].xpath('.//th')]
        if not headers:
            headers = [c.text_content().strip() for c in trs[0].xpath('./td')]

        pop_i = pct_i = None
        for idx, h in enumerate(headers):
            hl = h.lower()
            if pop_i is None and ("population" in hl or "人口" in hl):
                pop_i = idx
            elif pct_i is None and "%" in hl:
                pct_i = idx
        country_i = None
        for idx, h in enumerate(headers):
            if idx in (pop_i, pct_i):
                continue
            hl = h.lower()
            if any(k in hl for k in ("date", "source", "notes", "rank",
                                     "日期", "来源", "备注", "排名", "%")):
                continue
            country_i = idx
            break
        if country_i is None:
            country_i = 0
        if pop_i is None:               # 找不到人口列就换下一个网址
            continue

        # 逐行取原始文本；跳过表头/空行/World 合计行
        rows = []
        for tr in trs[1:]:
            cells = [c.text_content().strip() for c in tr.xpath('./th | ./td')]
            if len(cells) <= max(country_i, pop_i, pct_i or 0):
                continue
            country = cells[country_i]
            pop = cells[pop_i]
            pct = cells[pct_i] if pct_i is not None else ""
            if not country:
                continue
            if country.lower() in ("world", "世界"):   # 过滤合计行
                continue
            rows.append((country, pop, pct))

        if len(rows) > 100:             # 过关标准：至少上百行
            return rows
    return None


# —— 内置"模拟脏数据样本"（Wikipedia 被墙时的回退，格式与真实表格一致）——
# 每行: (国家, 人口, 占比)；故意混入脚注、不可见空格、% 单位、缺失值。
_SAMPLE = [
    ("India[1]",              "1,428,627,663[1]",      "17.8%"),
    ("China",                 "1,425,671,352[1][2]",   "17.8%"),
    ("United States [b]", "339,996,563[3]",        "4.2%"),
    ("Indonesia",             "277,534,122",           "3.5%"),
    ("Pakistan",              "240,485,658[4]",        "3.0%"),
    ("Nigeria",               "223,804,632",           "2.8%"),
    ("Brazil",                "216,422,446",           "2.7%"),
    ("Bangladesh",            "172,954,319",           "2.2%"),
    ("Russia",                "144,444,359[5]",        "1.8%"),
    ("Mexico",                "128,455,567",           "1.6 %"),
    ("Ethiopia",              "126,527,060",           "1.6%"),
    ("Japan",                 "123,294,513",           "1.5%"),
    ("Philippines",           "117,337,368",           "1.5%"),
    ("Egypt",                 "112,716,598",           "1.4%"),
    ("DR Congo[6]",           "102,262,808",           "1.3%"),
    ("Vietnam",               "98,858,950",            "1.2%"),
    ("Iran",                  "89,172,767",            "1.1%"),
    ("Turkey",                "85,816,199",            "1.1%"),
    ("Germany",               "83,294,633",            "1.0%"),
    ("Thailand",              "71,801,279",            "0.9%"),
    ("United Kingdom",        "67,736,802",            "0.8%"),
    ("France",                "64,756,584",            "0.8%"),
    ("South Africa",          "60,414,495",            "0.8%"),
    ("Italy",                 "58,870,762",            "0.7%"),
    ("Kenya",                 "55,100,586",            "0.7%"),
    ("South Sudan",           "11,088,796",            "—"),      # 占比缺失
    ("Vatican City",          "764",                   ""),       # 占比为空串
]


# ----------------------------------------------------------------------
# 二、清洗函数（文字 / 整数 / 小数 分开处理）
# ----------------------------------------------------------------------
_FOOTNOTE = re.compile(r"\[[^\]]*\]")            # [1] [2][3] [a] [note 1]
_INVISIBLE = re.compile(r"[   ​ 　]")  # 不可见空格

MISSING = {"", "—", "-", "–", "N/A", "n/a", "NA", "null", "None"}


def clean_text(s):
    """文字列：去脚注、去不可见空格、去首尾空白。"""
    s = _FOOTNOTE.sub("", s)
    s = _INVISIBLE.sub(" ", s)
    return s.strip()


def clean_int(s):
    """整数列：去脚注/不可见空格/千分位逗号/单位，转 int；脏到没法转则返回 None。"""
    s = _FOOTNOTE.sub("", s)
    s = _INVISIBLE.sub("", s)
    s = s.replace(",", "")                        # 去千分位逗号
    s = re.sub(r"[a-zA-Z²³]", "", s)              # 去掉混杂的单位字母/上标
    s = s.strip()
    if s in MISSING:
        return None
    try:
        return int(float(s))                       # 兼容 "1.4e3" 之类
    except ValueError:
        return None


def clean_real(s):
    """小数列：去脚注/不可见空格/%单位/千分位，转 float；缺失返回 None。"""
    s = _FOOTNOTE.sub("", s)
    s = _INVISIBLE.sub("", s)
    s = s.replace(",", "")
    s = s.replace("%", "")                        # 去掉 % 单位
    s = s.strip()
    if s in MISSING:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# ----------------------------------------------------------------------
# 三、清洗 + 分类入库（SQLite：文字 TEXT、整数 INTEGER、小数 REAL 分开存）
# ----------------------------------------------------------------------
def build_rows(raw_rows):
    """把原始串清洗成规范元组 (country:str, population:int|None, pct_world:float|None)。"""
    out = []
    for country, pop, pct in raw_rows:
        out.append((clean_text(country), clean_int(pop), clean_real(pct)))
    return out


def load_db(rows, db="countries.db"):
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute("DROP TABLE IF EXISTS countries")
    # 类型分开：文字 TEXT、整数 INTEGER、小数 REAL；缺失值存 NULL
    c.execute("""
        CREATE TABLE countries (
            country     TEXT    PRIMARY KEY,
            population  INTEGER,
            pct_world   REAL
        )
    """)
    c.executemany(
        "INSERT OR REPLACE INTO countries (country, population, pct_world) "
        "VALUES (?, ?, ?)",
        rows,
    )
    conn.commit()
    return conn


# ----------------------------------------------------------------------
# 四、读取并分析（排序 / 求和 / 取前十 / 缺失值）
# ----------------------------------------------------------------------
def analyze(conn):
    c = conn.cursor()
    n = c.execute("SELECT COUNT(*) FROM countries").fetchone()[0]

    # 排名结果表写入 CSV（过关标准：能输出一张排名结果表）
    with open("ranking.csv", "w", newline="", encoding="utf-8-sig") as f:
        f.write("rank,country,population,pct_world\n")
        for rank, (country, pop, pct) in enumerate(
            c.execute("SELECT country, population, pct_world FROM countries "
                      "ORDER BY population DESC"), start=1):
            pct_s = f"{pct:.2f}" if pct is not None else ""
            f.write(f"{rank},{country},{pop},{pct_s}\n")

    # 控制台：打印人口 Top 15
    print("\n" + "=" * 70)
    print(f"人口从大到小 Top 15（共 {n} 行已全量写入 ranking.csv）")
    print("=" * 70)
    print(f"  {'排名':<4}{'国家':<28}{'人口':>15}{'占比':>9}")
    for rank, (country, pop, pct) in enumerate(
        c.execute("SELECT country, population, pct_world FROM countries "
                  "ORDER BY population DESC LIMIT 15"), start=1):
        pct_s = f"{pct:.2f}%" if pct is not None else "NULL"
        print(f"  {rank:<4}{country:<28}{pop:>15,}{pct_s:>9}")

    # 汇总
    print("\n" + "=" * 70)
    print("汇总：求和 / 计数 / 平均")
    print("=" * 70)
    total_pop, n_pct, sum_pct = c.execute(
        "SELECT SUM(population), COUNT(pct_world), SUM(pct_world) FROM countries"
    ).fetchone()
    print(f"  入库国家总数        : {n}")
    print(f"  人口总和（SUM）     : {total_pop:,}")
    print(f"  平均人口（AVG）     : {total_pop // n:,}")
    print(f"  占比有效值个数      : {n_pct}（缺失 {n - n_pct} 个，存 NULL）")
    if sum_pct is not None:
        print(f"  占比合计（应≈100%） : {sum_pct:.2f}%")

    # 缺失值
    print("\n" + "=" * 70)
    print("缺失值处理规则演示（占比列为 NULL 的行）")
    print("=" * 70)
    nulls = c.execute("SELECT country FROM countries WHERE pct_world IS NULL").fetchall()
    print(f"  规则：无法解析的占比统一存 NULL，不参与 AVG/SUM，也不虚报为 0。")
    print(f"  当前缺失占比的行 : {[r[0] for r in nulls] if nulls else '无（真实表格占比列完整）'}")

    # 类型校验
    print("\n" + "=" * 70)
    print("入库类型校验（PRAGMA table_info）")
    print("=" * 70)
    for row in c.execute("PRAGMA table_info(countries)"):
        print(f"  {row[1]:<12} -> {row[2]}")

    print("\n  ✓ 数字列可正常参与计算；排名结果表已输出到 ranking.csv。")
    return conn


# ----------------------------------------------------------------------
# 五、主流程
# ----------------------------------------------------------------------
if __name__ == "__main__":
    raw = fetch_from_wikipedia()
    source = "Wikipedia（真实抓取）"
    if not raw:
        raw = _SAMPLE
        source = "内置模拟脏数据样本（本机无法直连 Wikipedia，已回退）"

    print(f"数据来源：{source}")
    print(f"原始行数：{len(raw)}")
    print("清洗前（前 3 行，注意逗号/脚注/不可见空格/% 单位）：")
    for r in raw[:3]:
        print(f"   {r!r}")

    rows = build_rows(raw)
    conn = load_db(rows)
    analyze(conn)
    conn.close()
