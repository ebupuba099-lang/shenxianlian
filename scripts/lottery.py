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
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

SPORTTERY_URL = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0'
HUINIAO_URL = 'http://api.huiniao.top/interface/home/lotteryHistory?type=plw&page=1&limit=1'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)

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
    log(f"填入开奖号 {winning4}")
    
    try:
        success = save_data(data)
        if success:
            log(f"推送成功！期{current_period} 开奖{winning4} 已更新")
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
