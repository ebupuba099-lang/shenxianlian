#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日自动生成脚本
直接用GitHub Contents API读写repo数据文件
"""

import json
import random
import os
import base64
from datetime import datetime
import os
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

BASE_DATE = datetime(2026, 5, 11)

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)


def match_balanced_braces(text, start):
    """从start位置开始，匹配平衡的花括号，返回匹配的字符串"""
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
    """更新index.html里的初始S对象，确保页面打开就能显示最新数据"""
    import re
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
        new_s = 'let S = ' + s_json + ';'
        
        # 找到 'let S = ' 的位置，用平衡花括号匹配完整的 S 对象
        target = 'let S = '
        idx = html_content.find(target)
        if idx < 0:
            log("未找到 'let S = '，无法更新")
            return False
        
        # 跳过 'let S = '，从 '{' 开始匹配
        brace_start = idx + len(target)
        matched = match_balanced_braces(html_content, brace_start)
        if not matched:
            log("无法匹配 S 对象的平衡花括号")
            return False
        
        old_s = matched
        new_html = html_content.replace(old_s, new_s, 1)
        
        if new_html == html_content:
            log("index.html无需更新")
            return True
        
        encoded = base64.b64encode(new_html.encode('utf-8')).decode('utf-8')
        body = json.dumps({
            'message': 'auto: update initial S data in index.html',
            'content': encoded,
            'sha': html_sha
        }).encode('utf-8')
        put_req = Request(
            f'https://api.github.com/repos/{REPO}/contents/index.html',
            data=body, method='PUT', headers=headers2
        )
        resp2 = urlopen(put_req, timeout=30)
        if resp2.status == 200:
            log("index.html初始数据已更新")
            return True
        else:
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
    body = json.dumps({'message': 'auto: generate new period', 'content': b64, 'sha': sha}).encode('utf-8')
    put_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', data=body, method='PUT', headers=headers)
    resp = urlopen(put_req, timeout=30)
    return resp.status == 200

def generate_decreasing_sequence():
    digits = list(range(10))
    random.shuffle(digits)
    selected = digits[:9]
    sequences = [''.join(str(d) for d in selected)]
    current = list(selected)
    while len(current) > 1:
        idx = random.randint(0, len(current) - 1)
        current.pop(idx)
        sequences.append(''.join(str(d) for d in current))
    # 返回空格分隔字符串，前端updatePreview()期望此格式
    return ' '.join(sequences)

def main():
    log("=" * 50)
    log("神仙连自动生成任务开始")
    
    data = load_data()
    
    today = datetime.now()
    days_diff = (today - BASE_DATE).days
    today_period = 2026121 + days_diff
    
    current_period = data.get('period', 0)
    log(f"当前期数: {current_period}, 历史记录: {len(data.get('history',[]))}条")
    
    auto_period = today_period
    log(f"自动计算期数: {auto_period}")
    
    if current_period >= auto_period:
        log(f"当前期{current_period}已是最新的{auto_period}，无需生成")
        return True
    
    qian = generate_decreasing_sequence()
    bai = generate_decreasing_sequence()
    shi = generate_decreasing_sequence()
    ge = generate_decreasing_sequence()
    
    # 保存当前期到历史（如果有开奖号）
    if current_period > 0:
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == current_period]
        if not existing:
            hist_entry = {
                'period': current_period,
                'sequences': data.get('sequences', {}),
                'winning': data.get('winning', ''),
                'hits': data.get('hits', {})
            }
            history.insert(0, hist_entry)
            if len(history) > 7:
                history = history[:10]
            data['history'] = history
    
    data['period'] = auto_period
    data['sequences'] = {'千': qian, '百': bai, '十': shi, '个': ge}
    data['winning'] = ''
    data['hits'] = {}
    
    log(f"新期 {auto_period} 生成完成")
    log(f"  千: {' '.join(qian[:3])}")
    log(f"  百: {' '.join(bai[:3])}")
    log(f"  十: {' '.join(shi[:3])}")
    log(f"  个: {' '.join(ge[:3])}")
    
    try:
        success = save_data(data)
        if success:
            log(f"推送成功！新期: {auto_period}")
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
