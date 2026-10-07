#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日生成脚本 v7（开奖驱动版）
================================
本脚本不再是按日历天数生成新期，而是作为安全网：
1. 当前期已有开奖结果但未推进（异常状态）-> 归档并生成下一期
2. 数据超前（当前期 > 已开奖期+1 且未开奖）-> 回滚到正确期数并清理超前假记录
3. 其余情况（正常等待开奖）-> 什么都不做
新一期的正常生成由 scripts/lottery.py 在获取到新开奖结果时自动完成。
"""
import json
import random
import os
import base64
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'
TZ = timezone(timedelta(hours=8))


def log(msg):
    now = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')
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
    """更新index.html里的内嵌数据（let S + embedded-data），确保页面打开就能显示最新数据"""
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

        embedded = json.dumps(data, ensure_ascii=False)
        new_html = None

        # 方式1：更新 let S = {...} 变量
        s_var_match = re.search(r'let\s+S\s*=\s*\{', html_content)
        if s_var_match:
            brace_start = s_var_match.end() - 1
            old_s_block = match_balanced_braces(html_content, brace_start)
            if old_s_block:
                new_html = html_content[:brace_start] + embedded + html_content[brace_start+len(old_s_block):]
                log("已更新 let S 变量")
            else:
                log("警告: 未找到 let S 平衡括号")
        else:
            log("警告: 未找到 let S 变量定义")

        # 方式2：更新 embedded-data script 标签
        m = re.search(r'(<script[^>]*id="embedded-data"[^>]*>)([\s\S]*?)(</script>)', html_content or '')
        if m and m.group(2).strip() != embedded:
            base_html = new_html if new_html is not None else html_content
            m2 = re.search(r'(<script[^>]*id="embedded-data"[^>]*>)([\s\S]*?)(</script>)', base_html)
            if m2:
                new_html = base_html[:m2.start(2)] + embedded + base_html[m2.end(2):]
                log("已更新 embedded-data script 标签")

        if new_html is None or new_html == html_content:
            log("index.html无需更新（内容未变化）")
            return True

        encoded = base64.b64encode(new_html.encode('utf-8')).decode('utf-8')
        body = json.dumps({
            'message': 'auto: update initial S data in index.html',
            'content': encoded,
            'sha': html_sha
        }).encode('utf-8')

        put_req = Request(
            f'https://api.github.com/repos/{REPO}/contents/index.html',
            data=body,
            method='PUT',
            headers=headers2
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
        import traceback
        traceback.print_exc()
        return False


def load_data():
    if not GH_TOKEN:
        log("✗ GH_TOKEN 为空，无法读取数据")
        return None, None
    headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3+json'}
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
    resp = urlopen(req, timeout=30)
    info = json.loads(resp.read().decode('utf-8'))
    sha = info['sha']
    data = json.loads(base64.b64decode(info['content']).decode('utf-8'))
    return sha, data


def save_data(sha, data):
    if not GH_TOKEN:
        log("✗ GH_TOKEN 为空，无法保存数据")
        return False
    headers = {
        'Authorization': f'token {GH_TOKEN}',
        'Accept': 'application/vnd.github.v3+json',
        'Content-Type': 'application/json'
    }
    content = json.dumps(data, ensure_ascii=False, indent=2)
    b64 = base64.b64encode(content.encode('utf-8')).decode()
    body = json.dumps({'message': 'auto: generate new period', 'content': b64, 'sha': sha}).encode('utf-8')

    put_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', data=body, method='PUT', headers=headers)
    resp = urlopen(put_req, timeout=30)
    return resp.status == 200


def generate_decreasing_sequence():
    digits = list(range(10))
    random.shuffle(digits)
    selected = digits[:8]
    sequences = [''.join(str(d) for d in selected)]
    current = list(selected)
    while len(current) > 1:
        idx = random.randint(0, len(current) - 1)
        current.pop(idx)
        sequences.append(''.join(str(d) for d in current))
    # 返回空格分隔字符串，前端updatePreview()期望此格式
    return ' '.join(sequences)


def calc_hits_py(sequences, winning):
    """计算每个位置的粒数（与前端 calcHits 逻辑一致）"""
    hits = {}
    if not winning or len(winning) != 4:
        return hits
    pos_map = [('千', 0), ('百', 1), ('十', 2), ('个', 3)]
    for pos_name, idx in pos_map:
        seq = sequences.get(pos_name, '')
        if not seq:
            hits[pos_name] = 0
            continue
        nums = seq.split(' ')
        target = winning[idx]
        found = False
        for j in range(len(nums) - 1, -1, -1):
            if target in nums[j]:
                hits[pos_name] = len(nums[j])
                found = True
                break
        if not found:
            hits[pos_name] = 0
    return hits


def main():
    log("=" * 50)
    log("神仙连生成任务 v7（开奖驱动版）开始")

    if not GH_TOKEN:
        log("✗ 严重错误：GH_TOKEN 环境变量为空！")
        log("  请检查 GitHub Secrets 中是否正确设置了 GH_TOKEN")
        return False

    sha, data = load_data()
    if data is None:
        log("✗ 读取数据失败")
        return False

    cp = int(data.get('period', 0) or 0)
    winning = data.get('winning', '')
    history = data.get('history', []) or []

    # 已开奖期号
    last_drawn = int(data.get('lastDrawnPeriod', 0) or 0)
    if not last_drawn:
        drawn = [int(h.get('period', 0) or 0) for h in history if h.get('winning')]
        last_drawn = max(drawn) if drawn else 0

    log(f"当前期数: {cp}, 开奖号: {'(空)' if not winning else winning}, 已开奖期号: {last_drawn}, 历史记录: {len(history)}条")

    changed = False
    now_str = datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')

    if winning and cp > 0:
        # 情况1：当前期已有开奖结果但尚未推进（异常状态兜底）-> 归档并生成下一期
        log(f"当前期{cp}已有开奖结果{winning}，归档并生成{cp + 1}期")

        entry = None
        for h in history:
            if int(h.get('period', 0) or 0) == cp:
                entry = h
                break
        if entry is None:
            entry = {'period': cp}
            history.insert(0, entry)
        entry['winning'] = winning
        if not entry.get('sequences'):
            entry['sequences'] = data.get('sequences', {})
        entry['hits'] = calc_hits_py(entry.get('sequences', {}), winning)
        if not entry.get('time'):
            entry['time'] = now_str

        history.sort(key=lambda x: int(x.get('period', 0) or 0), reverse=True)
        history = history[:7]
        data['history'] = history
        data['lastDrawnPeriod'] = cp
        data['period'] = cp + 1
        data['sequences'] = {'千': generate_decreasing_sequence(),
                             '百': generate_decreasing_sequence(),
                             '十': generate_decreasing_sequence(),
                             '个': generate_decreasing_sequence()}
        data['winning'] = ''
        data['hits'] = {}
        data.pop('lastGenerateAttempt', None)
        changed = True

    elif cp > last_drawn + 1:
        # 情况2：数据超前（未开奖却领先于已开奖期）-> 回滚并清理超前假记录
        log(f"数据超前: 当前期{cp} > 已开奖期{last_drawn}+1，回滚到{last_drawn + 1}")
        before = len(history)
        history = [h for h in history if int(h.get('period', 0) or 0) <= last_drawn]
        if len(history) != before:
            log(f"清理超前假记录: {before - len(history)}条")
        history.sort(key=lambda x: int(x.get('period', 0) or 0), reverse=True)
        history = history[:7]
        data['history'] = history
        data['period'] = last_drawn + 1
        data['winning'] = ''
        data['hits'] = {}
        data['sequences'] = {'千': generate_decreasing_sequence(),
                             '百': generate_decreasing_sequence(),
                             '十': generate_decreasing_sequence(),
                             '个': generate_decreasing_sequence()}
        data.pop('lastGenerateAttempt', None)
        changed = True
    else:
        # 情况3：正常状态，等待开奖（休市期间期数保持不变）
        log(f"当前期{cp}未开奖（最新开奖{last_drawn}），等待开奖后再生成新一期")

    if not changed:
        log("任务完成（无需变更）")
        return True

    data['lastUpdate'] = int(datetime.now(TZ).timestamp() * 1000)
    data['version'] = int(time.time())

    log(f"新期 {data['period']} 生成完成")

    try:
        success = save_data(sha, data)
        if success:
            log(f"✓ 推送成功！新期: {data['period']}")
            update_index_html(data)
        else:
            log("✗ 推送失败")
            return False
    except Exception as e:
        log(f"✗ 推送异常: {e}")
        return False

    log("任务完成")
    return True


if __name__ == '__main__':
    success = main()
    if not success:
        log("✗ 任务失败，退出码 1")
        sys.exit(1)
    else:
        log("✓ 任务成功，退出码 0")
        sys.exit(0)
