#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日开奖号码自动填入脚本
每天22:00执行：从体彩官方API获取开奖号码 → 填入当前期 → 计算命中 → 推送到GitHub Gist
"""

import json
import os
from datetime import datetime
from urllib.request import Request, urlopen

# ========== 配置 ==========
GIST_TOKEN = os.environ.get('GIST_TOKEN', '')
GIST_ID = 'b5df31cd9ef75152e7e9f880f22d7eb6'
GIST_FILENAME = 'sxl_data.json'
GIST_API = f'https://api.github.com/gists/{GIST_ID}'

# 体彩官方API - 排列五
SPORTTERY_URL = 'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0'
# 灰鸟API - 备用
HUINIAO_URL = 'http://api.huiniao.top/interface/home/lotteryHistory?type=plw&page=1&limit=1'

def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)

def fetch_gist():
    """从Gist读取数据"""
    headers = {'User-Agent': 'Python'}
    if GIST_TOKEN:
        headers['Authorization'] = f'token {GIST_TOKEN}'
    req = Request(GIST_API, headers=headers)
    resp = urlopen(req, timeout=30)
    data = json.loads(resp.read().decode('utf-8'))
    content = data['files'][GIST_FILENAME]['content']
    return json.loads(content)

def push_gist(data):
    """推送数据到Gist"""
    body = json.dumps({
        'files': {
            GIST_FILENAME: {
                'content': json.dumps(data, ensure_ascii=False, indent=2)
            }
        }
    }).encode('utf-8')
    headers = {
        'Authorization': f'token {GIST_TOKEN}',
        'Content-Type': 'application/json',
        'User-Agent': 'Python'
    }
    req = Request(GIST_API, data=body, method='PATCH', headers=headers)
    resp = urlopen(req, timeout=30)
    return resp.status == 200

def fetch_lottery_number(retry=3):
    """
    从API获取排列五最新开奖号码（降级链）
    返回 (draw_num, 5位号码字符串)，如 ('26135', '93925')
    """
    apis = [
        {
            'name': '体彩官方',
            'url': SPORTTERY_URL,
            'parse': lambda data: (
                data['value']['lastPoolDraw']['lotteryDrawNum'],
                data['value']['lastPoolDraw']['lotteryDrawResult']
            ) if data.get('value', {}).get('lastPoolDraw') else None
        },
        {
            'name': '灰鸟API',
            'url': HUINIAO_URL,
            'parse': lambda data: (
                data['data']['last']['code'],
                ' '.join([data['data']['last']['one'], data['data']['last']['two'],
                          data['data']['last']['three'], data['data']['last']['four'],
                          data['data']['last']['five']])
            ) if data.get('data', {}).get('last') else None
        }
    ]

    for api in apis:
        for attempt in range(retry):
            try:
                req = Request(api['url'], headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                    'Referer': 'https://www.lottery.gov.cn/'
                })
                resp = urlopen(req, timeout=15)
                data = json.loads(resp.read().decode('utf-8'))
                result = api['parse'](data)
                if not result:
                    log(f"{api['name']}: 解析返回数据失败")
                    continue

                draw_num, draw_result = result
                nums = draw_result.replace(',', ' ').split()
                if len(nums) != 5:
                    log(f"{api['name']}: 号码格式异常 '{draw_result}'，期望5位")
                    continue

                full_number = ''.join(nums)
                if not full_number.isdigit():
                    log(f"{api['name']}: 号码包含非数字: {full_number}")
                    continue

                log(f"{api['name']}获取成功: 期号{draw_num}, 号码{draw_result}")
                return (draw_num, full_number)

            except Exception as e:
                log(f"{api['name']}失败 (第{attempt+1}次): {e}")
                if attempt < retry - 1:
                    import time; time.sleep(5)

    return None

def calc_hits(sequences, winning):
    """计算命中，与网站JS一致"""
    hits = {}
    positions = ['千', '百', '十', '个']
    if not winning or len(winning) != 4:
        return hits
    for i, pos in enumerate(positions):
        seq = sequences.get(pos, '')
        if not seq:
            hits[pos] = 0
            continue
        nums = seq.split(' ')
        target = winning[i]
        for j in range(len(nums) - 1, -1, -1):
            if target in nums[j]:
                hits[pos] = len(nums[j])
                break
        if pos not in hits:
            hits[pos] = 0
    return hits

def main():
    log("=" * 50)
    log("神仙连开奖号码自动填入任务开始")

    # 1. 获取开奖号码
    result = fetch_lottery_number(retry=3)
    if not result:
        log("获取开奖号码失败，任务终止")
        return False

    draw_num, lottery_number = result
    winning4 = lottery_number[:4]

    if len(winning4) != 4 or not winning4.isdigit():
        log(f"开奖号码格式异常: {lottery_number}，取前4位: {winning4}，任务终止")
        return False

    # 将API期号转为完整期数格式，如 "26135" → "2026135"
    target_period = '20' + draw_num
    log(f"开奖期号: {draw_num}, 对应期数: {target_period}, 号码: {lottery_number}, 前4位: {winning4}")

    # 2. 从Gist读取当前数据
    for attempt in range(3):
        try:
            cloud_data = fetch_gist()
            break
        except Exception as e:
            log(f"读取Gist失败 (第{attempt+1}次): {e}")
            if attempt == 2:
                log("读取Gist彻底失败，任务终止")
                return False
            import time; time.sleep(5)

    current_period = cloud_data.get('period', 0)
    current_winning = cloud_data.get('winning', '')
    sequences = cloud_data.get('sequences', {})
    history = cloud_data.get('history', [])

    log(f"当前期数: {current_period}, 当前开奖号: {current_winning or '(空)'}")

    # 3. 填入开奖号码
    updated = False

    # 检查当前期
    if str(current_period) == target_period:
        if current_winning:
            log(f"当前期 {current_period} 已有开奖号码 '{current_winning}'，跳过")
        else:
            cloud_data['winning'] = winning4
            updated = True
            hits = calc_hits(sequences, winning4)
            hit_str = ' '.join([f"{p}中{h}粒" for p, h in hits.items()])
            log(f"填入成功！{target_period} 期 {winning4} - {hit_str}")
    else:
        log(f"当前期 {current_period} 与开奖期 {target_period} 不匹配")

    # 4. 更新历史记录
    history_changed = False
    for record in history:
        if str(record.get('period')) == target_period:
            if not record.get('winning'):
                record['winning'] = winning4
                record['hits'] = calc_hits(record.get('sequences', {}), winning4)
                history_changed = True
                log(f"历史记录期 {target_period} 填入开奖号 {winning4}")
            # 已有开奖号也重新计算命中
            elif record.get('winning') == winning4:
                new_hits = calc_hits(record.get('sequences', {}), winning4)
                if new_hits != record.get('hits'):
                    record['hits'] = new_hits
                    history_changed = True
            break

    if updated or history_changed:
        cloud_data['history'] = history
        cloud_data['lastUpdate'] = int(datetime.now().timestamp() * 1000)

        # 5. 推送到Gist
        for attempt in range(3):
            try:
                success = push_gist(cloud_data)
                if success:
                    log(f"推送成功！")
                    return True
                else:
                    log(f"推送失败 (第{attempt+1}次)")
            except Exception as e:
                log(f"推送异常 (第{attempt+1}次): {e}")
            if attempt < 2:
                import time; time.sleep(5)

        log("推送彻底失败")
        return False
    else:
        log("无需更新")
        return True

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
