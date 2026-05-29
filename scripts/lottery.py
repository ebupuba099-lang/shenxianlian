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
        # 找到完整的 let S = {...};;; 语句并替换
        target = 'let S = '
        idx = html_content.find(target)
        if idx < 0:
            log("未找到 'let S = '，无法更新")
            return False
        
        brace_start = idx + len(target)
        matched = match_balanced_braces(html_content, brace_start)
        if not matched:
            log("无法匹配 S 对象的平衡花括号")
            return False
        
        # 匹配到语句末尾的分号（;;;）
        end_pos = brace_start + len(matched)
        while end_pos < len(html_content) and html_content[end_pos] == ';':
            end_pos += 1
        
        old_statement = html_content[idx:end_pos]
        new_statement = 'let S = ' + s_json + ';;;'
        new_html = html_content.replace(old_statement, new_statement, 1)
        
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
    body = json.dumps({'message': 'auto: update lottery result', 'content': b64, 'sha': sha}).encode('utf-8')
    put_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', data=body, method='PUT', headers=headers)
    resp = urlopen(put_req, timeout=30)
    return resp.status == 200


def calc_hits(sequences, winning):
    """计算命中粒数：每位的开奖数字在对应序列中出现的最深层级"""
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
                    return winning4, period, latest.get('lotteryDrawTime', '')
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
                draw_date = last.get('day', '')
                log(f"灰鸟API: 期号={code}(→{period}), 号码={one}{two}{three}{four}{last.get('five','')}, 日期={draw_date}")
                return winning4, period, draw_date
    except Exception as e:
        log(f"灰鸟API失败: {e}")
    
    return None, None, ''

def main():
    log("=" * 50)
    log("神仙连开奖号码自动填入任务开始")
    
    winning4, api_period, draw_date = fetch_winning_number()
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
    
    # 用API的开奖日期计算对应我们的期号
    BASE_DATE = datetime(2026, 5, 21)
    if draw_date:
        try:
            draw_dt = datetime.strptime(draw_date, '%Y-%m-%d')
            api_our_period = 2026131 + (draw_dt - BASE_DATE).days
            log(f"API开奖日期: {draw_date} → 我们的期号: {api_our_period}")
        except:
            api_our_period = current_period
            log(f"日期解析失败，使用当前期号: {current_period}")
    else:
        api_our_period = current_period - 1  # 无日期时假设昨天
        log(f"无开奖日期，假设为前一期: {api_our_period}")
    
    # 将开奖号填入对应期号
    if api_our_period == current_period:
        # 开奖号属于当前期，直接填入
        target_period = current_period
    else:
        # 开奖号属于历史期，检查是否需要补填
        target_period = api_our_period
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == target_period]
        if existing and existing[0].get('winning'):
            log(f"期{target_period}已有开奖号 {existing[0]['winning']}，跳过")
            return True
        log(f"开奖号属于期{target_period}，非当前期{current_period}，补填历史")
    
    if target_period == current_period:
        # 填入当前期
        data['winning'] = winning4
        hits = calc_hits(data.get('sequences', {}), winning4)
        data['hits'] = hits
        log(f"填入当前期 {current_period} 开奖号 {winning4}, 命中: {hits}")
    else:
        # 补填历史期
        hits = calc_hits({}, winning4)  # 历史期可能没有序列
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == target_period]
        if existing:
            existing[0]['winning'] = winning4
            if not existing[0].get('hits') or existing[0]['hits'] == {}:
                if existing[0].get('sequences'):
                    existing[0]['hits'] = calc_hits(existing[0]['sequences'], winning4)
                else:
                    existing[0]['hits'] = hits
            log(f"补填历史期 {target_period} 开奖号 {winning4}")
        else:
            hist_entry = {
                'period': target_period,
                'winning': winning4,
                'hits': hits
            }
            history.insert(0, hist_entry)
            if len(history) > 10:
                history = history[:7]
            data['history'] = history
            log(f"新建历史期 {target_period} 开奖号 {winning4}")
    
    # 如果当前期已有开奖号，也保存到历史
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
            if len(history) > 10:
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
