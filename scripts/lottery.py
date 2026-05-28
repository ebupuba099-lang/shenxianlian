#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日开奖号码自动填入脚本
直接用GitHub Contents API读写repo数据文件，含期号校验
"""

import json
import os
import base64
from datetime import datetime
import time
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

SPORTTERY_URL = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0'
HUINIAO_URL = 'http://api.huiniao.top/interface/home/lotteryHistory?type=plw&page=1&limit=1'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)



def calc_hits(sequences, winning):
    """计算各位置命中粒数"""
    if not winning or len(winning) != 4:
        return {}
    hits = {}
    for pos in ['千', '百', '十', '个']:
        seq = sequences.get(pos, [])
        if not seq:
            hits[pos] = 0
            continue
        w = winning
        count = 0
        # 9级递减序列，取每级第一个数字（最长的那个）
        full_seq = seq[0] if seq else ''
        for i, d in enumerate(w):
            if i < len(full_seq) and full_seq[i] == d:
                count += 1
        hits[pos] = count
    return hits

def update_index_html(data):
    """更新index.html里的embedded-data script标签，确保页面打开就能显示最新数据"""
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
        html_content = sha_data['content'].decode('utf-8') if isinstance(sha_data['content'], bytes) else sha_data['content']
        
        # 构建完整数据
        full_data = {
            'period': data.get('period', 0),
            'winning': data.get('winning', ''),
            'sequences': data.get('sequences', {}),
            'history': data.get('history', []),
            'hits': data.get('hits', {}),
            'lastUpdate': data.get('lastUpdate', int(time.time() * 1000))
        }
        data_json = json.dumps(full_data, ensure_ascii=False, separators=(',', ':'))
        
        # 替换 embedded-data script 内容
        new_html = re.sub(
            r'(<script id="embedded-data"[^>]*>)(.*?)(</script>)',
            r'\g<1>' + data_json + r'\g<3>',
            html_content,
            count=1,
            flags=re.DOTALL
        )
        
        if new_html == html_content:
            # 尝试另一种方式：直接替换 let S = {...};
            # 匹配 "let S = " 后面一直到 "}; --> 的内容
            pattern = r'(let S = \(function\(\) \{[^}]+return )(\{[^}]+\})(\};?\s*\}\)\(\);)'
            match = re.search(r'let S = \(function\(\) \{[^}]+return (\{.*\});?\s*\}\)\(\);', html_content, re.DOTALL)
            if match:
                new_s = r'let S = (function() { var el = document.getElementById("embedded-data"); if (el) { try { return JSON.parse(el.textContent); } catch(e) {} } return ' + data_json + r'; })();'
                new_html = re.sub(r'let S = \(function\(\) \{[^}]+return \{[^}]+\};?\s*\}\)\(\);', new_s, html_content, count=1, flags=re.DOTALL)
            
        if new_html == html_content:
            log("index.html无需更新（无变化）")
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
            log("index.html内嵌数据已更新")
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
    body = json.dumps({'message': 'auto: update lottery result', 'content': b64, 'sha': sha}).encode('utf-8')
    put_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', data=body, method='PUT', headers=headers)
    resp = urlopen(put_req, timeout=30)
    return resp.status == 200

def fetch_winning_number():
    """获取最新开奖号码，返回 (4位数字, API期号) 或 (None, None)"""
    try:
        req = Request(SPORTTERY_URL, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Referer': 'https://www.lottery.gov.cn/',
            'Accept': 'application/json'
        })
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        if data.get('value') and data['value'].get('list'):
            latest = data['value']['list'][0]
            result = latest.get('lotteryDrawResult', '')
            draw_num = latest.get('lotteryDrawNum', '')
            if result:
                digits = result.replace(' ', '')
                if len(digits) >= 4:
                    winning4 = digits[:4]
                    period = int('20' + draw_num) if draw_num else None
                    log(f"体彩官方: 期号={draw_num}(→{period}), 号码={result}")
                    return winning4, period
    except Exception as e:
        log(f"体彩官方失败: {e}")
    
    try:
        req = Request(HUINIAO_URL, headers={
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        d = data.get('data', {})
        last = None
        if isinstance(d, dict):
            last = d.get('last')
            if not last and d.get('data', {}).get('list'):
                last = d['data']['list'][0]
        elif isinstance(d, list) and len(d) > 0:
            last = d[0]
        if last:
            code = last.get('code', '')
            one, two, three, four = last.get('one',''), last.get('two',''), last.get('three',''), last.get('four','')
            winning4 = f"{one}{two}{three}{four}"
            period = int('20' + code) if code else None
            if len(winning4) == 4 and winning4.isdigit():
                log(f"灰鸟API: 期号={code}(→{period}), 号码={one}{two}{three}{four}{last.get('five','')}")
                return winning4, period
    except Exception as e:
        log(f"灰鸟API失败: {e}")
    
    return None, None

def main():
    log("=" * 50)
    log("神仙连开奖号码自动填入任务开始")
    
    winning4, api_period = fetch_winning_number()
    if not winning4:
        log("所有API均未获取到开奖号码，跳过")
        return True
    
    data = load_data()
    current_period = data.get('period', 0)
    current_winning = data.get('winning', '')
    
    log(f"当前期数: {current_period}, 当前开奖号: {'(空)' if not current_winning else current_winning}")
    log(f"API期号: {api_period}, 开奖号: {winning4}")
    
    # 校验：API返回的期号必须与当前期匹配，且当前期无开奖号
    if current_winning:
        log(f"当前期已有开奖号 {current_winning}，跳过")
        return True
    
    if api_period and current_period != api_period:
        log(f"期号不匹配: 当前={current_period}, API={api_period}，跳过")
        return True
    
    data['winning'] = winning4
    hits = calc_hits(data.get('sequences', {}), winning4)
    data['hits'] = hits
    log(f"计算命中: {hits}")
    
    # 同时更新当前期的历史记录中的命中
    current_period = data.get('period', 0)
    history = data.get('history', [])
    for h in history:
        if h.get('period') == current_period:
            h['winning'] = winning4
            h['hits'] = hits
            break
    
    log(f"填入开奖号 {winning4}")
    
    try:
        success = save_data(data)
        if success:
            data['lastUpdate'] = int(time.time() * 1000)
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
