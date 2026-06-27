#!/usr/bin/env python3
"""
通用开奖号码获取脚本 v11
自动适配 shenxianlian / facaijiushou / fafafaf 三种数据格式
7数据源全量降级
"""

import json, os, sys, ssl, re, time, base64, traceback
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
    return 2026000 < period < 2027000 and len(digits) >= 4 and digits.isdigit()

# ==========================================
# 7个数据源（同上）
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
            m = re.search(r'第\s*(\d{7})\s*期[\s\S]*?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html)
            if m:
                period = int(m.group(1))
                digits = ''.join(m.groups()[1:])
                if valid(period, digits): return digits[:4], period
        except: continue
    return None, None

def fetch_500():
    try:
        html, _ = http_get('https://datachart.500.com/plw/history/newinc/history.php?start=26001&end=26999')
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
            # 不同格式的 winning 位置不同
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
# 数据格式适配
# ==========================================

def detect_format(data):
    """检测数据格式类型"""
    if 'records' in data and isinstance(data.get('records'), list):
        return 'facaijiushou'  # { records: [{period, winning, sequences, hits}, ...] }
    if 'tablePages' in data:
        return 'fafafaf'  # { tablePages: { id: { records: [...] } } }
    return 'shenxianlian'  # { period, winning, history, sequences, ... }

def get_current_period(data, fmt):
    """从数据中获取当前期号"""
    if fmt == 'facaijiushou':
        records = data.get('records', [])
        if records:
            p = records[-1].get('period', '')
            return int(p) if str(p).isdigit() else 0
        return 0
    elif fmt == 'fafafaf':
        # 取第一个表格的第一条记录
        for tid, table in data.get('tablePages', {}).items():
            records = table.get('records', [])
            if records:
                return records[-1].get('period', 0)
        return 0
    else:
        return data.get('period', 0)

def is_already_won(data, fmt):
    """检查是否已经获取过开奖号码"""
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
    """将开奖号码写入对应格式"""
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
        # 限制50条
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
        
    else:  # shenxianlian
        data['winning'] = winning4
        data['hits'] = {}
        history = data.get('history', [])
        for h in history:
            if h['period'] == cp:
                h['winning'] = winning4
                break
        else:
            history.insert(0, {'period': cp, 'winning': winning4, 'time': now_str, 'hits': {}})
        history.sort(key=lambda x: x['period'], reverse=True)
        if len(history) > 7:
            history = history[:7]
        data['history'] = history
    
    data['lastUpdate'] = int(datetime.now().timestamp() * 1000)
    data['version'] = int(time.time())
    return data

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
    
    log(f'===== 排列5开奖 v11 | {REPO} | {DATA_FILE} =====')
    
    # 读取数据
    sha, data = github_get(DATA_FILE)
    fmt = detect_format(data)
    log(f'数据格式: {fmt}')
    
    cp = get_current_period(data, fmt)
    log(f'当前期号: {cp}')
    
    if is_already_won(data, fmt):
        log('已开奖，跳过')
        return True
    
    # 7源降级
    sources = [
        ('江苏体彩网', fetch_js_lottery),
        ('彩经网移动端', fetch_cjcp),
        ('500彩票网', fetch_500),
        ('体彩官方API', fetch_sporttery),
        ('百度搜索', fetch_baidu),
        ('必应搜索', fetch_bing),
        ('缓存兜底', lambda: fetch_cache(DATA_FILE)),
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
    
    # 写入数据
    data = set_winning(data, fmt, winning4, period, cp)
    
    # 推送数据文件
    try:
        r = github_put(DATA_FILE, data, sha, f'更新开奖号码: {winning4} (期{cp}, 源{source})')
        log(f'✅ 数据已推送: {r["content"]["sha"][:8]}')
    except Exception as e:
        log(f'❌ 推送失败: {e}')
        sys.exit(1)
    
    # 更新 index.html
    try:
        sha2, _ = github_get('index.html')
        req = Request(f'https://api.github.com/repos/{REPO}/contents/index.html',
                      headers={'Authorization': f'token {os.environ.get("GH_TOKEN", "")}',
                               'Accept': 'application/vnd.github.v3+json'})
        resp = urlopen(req, timeout=30, context=ctx)
        hi = json.loads(resp.read().decode())
        html = base64.b64decode(hi['content']).decode('utf-8')
        
        embedded = json.dumps(data, ensure_ascii=False)
        ls = html.find('let S =')
        if ls > 0:
            nf = html.find('\n// ===', ls)
            if nf < 0: nf = html.find('\nfunction', ls)
            if nf > 0:
                html = html.replace(html[ls:nf], f'let S = {embedded};')
        elif 'embedded-data' in html:
            # facaijiushou/fafafaf 可能用 embedded-data 格式
            em_start = html.find('id="embedded-data"')
            if em_start > 0:
                em_start = html.find('>', em_start) + 1
                em_end = html.find('</script>', em_start)
                html = html[:em_start] + json.dumps(data, ensure_ascii=False) + html[em_end:]
        
        b64 = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        r2 = github_put_raw('index.html', b64, hi['sha'], f'同步开奖: {winning4}')
        log(f'✅ index.html 已更新: {r2["content"]["sha"][:8]}')
    except Exception as e:
        log(f'⚠️ index.html 更新失败: {e}')
    
    log(f'===== 完成: 期{cp} 前4位{winning4} ({source}) =====')

if __name__ == '__main__':
    try:
        main()
        sys.exit(0)
    except Exception as e:
        log(f'❌ {traceback.format_exc()}')
        sys.exit(1)
