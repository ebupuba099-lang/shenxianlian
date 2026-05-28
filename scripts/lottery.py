#!/usr/bin/env python3
"""获取排列3/排列5开奖号码，填入winning为空的记录（校验期号匹配）"""
import json
import os
import base64
import requests
from datetime import datetime

GH_TOKEN = os.environ.get('GH_TOKEN', '')
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

SPORTTERY_API = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0'
HUINIAO_API = 'http://api.huiniao.top/interface/home/lotteryHistory?type=plw&page=1&limit=1'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)

def load_data():
    headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3.raw'}
    resp = requests.get(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
    resp.raise_for_status()
    return resp.json()

def save_data(data):
    headers = {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github.v3+json'
    }
    sha_resp = requests.get(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
    sha_resp.raise_for_status()
    sha = sha_resp.json()['sha']
    content = json.dumps(data, ensure_ascii=False)
    b64 = base64.b64encode(content.encode('utf-8')).decode()
    put_resp = requests.put(
        f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}',
        headers=headers,
        json={'message': 'auto: update lottery results', 'content': b64, 'sha': sha}
    )
    put_resp.raise_for_status()

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
    try:
        headers2 = {
            'Authorization': f'token {GH_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        sha_resp = requests.get(f'https://api.github.com/repos/{REPO}/contents/index.html', headers=headers2)
        sha_resp.raise_for_status()
        sha_data = sha_resp.json()
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
        
        old_s = target + matched  # FIX: include the prefix so replacement is correct
        new_html = html_content.replace(old_s, new_s, 1)
        
        if new_html == html_content:
            log("index.html无需更新")
            return True
        
        encoded = base64.b64encode(new_html.encode('utf-8')).decode('utf-8')
        body = json.dumps({
            'message': 'auto: update initial S data in index.html',
            'content': encoded,
            'sha': html_sha
        })
        put_resp = requests.put(
            f'https://api.github.com/repos/{REPO}/contents/index.html',
            headers=headers2,
            data=body.encode('utf-8')
        )
        if put_resp.status_code == 200:
            log("index.html初始数据已更新")
            return True
        else:
            log(f"index.html更新失败: HTTP {put_resp.status_code}")
            return False
    except Exception as e:
        log(f"更新index.html异常: {e}")
        return False

def fetch_winning_number():
    """尝试从多个API获取最新开奖号码，返回 (4位数字字符串, 期号数字) 或 (None, None)"""
    # 方案1: 体育彩票官方API
    try:
        resp = requests.get(SPORTTERY_API, timeout=10)
        data = resp.json()
        if data.get('value') and data['value'].get('list'):
            latest = data['value']['list'][0]
            result = latest.get('lotteryDrawResult', '')
            draw_num = latest.get('lotteryDrawNum', '')
            if result:
                digits = result.replace(' ', '')
                if len(digits) >= 4:
                    winning4 = digits[:4]
                    period = None
                    if draw_num:
                        period = int('20' + draw_num)
                    log(f"官方API获取成功: 期号={draw_num}(→{period}), 号码={result}, 取前4位={winning4}")
                    return winning4, period
    except Exception as e:
        log(f"官方API失败: {e}")

    # 方案2: 灰鸟API
    try:
        resp = requests.get(HUINIAO_API, timeout=10)
        data = resp.json()
        if data.get('data'):
            last = None
            if isinstance(data['data'], dict):
                last = data['data'].get('last')
                if not last and data['data'].get('data', {}).get('list'):
                    last = data['data']['data']['list'][0]
            elif isinstance(data['data'], list) and len(data['data']) > 0:
                last = data['data'][0]
            if last:
                one = last.get('one', '')
                two = last.get('two', '')
                three = last.get('three', '')
                four = last.get('four', '')
                winning4 = f"{one}{two}{three}{four}"
                code = last.get('code', '')
                period = None
                if code:
                    period = int('20' + code)
                if len(winning4) == 4 and winning4.isdigit():
                    log(f"灰鸟API获取成功: 期号={code}(→{period}), 号码={one}{two}{three}{four}{last.get('five','')}")
                    return winning4, period
    except Exception as e:
        log(f"灰鸟API失败: {e}")

    return None, None

def main():
    log("神仙连开奖号码自动填入任务开始")
    
    winning4, api_period = fetch_winning_number()
    if not winning4:
        log("所有API均未获取到开奖号码，跳过")
        return

    data = load_data()
    
    rec_period = data.get('period')
    if api_period and rec_period != api_period:
        log(f"期号不匹配: API期号={api_period}, 数据期号={rec_period}, 跳过")
        return
    
    if data.get('winning'):
        log(f"期{rec_period}已有开奖号{data['winning']}，无需填入")
        return
    
    data['winning'] = winning4
    
    # Calculate hits
    sequences = data.get('sequences', {})
    hits = {}
    for pos, seq_str in sequences.items():
        if pos in ['千', '百', '十', '个']:
            target = int(winning4[{'千':0,'百':1,'十':2,'个':3}[pos]])
            seq_list = seq_str.split()
            hit = 0
            for i, s in enumerate(reversed(seq_list)):
                if str(target) in s:
                    hit = len(s)
                    break
            hits[pos] = hit
    data['hits'] = hits
    
    log(f"API期号: {api_period}, 开奖号: {winning4}")
    log(f"填入开奖号 {winning4}")
    
    try:
        save_data(data)
        log(f"推送成功！期{rec_period} 开奖{winning4} 已更新")
        update_index_html(data)
    except Exception as e:
        log(f"推送异常: {e}")

if __name__ == '__main__':
    main()
