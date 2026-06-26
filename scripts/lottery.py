#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
神仙连 - 每日开奖号码自动填入脚本 v3
通过百度搜索爬取开奖号码（服务端渲染，绕过API拦截）
备用：东方财富网、江苏体彩网、体彩官方API
"""

import json
import os
import base64
import ssl
import re
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.parse import quote

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)

def _make_request(url, timeout=15, parse_json=False, extra_headers=None):
    """通用请求函数"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
    }
    if extra_headers:
        headers.update(extra_headers)
    req = Request(url, headers=headers)
    try:
        resp = urlopen(req, timeout=timeout, context=ctx)
        raw = resp.read().decode('utf-8', errors='replace')
        if parse_json:
            return json.loads(raw)
        return raw
    except Exception as e:
        log(f"  请求失败 [{url[:60]}]: {e}")
        return None

# ============================================================
#  数据源1：百度搜索（最可靠，服务端渲染HTML）
# ============================================================

def fetch_from_baidu():
    """从百度搜索结果提取排列五开奖号码（服务端渲染HTML，不会被拦截）"""
    log("尝试百度搜索...")
    
    url = 'https://www.baidu.com/s?wd=' + quote('排列五开奖号码')
    html = _make_request(url, timeout=20, extra_headers={
        'Referer': 'https://www.baidu.com/',
    })
    if not html or len(html) < 5000:
        log("  百度返回内容过短，可能被拦截")
        return None, None
    
    # 精准匹配：期号和号码在200字符内，期号格式如 "26166期"
    # 百度卡片中最新一期排在最前面，所以取第一个匹配
    pattern = r'(\d{5})期.{0,200}?(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)'
    matches = re.findall(pattern, html, re.DOTALL)
    
    if matches:
        # 第一个匹配是最新一期（百度卡片中最新期排最前）
        m = matches[0]
        period_str = m[0]
        digits = ''.join(m[1:6])
        if len(digits) == 5 and digits.isdigit():
            our_period = int('20' + period_str) if len(period_str) <= 5 else int(period_str)
            winning4 = digits[:4]
            log(f"  百度解析成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period
    
    # 备用正则：匹配 "第XXXXX期"
    pattern2 = r'第\s*(\d{5})\s*期.{0,300}?(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)'
    matches2 = re.findall(pattern2, html, re.DOTALL)
    if matches2:
        m = matches2[0]
        period_str = m[0]
        digits = ''.join(m[1:6])
        if len(digits) == 5 and digits.isdigit():
            our_period = int('20' + period_str) if len(period_str) <= 5 else int(period_str)
            winning4 = digits[:4]
            log(f"  百度备用解析成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period
    
    log("  百度解析失败: 未匹配到开奖数据")
    return None, None

# ============================================================
#  数据源2：江苏体彩网（服务端渲染，直接含开奖号码）
# ============================================================

def fetch_from_jslottery():
    """从江苏体彩网获取最新排列五开奖公告（服务端渲染）"""
    log("尝试江苏体彩网...")
    
    html = _make_request('https://api.js-lottery.com/', timeout=20)
    if not html or len(html) < 3000:
        return None, None
    
    # 找所有文章链接
    links = re.findall(r'href="(/cms/post-\d+\.html)"', html)
    
    for link in links[:15]:  # 最多检查前15个
        full_url = 'https://api.js-lottery.com' + link
        detail = _make_request(full_url, timeout=15)
        if not detail or '排列5' not in detail:
            continue
        
        num_m = re.search(r'开奖号码[：:]\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', detail)
        period_m = re.search(r'第\s*(\d{5})\s*期', detail)
        
        if num_m and period_m:
            digits = ''.join(num_m.groups())
            our_period = int('20' + period_m.group(1))
            winning4 = digits[:4]
            log(f"  江苏体彩网成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period
    
    log("  江苏体彩网未找到排列五开奖公告")
    return None, None

# ============================================================
#  数据源3：东方财富网（通过 web_fetch 验证过可用）
# ============================================================

def fetch_from_eastmoney():
    """从东方财富网获取开奖号码（备用）"""
    log("尝试东方财富网...")
    
    html = _make_request('https://caipiao.eastmoney.com/pub/Result/Category/pl5', timeout=20)
    if not html or len(html) < 5000:
        return None, None
    
    # 匹配期号和号码在同一上下文
    pattern = r'(\d{5})期.{0,200}?(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)'
    m = re.search(pattern, html, re.DOTALL)
    if m:
        period_str = m.group(1)
        digits = ''.join(m.groups()[1:6])
        if len(digits) == 5 and digits.isdigit():
            our_period = int('20' + period_str)
            winning4 = digits[:4]
            log(f"  东方财富网成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period
    
    log("  东方财富网解析失败")
    return None, None

# ============================================================
#  数据源4：体彩官方API（备用）
# ============================================================

def fetch_from_sporttery():
    """从体彩官方API获取"""
    log("尝试体彩官方API...")
    result = _make_request(
        'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0',
        timeout=15, parse_json=True
    )
    if result:
        try:
            if result.get('value') and result['value'].get('list'):
                latest = result['value']['list'][0]
                result_str = latest.get('lotteryDrawResult', '')
                draw_num = latest.get('lotteryDrawNum', '')
                if result_str:
                    digits = result_str.replace(' ', '')
                    if len(digits) >= 4:
                        period = int('20' + draw_num) if draw_num else None
                        log(f"  体彩官方API成功: 期{period} 号码{result_str}")
                        return digits[:4], period
        except Exception as e:
            log(f"  体彩官方API解析失败: {e}")
    return None, None

# ============================================================
#  主获取函数
# ============================================================

def fetch_winning_number():
    """多源获取最新开奖号码，返回 (4位数字, 期号) 或 (None, None)"""
    
    # 数据源按优先级排序
    sources = [
        ('百度搜索', fetch_from_baidu),
        ('江苏体彩网', fetch_from_jslottery),
        ('东方财富网', fetch_from_eastmoney),
        ('体彩官方API', fetch_from_sporttery),
    ]
    
    for name, func in sources:
        try:
            winning4, period = func()
            if winning4 and period:
                log(f"{name}成功获取: 期号={period}, 号码={winning4}")
                return winning4, period
        except Exception as e:
            log(f"{name}异常: {e}")
    
    log("所有数据源均未获取到开奖号码")
    return None, None

# ============================================================
#  数据读写与更新
# ============================================================

def match_balanced_braces(text, start):
    count = 0
    for i in range(start, len(text)):
        if text[i] == '{':
            count += 1
        elif text[i] == '}':
            count -= 1
            if count == 0:
                return text[start:i+1]
    return None

def update_index_html(data):
    try:
        headers2 = {
            'Authorization': f'token {GH_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        sha_req = Request(f'https://api.github.com/repos/{REPO}/contents/index.html', headers=headers2)
        sha_resp = urlopen(sha_req, timeout=30)
        sha_data = json.loads(sha_resp.read().decode('utf-8'))
        html_sha = sha_data['sha']
        html_content = base64.b64decode(sha_data['content']).decode('utf-8')
        
        s_obj = {
            'period': data.get('period', 0),
            'winning': data.get('winning', ''),
            'sequences': data.get('sequences', {}),
            'history': data.get('history', [])
        }
        s_json = json.dumps(s_obj, ensure_ascii=False, separators=(',', ':'))
        target = '<script id="embedded-data" type="application/json">'
        idx = html_content.find(target)
        if idx < 0:
            log("未找到 embedded-data script 标签")
            return False
        
        brace_start = idx + len(target)
        matched = match_balanced_braces(html_content, brace_start)
        if not matched:
            log("无法匹配 S 对象")
            return False
        
        json_end = brace_start + len(matched)
        new_html = html_content[:brace_start] + s_json + html_content[json_end:]
        
        if new_html == html_content:
            return True
        
        encoded = base64.b64encode(new_html.encode('utf-8')).decode('utf-8')
        body = json.dumps({
            'message': 'auto: update embedded data in index.html',
            'content': encoded,
            'sha': html_sha
        }).encode('utf-8')
        put_req = Request(
            f'https://api.github.com/repos/{REPO}/contents/index.html',
            data=body, method='PUT', headers=headers2
        )
        resp2 = urlopen(put_req, timeout=30)
        if resp2.status == 200:
            log("index.html 已更新")
            return True
        log(f"index.html更新失败: HTTP {resp2.status}")
        return False
    except Exception as e:
        log(f"更新index.html异常: {e}")
        return False

def load_data():
    headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3.raw'}
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read().decode('utf-8'))

def save_data(data):
    headers = {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    }
    sha_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
    sha_resp = urlopen(sha_req, timeout=30)
    sha = json.loads(sha_resp.read().decode('utf-8'))['sha']
    content = json.dumps(data, ensure_ascii=False)
    b64 = base64.b64encode(content.encode('utf-8')).decode()
    body = json.dumps({'message': 'auto: update lottery result', 'content': b64, 'sha': sha}).encode('utf-8')
    put_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', data=body, method='PUT', headers=headers)
    resp = urlopen(put_req, timeout=30)
    return resp.status == 200

def calc_hits(sequences, winning):
    hits = {}
    if not winning or len(winning) != 4:
        return hits
    positions = ['千', '百', '十', '个']
    for i, pos in enumerate(positions):
        seq = sequences.get(pos, '')
        if not seq:
            hits[pos] = 0
            continue
        nums = seq.split(' ')
        target = winning[i]
        hit_level = 0
        for j in range(len(nums) - 1, -1, -1):
            if target in nums[j]:
                hit_level = len(nums[j])
                break
        hits[pos] = hit_level
    return hits

def main():
    log("=" * 50)
    log("神仙连开奖号码自动填入任务开始 v3 (百度搜索版)")
    
    winning4, api_period = fetch_winning_number()
    if not winning4:
        log("所有数据源均未获取到开奖号码，跳过")
        log("可能原因: 所有源均不可用或网络问题")
        return True
    
    data = load_data()
    current_period = data.get('period', 0)
    current_winning = data.get('winning', '')
    
    log(f"当前期数: {current_period}, 当前开奖号: {'(空)' if not current_winning else current_winning}")
    log(f"爬取到期号: {api_period}, 开奖号: {winning4}")
    
    if current_winning:
        log(f"当前期已有开奖号 {current_winning}，跳过")
        return True
    
    if api_period == current_period:
        target_period = current_period
    else:
        target_period = api_period
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == target_period]
        if existing and existing[0].get('winning'):
            log(f"期{target_period}已有开奖号 {existing[0]['winning']}，跳过")
            return True
        log(f"开奖号属于期{target_period}，非当前期{current_period}，填入历史")
    
    if target_period == current_period:
        data['winning'] = winning4
        hits = calc_hits(data.get('sequences', {}), winning4)
        data['hits'] = hits
        log(f"填入当前期 {current_period} 开奖号 {winning4}, 命中: {hits}")
    else:
        hits = calc_hits({}, winning4)
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == target_period]
        if existing:
            existing[0]['winning'] = winning4
            if not existing[0].get('hits') or existing[0]['hits'] == {}:
                if existing[0].get('sequences'):
                    existing[0]['hits'] = calc_hits(existing[0]['sequences'], winning4)
                else:
                    existing[0]['hits'] = hits
            log(f"填入历史期 {target_period} 开奖号 {winning4}")
        else:
            hist_entry = {
                'period': target_period,
                'winning': winning4,
                'hits': hits
            }
            history.insert(0, hist_entry)
            if len(history) > 7:
                history = history[:7]
            data['history'] = history
            log(f"新建历史期 {target_period} 开奖号 {winning4}")
    
    if target_period == current_period and data.get('sequences') and data.get('winning'):
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == current_period]
        if not existing:
            hist_entry = {
                'period': current_period,
                'sequences': data.get('sequences', {}),
                'winning': winning4,
                'hits': data.get('hits', {})
            }
            history.insert(0, hist_entry)
            if len(history) > 7:
                history = history[:7]
            data['history'] = history
    
    try:
        success = save_data(data)
        if success:
            log(f"推送成功！期{current_period} 开奖{winning4} 已更新")
            update_index_html(data)
        else:
            log("推送失败")
    except Exception as e:
        log(f"推送异常: {e}")
    
    log("任务完成")
    return True

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
