#!/usr/bin/env python3
"""
通用开奖号码获取脚本 v12（开奖驱动版）
================================
核心逻辑（shenxianlian 格式）：
1. 期数完全由真实开奖结果驱动，不再按日历天数生成：
   - 抓到新的开奖(期号P) -> 写入P期开奖号和命中 -> 自动生成 P+1 期新资料
   - 休市停售期间抓不到新开奖 -> 什么都不做，期数原地不动
   - 复市后第一期开奖被获取到 -> 自动更新到新一期
2. 防过期数据：数据源返回的期号小于"已开奖期号"时视为过期，一律忽略
3. 自愈：数据超前（当前期 > 已开奖期+1）时自动回滚，并清理超前的假记录
4. 兼容 shenxianlian / facaijiushou / fafafaf 三种数据格式
   （仅 shenxianlian 启用开奖驱动推进，其他格式维持原有填入逻辑）
"""

import json, os, sys, ssl, re, time, base64, random, traceback
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone, timedelta

REPO = os.environ.get('GITHUB_REPOSITORY', 'ebupuba099-lang/shenxianlian')
DATA_FILE = 'data/sxl_data.json'  # 默认，后面会根据项目名修改
TZ = timezone(timedelta(hours=8))

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
HEADERS = {'User-Agent': UA, 'Accept': 'text/html,application/xhtml+xml,*/*', 'Accept-Language': 'zh-CN,zh;q=0.9'}

def log(msg):
    print(f'[{datetime.now(TZ).strftime("%H:%M:%S")}] {msg}', flush=True)

def http_get(url, retries=2, timeout=20):
    for i in range(retries):
        try:
            resp = urlopen(Request(url, headers=HEADERS), timeout=timeout, context=ctx)
            return resp.read().decode('utf-8', errors='ignore'), resp.status
        except HTTPError as e:
            if i == retries - 1: raise
            time.sleep(2)
        except URLError as e:
            if i == retries - 1: raise
            time.sleep(2)
    return None, 0

def valid(period, digits):
    # 跨年份通用校验: 20xxxxxx 年份段 + 期号序号 1~399
    return 2000000 < period < 2100000 and 0 < (period % 1000) < 400 and len(digits) >= 4 and digits.isdigit()

# ==========================================
# 数据源
# ==========================================

def fetch_js_lottery():
    try:
        html, _ = http_get('https://api.js-lottery.com/')
        if not html: return None, None
        posts = re.findall(r'(post-\d+\.html)', html)
        for post in posts[:5]:
            try:
                detail, _ = http_get(f'https://api.js-lottery.com/{post}')
                if not detail: continue
                t = re.search(r'排列[5五]第\s*(\d{5})\s*期', detail)
                if not t: continue
                period = int('20' + t.group(1))
                n = re.search(r'(?:本期)?开奖号码[：:]\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', detail)
                if n:
                    digits = ''.join(n.groups())
                    if valid(period, digits):
                        return digits[:4], period
            except: continue
    except Exception as e: log(f'  江苏体彩: {e}')
    return None, None

def fetch_cjcp():
    for url in ['https://m.cjcp.com.cn/kaijiang/pl5/', 'https://m.cjcp.cn/kaijiang/pl5/']:
        try:
            html, _ = http_get(url, retries=1)
            if not html or len(html) < 3000: continue

            # 格式1: 传统文本
            m = re.search(r'第\s*(\d{7})\s*期[\s\S]*?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html)
            if m:
                period = int(m.group(1))
                digits = ''.join(m.groups()[1:])
                if valid(period, digits): return digits[:4], period

            # 格式2: span标签 - 精确匹配最新期
            period_m = re.search(r'第(\d{7})期开奖', html)
            if period_m:
                period = int(period_m.group(1))
                idx = period_m.start()
                chunk = html[idx:idx+800]
                nums = re.findall(r'qiu_red">(\d)</span>', chunk)
                if len(nums) >= 5:
                    digits = ''.join(nums[:5])
                    if valid(period, digits): return digits[:4], period
        except: continue
    return None, None

def fetch_500():
    try:
        yy = datetime.now(TZ).strftime('%y')  # 动态年份, 避免跨年后失效
        url = f'https://datachart.500.com/plw/history/newinc/history.php?start={yy}001&end={yy}999'
        html, _ = http_get(url)
        if not html: return None, None
        rows = re.findall(r'(\d{5})\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html)
        if rows:
            last = rows[-1]
            period = int('20' + last[0])
            digits = ''.join(last[1:])
            if valid(period, digits): return digits[:4], period
    except Exception as e: log(f'  500网: {e}')
    return None, None

def fetch_sporttery():
    try:
        html, _ = http_get('https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&isVerify=1&pageNo=1', timeout=10)
        if not html: return None, None
        data = json.loads(html)
        if data.get('errorCode') == '0':
            r = data.get('value', {}).get('list', [{}])[0]
            num = r.get('lotteryDrawResult', '').replace(' ', '')
            period = int(r.get('lotteryDrawNum', 0))
            if valid(period, num): return num[:4], period
    except: pass
    return None, None

def fetch_baidu():
    try:
        from urllib.parse import quote
        html, _ = http_get(f'https://www.baidu.com/s?wd={quote("排列5开奖结果")}', timeout=10)
        if not html: return None, None
        m = re.search(r'第\s*(\d{7})\s*期[\s\S]{0,50}?(\d)\s+(\d)\s+(\d)\s+(\d)', html)
        if m:
            period = int(m.group(1))
            digits = m.group(2)+m.group(3)+m.group(4)+m.group(5)
            if valid(period, digits): return digits[:4], period
    except: pass
    return None, None

def fetch_bing():
    try:
        from urllib.parse import quote
        html, _ = http_get(f'https://www.bing.com/search?q={quote("排列5 开奖号码")}', timeout=10)
        if not html: return None, None
        m = re.search(r'(\d{7})\s*期[\s\S]{0,30}?(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)', html)
        if m:
            period = int(m.group(1))
            digits = m.group(2)+m.group(3)+m.group(4)+m.group(5)
            if valid(period, digits): return digits[:4], period
    except: pass
    return None, None

def fetch_cache(data_file):
    try:
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                d = json.load(f)
            w = d.get('winning', '')
            if not w:
                records = d.get('records', [])
                if records:
                    w = records[-1].get('winning', '')
            return w, d.get('period', 0)
    except: pass
    return None, None

# ==========================================
# GitHub API
# ==========================================
def github_get(path):
    token = os.environ.get('GH_TOKEN', '')
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{path}',
                  headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'})
    resp = urlopen(req, timeout=30, context=ctx)
    info = json.loads(resp.read().decode())
    return info['sha'], json.loads(base64.b64decode(info['content']).decode('utf-8'))

def github_get_raw(path):
    token = os.environ.get('GH_TOKEN', '')
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{path}',
                  headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'})
    resp = urlopen(req, timeout=30, context=ctx)
    info = json.loads(resp.read().decode())
    return info['sha'], base64.b64decode(info['content']).decode('utf-8')

def github_put(path, content, sha, msg):
    token = os.environ.get('GH_TOKEN', '')
    b64 = base64.b64encode(json.dumps(content, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    payload = {'message': msg, 'content': b64, 'sha': sha}
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{path}',
                  data=json.dumps(payload).encode('utf-8'),
                  headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json',
                           'Content-Type': 'application/json'}, method='PUT')
    resp = urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read().decode())

def github_put_raw(path, b64_content, sha, msg):
    token = os.environ.get('GH_TOKEN', '')
    payload = {'message': msg, 'content': b64_content, 'sha': sha}
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{path}',
                  data=json.dumps(payload).encode('utf-8'),
                  headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json',
                           'Content-Type': 'application/json'}, method='PUT')
    resp = urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read().decode())


# ==========================================
# 粒数计算（与前端 calcHits 逻辑一致）
# ==========================================
def calc_hits_py(sequences, winning):
    """计算每个位置的粒数"""
    hits = {}
    if not winning or len(winning) != 4:
        return hits
    pos_map = [('千', 0), ('百', 1), ('十', 2), ('个', 3)]
    for pos_name, idx in pos_map:
        seq = sequences.get(pos_name, '')
        if not seq:
            hits[pos_name] = 0
            continue
        nums = seq.split(' ')
        target = winning[idx]
        found = False
        for j in range(len(nums) - 1, -1, -1):
            if target in nums[j]:
                hits[pos_name] = len(nums[j])
                found = True
                break
        if not found:
            hits[pos_name] = 0
    return hits

# ==========================================
# 随机资料生成（与 generate.py 一致的递减序列）
# ==========================================
def gen_sequence():
    digits = list(range(10))
    random.shuffle(digits)
    selected = digits[:8]
    parts = [''.join(str(d) for d in selected)]
    current = list(selected)
    while len(current) > 1:
        current.pop(random.randint(0, len(current) - 1))
        parts.append(''.join(str(d) for d in current))
    return ' '.join(parts)

# ==========================================
# 更新 index.html 内嵌数据（let S + embedded-data 双写）
# ==========================================
def update_index_html(data):
    try:
        sha2, html = github_get_raw('index.html')
        embedded = json.dumps(data, ensure_ascii=False)
        changed = False

        # 1) let S = {...};
        ls = html.find('let S =')
        if ls >= 0:
            nf = html.find('\n// ===', ls)
            if nf < 0: nf = html.find('\nfunction', ls)
            if nf > 0:
                new_part = f'let S = {embedded};'
                if html[ls:nf].rstrip() != new_part:
                    html = html[:ls] + new_part + html[nf:]
                    changed = True

        # 2) <script id="embedded-data" ...>...</script>
        m = re.search(r'(<script[^>]*id="embedded-data"[^>]*>)([\s\S]*?)(</script>)', html)
        if m and m.group(2).strip() != embedded:
            html = html[:m.start(2)] + embedded + html[m.end(2):]
            changed = True

        if not changed:
            log('index.html 内嵌数据已是最新')
            return True

        b64 = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        github_put_raw('index.html', b64, sha2, f'同步内嵌数据: 期{data.get("period")} 开奖={data.get("winning") or "待开"}')
        log('✅ index.html 内嵌数据已更新')
        return True
    except Exception as e:
        log(f'⚠️ index.html 更新失败: {e}')
        return False

# ==========================================
# 数据格式适配
# ==========================================

def detect_format(data):
    if 'records' in data and isinstance(data.get('records'), list):
        return 'facaijiushou'
    if 'tablePages' in data:
        return 'fafafaf'
    return 'shenxianlian'

def get_current_period(data, fmt):
    if fmt == 'facaijiushou':
        records = data.get('records', [])
        if records:
            p = records[-1].get('period', '')
            return int(p) if str(p).isdigit() else 0
        return 0
    elif fmt == 'fafafaf':
        for tid, table in data.get('tablePages', {}).items():
            records = table.get('records', [])
            if records:
                return records[-1].get('period', 0)
        return 0
    else:
        return data.get('period', 0)

def is_already_won(data, fmt):
    if fmt == 'facaijiushou':
        records = data.get('records', [])
        if records:
            return bool(records[-1].get('winning', ''))
        return False
    elif fmt == 'fafafaf':
        for tid, table in data.get('tablePages', {}).items():
            records = table.get('records', [])
            if records:
                return bool(records[-1].get('winning', ''))
        return False
    else:
        return bool(data.get('winning', ''))

def set_winning(data, fmt, winning4, period, cp):
    """将开奖号码写入对应格式（facaijiushou / fafafaf 用，仅填入不推进）"""
    now_str = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')

    if fmt == 'facaijiushou':
        records = data.get('records', [])
        for r in records:
            if str(r.get('period', '')) == str(cp):
                r['winning'] = winning4
                r['hits'] = r.get('hits', {})
                break
        else:
            records.append({
                'period': str(cp),
                'winning': winning4,
                'hits': {},
                'time': now_str,
                'sequences': records[-1].get('sequences', {}) if records else {}
            })
        if len(records) > 50:
            data['records'] = records[-50:]

    elif fmt == 'fafafaf':
        for tid, table in data.get('tablePages', {}).items():
            records = table.get('records', [])
            for r in records:
                if r.get('period') == cp or str(r.get('period')) == str(cp):
                    r['winning'] = winning4
                    r['header'] = table.get('name', '')
                    break

    else:  # shenxianlian（此分支一般不会走到，主流程走 sync_shenxianlian）
        data['winning'] = winning4
        data['hits'] = calc_hits_py(data.get('sequences', {}), winning4)

    data['lastUpdate'] = int(datetime.now(TZ).timestamp() * 1000)
    data['version'] = int(time.time())
    return data

# ==========================================
# shenxianlian 开奖驱动同步（核心）
# ==========================================
def sync_shenxianlian(sha, data):
    cp = int(data.get('period', 0) or 0)
    history = data.get('history', []) or []

    # 已开奖期号：优先 lastDrawnPeriod 字段，否则取历史中最新已开奖的一期
    last_drawn = int(data.get('lastDrawnPeriod', 0) or 0)
    if not last_drawn:
        drawn = [int(h.get('period', 0) or 0) for h in history if h.get('winning')]
        last_drawn = max(drawn) if drawn else 0
    log(f'当前期号: {cp} | 已开奖期号: {last_drawn}')

    # ---- 抓取最新开奖（带过期数据防护）----
    sources = [
        ('江苏体彩网', fetch_js_lottery),
        ('彩经网移动端', fetch_cjcp),
        ('500彩票网', fetch_500),
        ('体彩官方API', fetch_sporttery),
        ('百度搜索', fetch_baidu),
        ('必应搜索', fetch_bing),
    ]

    best = None      # (期号, 号码, 源名)
    any_resp = False # 是否有任何源返回过有效格式的数据
    for name, fn in sources:
        try:
            log(f'尝试: {name}')
            w, p = fn()
            if not (w and p):
                continue
            any_resp = True
            if not valid(p, w):
                log(f'  ✗ 数据异常: 期{p} 号{w}')
                continue
            if last_drawn and p < last_drawn:
                log(f'  ↷ 过期数据: 期{p} < 已开奖{last_drawn}，忽略')
                continue
            same_year = (p // 1000) == (last_drawn // 1000) if last_drawn else True
            if last_drawn and same_year and p > last_drawn + 60:
                log(f'  ✗ 期号跳跃异常: {p}，忽略')
                continue
            log(f'  ✅ {name}: 期{p} 号{w}')
            if best is None or p > best[0]:
                best = (p, w, name)
        except Exception as e:
            log(f'  ❌ {name}: {e}')

    if best is None:
        if any_resp:
            log('暂无新开奖（休市/停售或未到开奖时间），期数保持不变')
            return True
        log('❌ 所有数据源均失败')
        return False

    p, w, source = best

    # ---- 状态1: 无新开奖且状态正常 -> 什么都不做 ----
    if p == last_drawn and cp == p + 1:
        if data.get('winning'):
            # 当前期尚未开奖却带有开奖号（历史脏数据），清除
            log(f'当前期{cp}尚未开奖却带有开奖号，清除脏数据')
            data['winning'] = ''
            data['hits'] = {}
            data['lastUpdate'] = int(datetime.now(TZ).timestamp() * 1000)
            data['version'] = int(time.time())
            try:
                github_put(DATA_FILE, data, sha, f'清除{cp}期异常开奖数据')
                update_index_html(data)
            except Exception as e:
                log(f'❌ 清除脏数据失败: {e}')
                return False
        else:
            log(f'期{p}已同步过，当前期{cp}正确，无需更新')
        return True

    # ---- 状态2: 有新开奖（或数据超前需回滚）-> 同步并生成新一期 ----
    log(f'同步开奖: 期{p} 号{w} (源{source}) -> 生成{p + 1}期新资料')
    now_str = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')

    # P期的资料：若P正好是当前展示期，则当前sequences就是P期的资料
    seq_for_p = data.get('sequences', {}) or {} if p == cp else {}

    # upsert P期历史记录
    entry = None
    for h in history:
        if int(h.get('period', 0) or 0) == p:
            entry = h
            break
    if entry is None:
        entry = {'period': p}
        history.insert(0, entry)
    entry['winning'] = w
    if seq_for_p and not entry.get('sequences'):
        entry['sequences'] = seq_for_p
    entry['hits'] = calc_hits_py(entry.get('sequences', {}), w)
    if not entry.get('time'):
        entry['time'] = now_str

    # 清理超前的假记录（期号大于P的一律删除）
    before = len(history)
    history = [h for h in history if int(h.get('period', 0) or 0) <= p]
    if len(history) != before:
        log(f'清理超前记录: {before - len(history)}条')
    history.sort(key=lambda x: int(x.get('period', 0) or 0), reverse=True)
    history = history[:7]
    data['history'] = history

    # 推进到 P+1 期，生成新资料
    data['lastDrawnPeriod'] = p
    data['period'] = p + 1
    data['sequences'] = {'千': gen_sequence(), '百': gen_sequence(), '十': gen_sequence(), '个': gen_sequence()}
    data['winning'] = ''
    data['hits'] = {}
    data.pop('lastGenerateAttempt', None)
    data['lastUpdate'] = int(datetime.now(TZ).timestamp() * 1000)
    data['version'] = int(time.time())

    try:
        r = github_put(DATA_FILE, data, sha, f'开奖同步: {p}期 {w} -> 生成{p + 1}期 (源{source})')
        log(f'✅ 数据已推送: {r["content"]["sha"][:8]}')
    except Exception as e:
        log(f'❌ 推送失败: {e}')
        return False

    update_index_html(data)
    log(f'===== 完成: {p}期开奖{w}已记录，{p + 1}期新资料已生成 =====')
    return True

# ==========================================
# 主流程
# ==========================================
def main():
    global DATA_FILE

    # 根据仓库名确定数据文件
    if 'facaijiushou' in REPO:
        DATA_FILE = 'data/lottery_data.json'
    elif 'fafafaf' in REPO:
        DATA_FILE = 'data/lottery_data.json'
    else:
        DATA_FILE = 'data/sxl_data.json'

    log(f'===== 排列5开奖驱动同步 v12 | {REPO} | {DATA_FILE} =====')

    # 读取数据
    sha, data = github_get(DATA_FILE)
    fmt = detect_format(data)
    log(f'数据格式: {fmt}')

    # shenxianlian：开奖驱动同步（填入 + 推进 一体）
    if fmt == 'shenxianlian':
        ok = sync_shenxianlian(sha, data)
        sys.exit(0 if ok else 1)

    # ---- 以下为 facaijiushou / fafafaf 格式的原有逻辑（仅填入开奖号）----
    cp = get_current_period(data, fmt)
    log(f'当前期号: {cp}')

    if is_already_won(data, fmt):
        log('已开奖，跳过')
        return True

    sources = [
        ('江苏体彩网', fetch_js_lottery),
        ('彩经网移动端', fetch_cjcp),
        ('500彩票网', fetch_500),
        ('体彩官方API', fetch_sporttery),
        ('百度搜索', fetch_baidu),
        ('必应搜索', fetch_bing),
    ]

    result = None
    for name, fn in sources:
        try:
            log(f'尝试: {name}')
            w, p = fn()
            if w and p:
                if abs(p - cp) > 10:
                    log(f'  期号不符 (获取{p}, 当前{cp})')
                    continue
                result = (w, p, name)
                log(f'  ✅ {name}: 期{p} 前4位{w}')
                break
        except Exception as e:
            log(f'  ❌ {e}')

    if not result:
        log('❌ 全部失败')
        sys.exit(1)

    winning4, period, source = result
    data = set_winning(data, fmt, winning4, period, cp)

    try:
        r = github_put(DATA_FILE, data, sha, f'更新开奖号码: {winning4} (期{cp}, 源{source})')
        log(f'✅ 数据已推送: {r["content"]["sha"][:8]}')
    except Exception as e:
        log(f'❌ 推送失败: {e}')
        sys.exit(1)

    log(f'===== 完成: 期{cp} 前4位{winning4} ({source}) =====')
    return True

if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except SystemExit:
        raise
    except Exception as e:
        log(f'❌ {traceback.format_exc()}')
        sys.exit(1)
