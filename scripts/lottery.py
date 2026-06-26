#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
神仙连 - 每日开奖号码自动填入脚本 v5
数据源优先级：
1. 彩经网移动端 m.cjcp.cn（服务器渲染HTML，已验证可用）
2. 江苏体彩网 api.js-lottery.com（服务器渲染HTML）
3. 体彩官方API（备用）

v5 修复：同时更新 let S 变量和 embedded-data script 标签
"""

import json
import os
import base64
import ssl
import re
from datetime import datetime
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)

def _make_request(url, timeout=20, parse_json=False, extra_headers=None):
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

# ==========================================
#  数据源1：彩经网移动端（服务器渲染，已验证）
# ==========================================

def fetch_from_cjcp():
    """从彩经网移动端获取开奖号码 - 服务器渲染HTML"""
    log("尝试彩经网移动端...")
    
    html = _make_request('https://m.cjcp.cn/kaijiang/pl5/', timeout=20)
    if not html or len(html) < 5000:
        log("  彩经网返回内容过短")
        return None, None
    
    # 提取期号：<em>2026166期开奖</em>
    period_m = re.search(r'(\d{7})期开奖', html)
    if not period_m:
        log("  未找到期号")
        return None, None
    
    our_period = int(period_m.group(1))
    
    # 提取开奖号码：<span class="qiu_red">2</span>... 格式
    period_pos = period_m.start()
    segment = html[period_pos:period_pos+5000]
    
    num_matches = re.findall(r'<span class="qiu_red">(\d)</span>', segment)
    if len(num_matches) >= 5:
        digits = ''.join(num_matches[:5])
        winning4 = digits[:4]
        log(f"  彩经网成功: 期{our_period} 号码{digits} -> {winning4}")
        return winning4, our_period
    
    # 备用匹配
    num_m = re.search(r'(\d{7})期开奖.*?(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', segment, re.DOTALL)
    if num_m:
        digits = ''.join(num_m.groups()[1:6])
        winning4 = digits[:4]
        log(f"  彩经网备用成功: 期{our_period} 号码{digits} -> {winning4}")
        return winning4, our_period
    
    log("  彩经网解析失败")
    return None, None

# ==========================================
#  数据源2：江苏体彩网（服务器渲染）
# ==========================================

def fetch_from_jslottery():
    """从江苏体彩网获取开奖公告"""
    log("尝试江苏体彩网...")
    
    html = _make_request('https://api.js-lottery.com/', timeout=20)
    if not html or len(html) < 3000:
        return None, None
    
    links = re.findall(r'href="(/cms/post-\d+\.html)"', html)
    
    for link in links[:15]:
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

# ==========================================
#  数据源3：体彩官方API（备用）
# ==========================================

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

# ==========================================
#  主获取函数
# ==========================================

def fetch_winning_number():
    """多源获取最新开奖号码，返回 (4位数字, 期号) 或 (None, None)"""
    
    sources = [
        ('彩经网移动端', fetch_from_cjcp),
        ('江苏体彩网', fetch_from_jslottery),
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

# ==========================================
#  match_balanced_braces - 匹配平衡的大括号
# ==========================================

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

# ==========================================
#  更新 index.html - v5 同时更新 let S 和 embedded-data
# ==========================================

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
        
        new_html = html_content
        updated = False
        
        # ============================================================
        # 方式1：更新 embedded-data script 标签
        # ============================================================
        target = '<script id="embedded-data" type="application/json">'
        idx = html_content.find(target)
        if idx >= 0:
            brace_start = idx + len(target)
            matched = match_balanced_braces(html_content, brace_start)
            if matched:
                json_end = brace_start + len(matched)
                new_html = new_html[:brace_start] + s_json + new_html[json_end:]
                updated = True
                log("embedded-data 标签已更新")
            else:
                log("无法匹配 embedded-data 中的大括号")
        else:
            log("未找到 embedded-data script 标签")
        
        # ============================================================
        # 方式2：更新 let S = {...} 变量（页面实际使用的数据）
        # ============================================================
        # 查找 let S = {...};
        s_match = re.search(r'let\s+S\s*=\s*\{', new_html)
        if s_match:
            brace_start = s_match.end() - 1  # 指向 {
            matched = match_balanced_braces(new_html, brace_start)
            if matched:
                json_end = brace_start + len(matched)
                new_html = new_html[:brace_start] + s_json + new_html[json_end:]
                updated = True
                log("let S 变量已更新")
            else:
                log("无法匹配 let S 中的大括号")
        else:
            # 备用：var S = {...};
            s_match = re.search(r'var\s+S\s*=\s*\{', new_html)
            if s_match:
                brace_start = s_match.end() - 1
                matched = match_balanced_braces(new_html, brace_start)
                if matched:
                    json_end = brace_start + len(matched)
                    new_html = new_html[:brace_start] + s_json + new_html[json_end:]
                    updated = True
                    log("var S 变量已更新")
            else:
                log("未找到 let S = 或 var S = 变量")
        
        if not updated or new_html == html_content:
            log("index.html 无需更新")
            return True
        
        encoded = base64.b64encode(new_html.encode('utf-8')).decode('utf-8')
        body = json.dumps({
            'message': 'auto: update embedded data and let S in index.html',
            'content': encoded,
            'sha': html_sha
        }).encode('utf-8')
        put_req = Request(
            f'https://api.github.com/repos/{REPO}/contents/index.html',
            data=body, method='PUT', headers=headers2
        )
        resp2 = urlopen(put_req, timeout=30)
        if resp2.status == 200:
            log("index.html 已更新（embedded-data + let S）")
            return True
        log(f"index.html更新失败: HTTP {resp2.status}")
        return False
    except Exception as e:
        log(f"更新index.html异常: {e}")
        return False

# ==========================================
#  数据读写
# ==========================================

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
    log("神仙连开奖号码自动填入任务开始 v5 (修复let S + 彩经网)")
    
    winning4, api_period = fetch_winning_number()
    if not winning4:
        log("所有数据源均未获取到开奖号码，跳过")
        return True
    
    data = load_data()
    current_period = data.get('period', 0)
    current_winning = data.get('winning', '')
    
    log(f"当前期数: {current_period}, 当前开奖号: {'(空)' if not current_winning else current_winning}")
    log(f"新获取到期号: {api_period}, 开奖号: {winning4}")
    
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
