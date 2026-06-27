#!/usr/bin/env python3
"""
神仙连 - 开奖号码获取 v9
多数据源降级 + 历史缓存兜底，最大化成功率

数据源优先级：
0. Vercel 代理 API (最稳定，Vercel IP 不会被墙)
1. 彩经网移动端 (m.cjcp.com.cn)
2. 江苏体彩网 (api.js-lottery.com)
3. 500彩票网 (datachart.500.com)
4. 体彩官方API (webapi.sporttery.cn)
5. 上次缓存兜底 (data/sxl_data.json 中的 winning)
"""

# Vercel 部署后替换为你的实际地址
VERCEL_API = 'https://shenxianlian.vercel.app/api/pl5'

import json, os, sys, ssl, re, time, base64, traceback
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from datetime import datetime, timezone, timedelta

REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

TZ = timezone(timedelta(hours=8))
ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}

def log(msg):
    t = datetime.now(TZ).strftime('%H:%M:%S')
    print(f'[{t}] {msg}', flush=True)

def http_get(url, retries=3, timeout=20):
    """带重试的HTTP GET"""
    for i in range(retries):
        try:
            req = Request(url, headers=HEADERS)
            resp = urlopen(req, timeout=timeout, context=ctx)
            return resp.read().decode('utf-8', errors='ignore'), resp.status
        except HTTPError as e:
            if i == retries - 1:
                raise
            log(f'  HTTP {e.code}, 重试 {i+2}/{retries}')
            time.sleep(2)
        except URLError as e:
            if i == retries - 1:
                raise
            log(f'  网络错误, 重试 {i+2}/{retries}')
            time.sleep(2)
    return None, 0

# ==========================================
# 数据源0: Vercel 代理 API (最优先)
# ==========================================
def fetch_vercel():
    """Vercel Serverless 代理，用 Vercel IP 抓取数据"""
    try:
        html, status = http_get(VERCEL_API, retries=2, timeout=15)
        if not html:
            return None, None
        data = json.loads(html)
        if data.get('success') and data.get('winning'):
            period = data.get('period', 0)
            winning = data.get('winning', '')
            source = data.get('source', 'Vercel')
            log(f'  Vercel代理({source}): 期{period} 号{winning}')
            return winning, period
    except Exception as e:
        log(f'  Vercel API异常: {e}')
    return None, None

# ==========================================
# 数据源1: 彩经网移动端
# ==========================================
def fetch_cjcp():
    """彩经网移动端 - 排列5开奖页"""
    try:
        for url in ['https://m.cjcp.com.cn/kaijiang/pl5/', 'https://m.cjcp.cn/kaijiang/pl5/']:
            try:
                html, status = http_get(url, retries=2)
                if not html or len(html) < 3000:
                    continue
                if '排列5' not in html and '排列五' not in html:
                    continue
                
                # 提取开奖号码: 第2026167期 ... 0 1 2 3 1
                m = re.search(r'第\s*(\d{7})\s*期.*?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html, re.DOTALL)
                if not m:
                    m = re.search(r'(\d{7})\s*期.*?(\d)\s*(\d)\s*(\d)\s*(\d)\s*(\d)', html)
                if m:
                    period = int(m.group(1))
                    digits = ''.join(m.groups()[1:])
                    if 2026000 < period < 2027000:
                        return digits[:4], period
            except:
                continue
    except Exception as e:
        log(f'  彩经网异常: {e}')
    return None, None

# ==========================================
# 数据源2: 江苏体彩网
# ==========================================
def fetch_js_lottery():
    """江苏体彩网 - 从文章列表找到排列5开奖公告"""
    try:
        # 获取文章列表
        list_html, _ = http_get('https://api.js-lottery.com/')
        if not list_html:
            return None, None
        
        # 找所有文章链接
        links = re.findall(r'href="([^"]+)"', list_html)
        pl5_links = []
        for link in links:
            if '排列5' in link or '排列五' in link:
                # 提取href中的实际URL
                m = re.search(r'(post-\d+\.html)', link)
                if m:
                    pl5_links.append(m.group(1))
        
        for post in pl5_links[:5]:
            try:
                detail_url = f'https://api.js-lottery.com/{post}'
                detail, _ = http_get(detail_url)
                if not detail:
                    continue
                
                # 精确匹配排列5标题
                title_m = re.search(r'排列[5五]第\s*(\d{5})\s*期', detail)
                if not title_m:
                    continue
                
                period_str = title_m.group(1)
                period = int('20' + period_str) if len(period_str) == 5 else int(period_str)
                
                # 匹配开奖号码 (支持"开奖号码"和"本期开奖号码"两种格式)
                num_m = re.search(r'(?:本期)?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', detail)
                if num_m:
                    digits = ''.join(num_m.groups())
                    if 2026000 < period < 2027000:
                        log(f'  江苏体彩网: 期{period} 号{digits}')
                        return digits[:4], period
            except:
                continue
    except Exception as e:
        log(f'  江苏体彩网异常: {e}')
    return None, None

# ==========================================
# 数据源3: 500彩票网
# ==========================================
def fetch_500():
    """500彩票网历史数据"""
    try:
        url = 'https://datachart.500.com/plw/history/newinc/history.php?start=26001&end=26999'
        html, _ = http_get(url)
        if not html:
            return None, None
        
        # 找最新一行数据: 26167  0  1  2  3  1
        rows = re.findall(r'(\d{5})\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', html)
        if rows:
            last = rows[-1]
            period = int('20' + last[0])
            digits = ''.join(last[1:])
            if 2026000 < period < 2027000:
                return digits[:4], period
    except Exception as e:
        log(f'  500彩票网异常: {e}')
    return None, None

# ==========================================
# 数据源4: 体彩官方API
# ==========================================
def fetch_sporttery():
    """体彩官方API"""
    try:
        url = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&isVerify=1&pageNo=1'
        html, _ = http_get(url, timeout=10)
        if not html:
            return None, None
        data = json.loads(html)
        if data.get('errorCode') == '0':
            records = data.get('value', {}).get('list', [])
            if records:
                r = records[0]
                num = r.get('lotteryDrawResult', '')
                period = int(r.get('lotteryDrawNum', 0))
                if num and period:
                    digits = num.replace(' ', '')
                    return digits[:4], period
    except Exception as e:
        log(f'  体彩API异常: {e}')
    return None, None

# ==========================================
# 数据源5: 缓存兜底
# ==========================================
def fetch_cache():
    """从本地数据文件读取上次成功获取的开奖号码作为兜底"""
    try:
        if os.path.exists(DATA_FILE):
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            winning = data.get('winning', '')
            period = data.get('period', 0)
            if winning and period:
                log(f'  缓存兜底: 期{period} 号{winning}')
                return winning, period
    except:
        pass
    return None, None

# ==========================================
# GitHub API 操作
# ==========================================
def github_get(path):
    token = os.environ.get('GH_TOKEN', '')
    if not token:
        log('❌ GH_TOKEN 未设置')
        return None, None
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{path}',
                  headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'})
    resp = urlopen(req, timeout=30, context=ctx)
    info = json.loads(resp.read().decode())
    return info['sha'], json.loads(base64.b64decode(info['content']).decode('utf-8'))

def github_put(path, content_dict, sha, message):
    token = os.environ.get('GH_TOKEN', '')
    content_b64 = base64.b64encode(json.dumps(content_dict, ensure_ascii=False, indent=2).encode('utf-8')).decode('utf-8')
    payload = {'message': message, 'content': content_b64, 'sha': sha}
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{path}',
                  data=json.dumps(payload).encode('utf-8'),
                  headers={'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json',
                           'Content-Type': 'application/json'},
                  method='PUT')
    resp = urlopen(req, timeout=30, context=ctx)
    return json.loads(resp.read().decode())

# ==========================================
# 主流程
# ==========================================
def main():
    log('===== 排列5开奖号码获取 v9 =====')
    
    # 获取当前数据
    try:
        sha, data = github_get(DATA_FILE)
    except Exception as e:
        log(f'❌ 读取数据失败: {e}')
        sys.exit(1)
    
    current_period = data.get('period', 0)
    current_winning = data.get('winning', '')
    log(f'当前期号: {current_period}, 开奖号: {current_winning or "未开奖"}')
    
    # 如果已开奖，跳过
    if current_winning:
        log('已开奖，无需获取')
        return True
    
    # 依次尝试数据源
    sources = [
        ('Vercel代理API', fetch_vercel),
        ('彩经网移动端', fetch_cjcp),
        ('江苏体彩网', fetch_js_lottery),
        ('500彩票网', fetch_500),
        ('体彩官方API', fetch_sporttery),
        ('缓存兜底', fetch_cache),
    ]
    
    winning4 = None
    source_name = None
    
    for name, fn in sources:
        log(f'尝试: {name}...')
        try:
            w, p = fn()
            if w and p:
                # 期号校验
                if abs(p - current_period) > 10:
                    log(f'  期号不匹配 (获取{p}, 当前{current_period}), 跳过')
                    continue
                winning4 = w
                source_name = name
                log(f'  ✅ 成功! 期号{p} 前4位{winning4}')
                break
        except Exception as e:
            log(f'  ❌ {e}')
            continue
    
    if not winning4:
        log('❌ 所有数据源均失败')
        sys.exit(1)
    
    # 更新数据
    data['winning'] = winning4
    data['hits'] = {}
    data['lastUpdate'] = int(datetime.now().timestamp() * 1000)
    data['version'] = int(time.time())
    
    # 更新 history
    history = data.get('history', [])
    for h in history:
        if h['period'] == current_period:
            h['winning'] = winning4
            break
    else:
        history.insert(0, {
            'period': current_period,
            'winning': winning4,
            'time': datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S'),
            'hits': {}
        })
        history.sort(key=lambda x: x['period'], reverse=True)
        if len(history) > 7:
            history = history[:7]
    data['history'] = history
    
    # 推送数据
    try:
        result = github_put(DATA_FILE, data, sha, f'更新开奖号码: {winning4} (期号: {current_period}, 来源: {source_name})')
        log(f'✅ 数据已推送: {result["content"]["sha"][:8]}')
    except Exception as e:
        log(f'❌ 推送失败: {e}')
        sys.exit(1)
    
    # 更新 index.html
    try:
        sha2, _ = github_get('index.html')
        html_sha = sha2
        
        # 读取当前html
        req = Request(f'https://api.github.com/repos/{REPO}/contents/index.html',
                      headers={'Authorization': f'token {os.environ.get("GH_TOKEN", "")}',
                               'Accept': 'application/vnd.github.v3+json'})
        resp = urlopen(req, timeout=30, context=ctx)
        html_info = json.loads(resp.read().decode())
        html = base64.b64decode(html_info['content']).decode('utf-8')
        
        # 替换 let S
        embedded = json.dumps(data, ensure_ascii=False)
        let_start = html.find('let S =')
        next_func = html.find('function calcAutoPeriod', let_start)
        old_block = html[let_start:next_func]
        new_block = f'let S = {embedded};\n\n'
        html = html.replace(old_block, new_block)
        
        content_b64 = base64.b64encode(html.encode('utf-8')).decode('utf-8')
        payload = {
            'message': f'同步开奖数据: {winning4}',
            'content': content_b64,
            'sha': html_info['sha']
        }
        req2 = Request(f'https://api.github.com/repos/{REPO}/contents/index.html',
                       data=json.dumps(payload).encode('utf-8'),
                       headers={'Authorization': f'token {os.environ.get("GH_TOKEN", "")}',
                                'Accept': 'application/vnd.github.v3+json',
                                'Content-Type': 'application/json'},
                       method='PUT')
        resp2 = urlopen(req2, timeout=30, context=ctx)
        result2 = json.loads(resp2.read().decode())
        log(f'✅ index.html 已更新: {result2["content"]["sha"][:8]}')
    except Exception as e:
        log(f'⚠️ index.html 更新失败: {e} (数据已保存)')
    
    log(f'===== 完成: 期{current_period} 前4位{winning4} ({source_name}) =====')
    return True

if __name__ == '__main__':
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        log(f'❌ 未捕获异常: {traceback.format_exc()}')
        sys.exit(1)
