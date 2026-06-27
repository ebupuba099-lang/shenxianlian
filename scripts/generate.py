#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日自动生成脚本 v6
直接用GitHub Contents API读写repo数据文件
v6 修复：update_index_html 中的代码截断问题 + GH_TOKEN空值检查
"""
import json
import random
import os
import base64
import re
import sys
from datetime import datetime
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'
BASE_DATE = datetime(2026, 5, 21)


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
            'history': data.get('history', []),
            'hits': data.get('hits', {})
        }
        s_json = json.dumps(s_obj, ensure_ascii=False, separators=(',', ':'))

        # 方式1：更新 embedded-data script 标签
        updated = False
        target = '<script type="application/json" id="embedded-data">'
        if target in html_content:
            start = html_content.index(target) + len(target)
            end = html_content.index('</script>', start)
            new_html = html_content[:start] + '\n' + s_json + '\n' + html_content[end:]
            updated = True
            log("已更新 embedded-data script 标签")
        else:
            log("警告: 未找到 embedded-data script 标签")

        # 方式2：更新 let S = {...} 变量
        s_var_match = re.search(r'let\s+S\s*=\s*\{', html_content)
        if s_var_match:
            brace_start = s_var_match.end() - 1
            old_s_block = match_balanced_braces(html_content, brace_start)
            if old_s_block:
                new_s_block = json.dumps(s_obj, ensure_ascii=False, indent=6)
                if 'new_html' not in dir():
                    new_html = html_content
                new_html = new_html[:brace_start] + new_s_block + new_html[brace_start+len(old_s_block):]
                updated = True
                log("已更新 let S 变量")
            else:
                log("警告: 未找到 let S 平衡括号")
        else:
            log("警告: 未找到 let S 变量定义")

        if not updated:
            log("index.html无需更新")
            return True

        # 检查是否真的有变化
        if new_html == html_content:
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
        return None
    headers = {'Authorization': f'token {GH_TOKEN}', 'Accept': 'application/vnd.github.v3.raw'}
    req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
    resp = urlopen(req, timeout=30)
    return json.loads(resp.read().decode('utf-8'))


def save_data(data):
    if not GH_TOKEN:
        log("✗ GH_TOKEN 为空，无法保存数据")
        return False
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
    selected = digits[:8]
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
    log("神仙连自动生成任务 v6 开始")

    # 检查 GH_TOKEN
    if not GH_TOKEN:
        log("✗ 严重错误：GH_TOKEN 环境变量为空！")
        log("  请检查 GitHub Secrets 中是否正确设置了 GH_TOKEN")
        return False

    data = load_data()
    if data is None:
        log("✗ 读取数据失败")
        return False

    today = datetime.now()
    days_diff = (today - BASE_DATE).days
    today_period = 2026131 + days_diff

    current_period = data.get('period', 0)
    current_winning = data.get('winning', '')
    log(f"当前期数: {current_period}, 开奖号: {'(空)' if not current_winning else current_winning}, 历史记录: {len(data.get('history',[]))}条")

    auto_period = today_period
    log(f"自动计算期数: {auto_period}")

    if current_period >= auto_period:
        log(f"当前期{current_period}已是最新的{auto_period}，无需生成")
        return True

    # 兜底机制：如果当前期超过2天还没开奖，也继续生成避免永久卡死
    if not current_winning and current_period > 0:
        # 使用 lastGenerateAttempt 字段追踪首次检测时间（不受 save_data 影响）
        last_attempt = data.get('lastGenerateAttempt', 0)
        now_ts = int(datetime.now().timestamp() * 1000)
        if last_attempt == 0:
            # 首次检测到未开奖，记录时间戳
            data['lastGenerateAttempt'] = now_ts
            save_data(data)
            log(f"当前期{current_period}还未开奖，首次记录等待时间戳")
            return True
        stale_hours = (now_ts - last_attempt) / 3600000
        if stale_hours < 48:
            log(f"当前期{current_period}还未开奖（{stale_hours:.1f}小时前首次检测），今天不生成新一期")
            return True
        else:
            log(f"当前期{current_period}超过2天未开奖，跳过继续生成下一期")

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
            # 不再限制历史记录条数
            data['history'] = history

    data['period'] = auto_period
    data['sequences'] = {'千': qian, '百': bai, '十': shi, '个': ge}
    data['winning'] = ''
    data['hits'] = {}
    # 生成成功后清除 lastGenerateAttempt
    data.pop('lastGenerateAttempt', None)

    log(f"新期 {auto_period} 生成完成")
    log(f"  千: {' '.join(qian.split()[:3])}")
    log(f"  百: {' '.join(bai.split()[:3])}")
    log(f"  十: {' '.join(shi.split()[:3])}")
    log(f"  个: {' '.join(ge.split()[:3])}")

    try:
        success = save_data(data)
        if success:
            log(f"✓ 推送成功！新期: {auto_period}")
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
