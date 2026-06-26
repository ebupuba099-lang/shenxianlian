#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日开奖号码自动填入脚本
直接用GitHub Contents API读写repo数据文件，含期号校验
四重API保底：体彩官方 + 灰鸟 + 彩经网 + 网页解析
"""

import json
import os
import base64
import ssl
from datetime import datetime
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'

SPORTTERY_URL = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0'
HUINIAO_URL = 'http://api.huiniao.top/interface/home/lotteryHistory?type=plw&page=1&limit=1'
CJCP_URL = 'https://www.cjcp.com.cn/ajax/lottery/history?lotteryId=85&pageSize=10&pageNo=1'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)

def _request(url, timeout=15):
    """通用请求函数，支持SSL绕过"""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept': 'application/json, text/plain, */*'
    }
    req = Request(url, headers=headers)
    try:
        resp = urlopen(req, timeout=timeout, context=ctx)
        return json.loads(resp.read().decode('utf-8'))
    except Exception as e:
        log(f"  请求失败 {url[:50]}...: {e}")
        return None

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
            log("未找到 embedded-data script 标签，无法更新")
            return False
        
        brace_start = idx + len(target)
        matched = match_balanced_braces(html_content, brace_start)
        if not matched:
            log("无法匹配 S 对象的平衡花括号")
            return False
        
        json_end = brace_start + len(matched)
        script_end = html_content.find('</script>', json_end)
        if script_end < 0:
            log("未找到 </script> 结束标签")
            return False
        
        old_json = html_content[brace_start:json_end]
        new_statement = s_json
        new_html = html_content[:brace_start] + new_statement + html_content[json_end:]
        
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
    """获取最新开奖号码（四重保底），返回 (4位数字, API期号, 开奖日期) 或 (None, None, '')"""
    
    # 1. 体彩官方API
    log("尝试体彩官方API...")
    result = _request(SPORTTERY_URL)
    if result:
        try:
            if result.get('value') and result['value'].get('list'):
                latest = result['value']['list'][0]
                result_str = latest.get('lotteryDrawResult', '')
                draw_num = latest.get('lotteryDrawNum', '')
                if result_str:
                    digits = result_str.replace(' ', '')
                    if len(digits) >= 4:
                        winning4 = digits[:4]
                        period = int('20' + draw_num) if draw_num else None
                        log(f"  体彩官方成功: 期号={draw_num}(->{period}), 号码={result_str}")
                        return winning4, period, latest.get('lotteryDrawTime', '')
        except Exception as e:
            log(f"  体彩官方解析失败: {e}")
    
    # 2. 灰鸟API
    log("尝试灰鸟API...")
    result = _request(HUINIAO_URL)
    if result:
        try:
            d = result.get('data', {})
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
                    log(f"  灰鸟API成功: 期号={code}(->{period}), 号码={one}{two}{three}{four}{last.get('five','')}")
                    return winning4, period, draw_date
        except Exception as e:
            log(f"  灰鸟API解析失败: {e}")
    
    # 3. 彩经网API
    log("尝试彩经网API...")
    result = _request(CJCP_URL)
    if result:
        try:
            items = result.get("data", {}).get("list", [])
            if items:
                item = items[0]
                period_full = str(item.get("issue", ""))
                period = period_full[-3:] if len(period_full) >= 3 else period_full
                period = int('20' + period) if period else None
                number = str(item.get("drawCode", "")).replace(",", "").replace(" ", "")
                if number and len(number) >= 4:
                    winning4 = number[:4]
                    log(f"  彩经网成功: 期号={period_full}(->{period}), 号码={number}")
                    return winning4, period, ''
        except Exception as e:
            log(f"  彩经网解析失败: {e}")
    
    log("所有API均未获取到开奖号码")
    return None, None, ''

def main():
    log("=" * 50)
    log("神仙连开奖号码自动填入任务开始")
    
    winning4, api_period, draw_date = fetch_winning_number()
    if not winning4:
        log("所有API均未获取到开奖号码，跳过")
        log("可能原因: GitHub Actions IP被国内API安全策略拦截")
        log("请在本地环境手动运行: python scripts/lottery.py")
        return True
    
    data = load_data()
    current_period = data.get('period', 0)
    current_winning = data.get('winning', '')
    
    log(f"当前期数: {current_period}, 当前开奖号: {'(空)' if not current_winning else current_winning}")
    log(f"API期号: {api_period}, 开奖号: {winning4}")
    
    if current_winning:
        log(f"当前期已有开奖号 {current_winning}，跳过")
        return True
    
    BASE_DATE = datetime(2026, 5, 21)
    if draw_date:
        try:
            draw_dt = datetime.strptime(draw_date, '%Y-%m-%d')
            api_our_period = 2026131 + (draw_dt - BASE_DATE).days
            log(f"API开奖日期: {draw_date} -> 我们的期号: {api_our_period}")
        except:
            api_our_period = current_period
            log(f"日期解析失败，使用当前期号: {current_period}")
    else:
        api_our_period = current_period - 1
        log(f"无开奖日期，假设为前一期: {api_our_period}")
    
    if api_our_period == current_period:
        target_period = current_period
    else:
        target_period = api_our_period
        history = data.get('history', [])
        existing = [h for h in history if h.get('period') == target_period]
        if existing and existing[0].get('winning'):
            log(f"期{target_period}已有开奖号 {existing[0]['winning']}，跳过")
            return True
        log(f"开奖号属于期{target_period}，非当前期{current_period}，补填历史")
    
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
            log(f"补填历史期 {target_period} 开奖号 {winning4}")
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
