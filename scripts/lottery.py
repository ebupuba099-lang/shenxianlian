#!/usr/bin/env python3
"""
神仙连 - 开奖号码获取 v10
7个数据源全量降级，每个源独立策略，最大化成功率

源1: 江苏体彩网文章页 (最稳定)
源2: 彩经网移动端HTML
源3: 500彩票网表格
源4: 体彩官方JSON API
源5: 百度搜索"排列5开奖"快照
源6: 必应搜索"排列5开奖结果"
源7: 本地缓存兜底
"""

import json, os, sys, ssl, re, time, base64, traceback
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from datetime import datetime, timezone, timedelta

REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'
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
    """校验期号和号码是否合理"""
    return 2026000 < period < 2027000 and len(digits) >= 4 and digits.isdigit()

# ==========================================
# 源1: 江苏体彩网 (当前最稳定)
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
    except Exception as e:
        log(f'  江苏体彩: {e}')
    return None, None

# ==========================================
# 源2: 彩经网移动端
# ==========================================
def fetch_cjcp():
    for url in ['https://m.cjcp.com.cn/kaijiang/pl5/', 'https://m.cjcp.cn/kaijiang/pl5/']:
        try:
            html, _ = http_get(url, retries=1)
            if not html or len(html) < 3000: continue
            if '排列5' not in html and '排列五' not in html: continue
            
            m = re.search(r'第\s*(\d{7})\s*期[\s\S]*?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html)
            if m:
                period = int(m.group(1))
                digits = ''.join(m.groups()[1:])
                if valid(period, digits):
                    return digits[:4], period
        except: continue
    return None, None

# ==========================================
# 源3: 500彩票网
# ==========================================
def fetch_500():
    try:
        html, _ = http_get('https://datachart.500.com/plw/history/newinc/history.php?start=26001&end=26999')
        if not html: return None, None
        rows = re.findall(r'(\d{5})\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html)
        if rows:
            last = rows[-1]
            period = int('20' + last[0])
            digits = ''.join(last[1:])
            if valid(period, digits):
                return digits[:4], period
    except Exception as e:
        log(f'  500网: {e}')
    return None, None

# ==========================================
# 源4: 体彩官方JSON API
# ==========================================
def fetch_sporttery():
    try:
        url = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&isVerify=1&pageNo=1'
        html, _ = http_get(url, timeout=10)
        if not html: return None, None
        data = json.loads(html)
        if data.get('errorCode') == '0':
            r = data.get('value', {}).get('list', [{}])[0]
            num = r.get('lotteryDrawResult', '').replace(' ', '')
            period = int(r.get('lotteryDrawNum', 0))
            if valid(period, num):
                return num[:4], period
    except: pass
    return None, None

# ==========================================
# 源5: 百度搜索快照
# ==========================================
def fetch_baidu():
    """百度搜索"排列5开奖结果"，从摘要中提取"""
    try:
        kw = quote('排列5开奖结果')
        html, _ = http_get(f'https://www.baidu.com/s?wd={kw}', timeout=10)
        if not html: return None, None
        # 百度搜索结果中常有开奖号码
        m = re.search(r'第\s*(\d{7})\s*期[\s\S]{0,50}?(\d)\s+(\d)\s+(\d)\s+(\d)', html)
        if m:
            period = int(m.group(1))
            digits = m.group(2) + m.group(3) + m.group(4) + m.group(5)
            if valid(period, digits):
                return digits[:4], period
    except: pass
    return None, None

# ==========================================
# 源6: 必应搜索
# ==========================================
def fetch_bing():
    """必应搜索"""
    try:
        kw = quote('排列5 开奖号码')
        html, _ = http_get(f'https://www.bing.com/search?q={kw}', timeout=10)
        if not html: return None, None
        m = re.search(r'(\d{7})\s*期[\s\S]{0,30}?(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)', html)
        if m:
            period = int(m.group(1))
            digits = m.group(2) + m.group(3) + m.group(4) + m.group(5)
            if valid(period, digits):
                return digits[:4], period
    except: pass
    return None, None

# ==========================================
# 源7: 缓存兜底
# ==========================================
def fetch_cache():
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d.get('winning', ''), d.get('period', 0)
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

# ==========================================
# 主流程
# ==========================================
def main():
    log('===== 排列5开奖获取 v10 (7源) =====')
    
    sha, data = github_get(DATA_FILE)
    cp = data.get('period', 0)
    cw = data.get('winning', '')
    log(f'当前: 期{cp} 号{cw or "未开"}')
    
    if cw:
        log('已开奖，跳过')
        return True
    
    sources = [
        ('江苏体彩网', fetch_js_lottery),
        ('彩经网移动端', fetch_cjcp),
        ('500彩票网', fetch_500),
        ('体彩官方API', fetch_sporttery),
        ('百度搜索', fetch_baidu),
        ('必应搜索', fetch_bing),
        ('缓存兜底', fetch_cache),
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
    data['winning'] = winning4
    data['hits'] = {}
    data['lastUpdate'] = int(datetime.now().timestamp() * 1000)
    data['version'] = int(time.time())
    
    # 更新 history
    history = data.get('history', [])
    found = False
    for h in history:
        if h['period'] == cp:
            h['winning'] = winning4
            found = True
            break
    if not found:
        history.insert(0, {
            'period': cp, 'winning': winning4,
            'time': datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S'), 'hits': {}
        })
    history.sort(key=lambda x: x['period'], reverse=True)
    if len(history) > 7:
        history = history[:7]
    data['history'] = history
    
    # 推送数据
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
        nf = html.find('function calcAutoPeriod', ls)
        html = html.replace(html[ls:nf], f'let S = {embedded};\n\n')
        
        b64 = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        r2 = github_put('index.html', None, hi['sha'], f'同步开奖: {winning4}')
        # 用 raw API 因为 github_put 期望 content_dict
        payload = {'message': f'同步开奖: {winning4}', 'content': b64, 'sha': hi['sha']}
        req2 = Request(f'https://api.github.com/repos/{REPO}/contents/index.html',
                       data=json.dumps(payload).encode('utf-8'),
                       headers={'Authorization': f'token {os.environ.get("GH_TOKEN", "")}',
                                'Accept': 'application/vnd.github.v3+json', 'Content-Type': 'application/json'},
                       method='PUT')
        resp2 = urlopen(req2, timeout=30, context=ctx)
        log(f'✅ index.html 已更新: {json.loads(resp2.read().decode())["content"]["sha"][:8]}')
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
