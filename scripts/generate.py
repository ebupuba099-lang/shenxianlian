#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日自动生成脚本
每天04:27执行：生成新一期递减序列 → 保存旧期到历史 → 推送到GitHub Gist
"""

import json
import random
import os
from datetime import datetime
from urllib.request import Request, urlopen

# ========== 配置 ==========
GIST_TOKEN = os.environ.get('GIST_TOKEN', '')
GIST_ID = 'b5df31cd9ef75152e7e9f880f22d7eb6'
GIST_FILENAME = 'sxl_data.json'
GIST_API = f'https://api.github.com/gists/{GIST_ID}'

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

def shuffle_array(arr):
    """Fisher-Yates洗牌"""
    a = list(arr)
    for i in range(len(a) - 1, 0, -1):
        j = random.randint(0, i)
        a[i], a[j] = a[j], a[i]
    return a

def gen_decreasing(digits):
    """生成递减序列，与网站JS逻辑一致"""
    seq = []
    cur = list(digits)
    seq.append(''.join(str(d) for d in cur))
    while len(cur) > 1:
        cur.pop(random.randint(0, len(cur) - 1))
        seq.append(''.join(str(d) for d in cur))
    return seq

def calc_auto_period():
    """计算期数，与网站JS一致：baseDate=2026-05-11, basePeriod=2026121"""
    base = datetime(2026, 5, 11)
    now = datetime.now()
    diff = (now - base).days
    return 2026121 + diff

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
    log("神仙连自动生成任务开始")

    # 1. 从Gist读取当前数据
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

    old_period = cloud_data.get('period', 0)
    old_sequences = cloud_data.get('sequences', {})
    old_winning = cloud_data.get('winning', '')
    history = cloud_data.get('history', [])

    log(f"当前期数: {old_period}, 历史记录: {len(history)}条")

    # 2. 计算新期数
    new_period = calc_auto_period()
    log(f"自动计算期数: {new_period}")

    if new_period <= old_period:
        log(f"期数未变化 ({new_period} <= {old_period})，无需生成新期")
        return True

    # 3. 保存旧期到历史
    if old_sequences.get('千') or old_sequences.get('百') or old_sequences.get('十') or old_sequences.get('个'):
        exist_idx = None
        for i, r in enumerate(history):
            if r.get('period') == old_period:
                exist_idx = i
                break

        record = {
            'period': old_period,
            'sequences': old_sequences,
            'winning': old_winning,
            'hits': calc_hits(old_sequences, old_winning) if old_winning else {}
        }

        if exist_idx is not None:
            history[exist_idx] = record
        else:
            history.insert(0, record)

        # 最多保留7条
        history = history[:7]

    # 4. 生成新一期序列
    positions = ['千', '百', '十', '个']
    new_sequences = {}
    for pos in positions:
        digits = shuffle_array([0, 1, 2, 3, 4, 5, 6, 7, 8, 9])
        selected = digits[:8]
        seq = gen_decreasing(selected)
        new_sequences[pos] = ' '.join(seq)

    log(f"新期 {new_period} 生成完成")
    log(f"  千: {new_sequences['千']}")
    log(f"  百: {new_sequences['百']}")
    log(f"  十: {new_sequences['十']}")
    log(f"  个: {new_sequences['个']}")

    # 5. 更新数据
    cloud_data['period'] = new_period
    cloud_data['sequences'] = new_sequences
    cloud_data['winning'] = ''
    cloud_data['history'] = history
    cloud_data['lastUpdate'] = int(datetime.now().timestamp() * 1000)

    # 6. 推送到Gist
    for attempt in range(3):
        try:
            success = push_gist(cloud_data)
            if success:
                log(f"推送成功！新期: {new_period}")
                return True
            else:
                log(f"推送失败 (第{attempt+1}次)")
        except Exception as e:
            log(f"推送异常 (第{attempt+1}次): {e}")
        if attempt < 2:
            import time; time.sleep(5)

    log("推送彻底失败")
    return False

if __name__ == '__main__':
    import sys
    success = main()
    sys.exit(0 if success else 1)
