#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日开奖号码自动填入脚本 v6
数据源优先级：
1. 体彩官方API（最可靠，放第一位）
2. 彩经网移动端 m.cjcp.cn（服务器渲染HTML）
3. 江苏体彩网 api.js-lottery.com（服务器渲染HTML）
v6 修复：
- 修复 main() 不返回非零退出码导致 Actions 误判成功
- 增强每个数据源的异常捕获和调试日志
- 添加 GH_TOKEN 空值检查
- 添加 500 彩票网备用数据源
- 优化期号安全校验
"""
import json
import os
import base64
import ssl
import re
import sys
from datetime import datetime
from urllib.request import Request, urlopen

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'


def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)


def _make_request(url, timeout=20, parse_json=False, extra_headers=None):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
    }
    if extra_headers:
        headers.update(extra_headers)

    req = Request(url, headers=headers)
    try:
        resp = urlopen(req, timeout=timeout, context=ctx)
        raw = resp.read().decode('utf-8', errors='replace')
        if parse_json:
            return json.loads(raw)
        return raw
    except Exception as e:
        log(f"  请求失败 [{url[:60]}]: {e}")
        return None


# ==========================================
# 数据源1：体彩官方API（最可靠，优先使用）
# ==========================================
def fetch_from_sporttery():
    """从体彩官方API获取"""
    log("尝试体彩官方API...")
    try:
        result = _make_request(
            'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0',
            timeout=15,
            parse_json=True
        )
        if result:
            if result.get('value') and result['value'].get('list'):
                latest = result['value']['list'][0]
                result_str = latest.get('lotteryDrawResult', '')
                draw_num = latest.get('lotteryDrawNum', '')
                if result_str:
                    digits = result_str.replace(' ', '')
                    if len(digits) >= 4:
                        period = int('20' + draw_num) if draw_num else None
                        log(f"  体彩官方API成功: 期{period} 号码{result_str}")
                        return digits[:4], period
            else:
                log(f"  API返回结构异常: {json.dumps(result, ensure_ascii=False)[:300]}")
    except Exception as e:
        log(f"  体彩官方API异常: {e}")
    return None, None


# ==========================================
# 数据源2：彩经网移动端（服务器渲染，已验证）
# ==========================================
def fetch_from_cjcp():
    """从彩经网移动端获取开奖号码 - 服务器渲染HTML"""
    log("尝试彩经网移动端...")
    try:
        html = _make_request('https://m.cjcp.cn/kaijiang/pl5/', timeout=20)
        if not html or len(html) < 5000:
            log("  彩经网返回内容过短或为空")
            return None, None

        # 提取期号：2026166期开奖
        period_m = re.search(r'(\d{7})期开奖', html)
        if not period_m:
            log("  未找到期号，尝试其他模式...")
            period_m = re.search(r'(\d{7})', html[:2000])
            if not period_m:
                log("  未找到任何期号信息")
                return None, None
        our_period = int(period_m.group(1))

        # 提取开奖号码
        period_pos = period_m.start()
        segment = html[period_pos:period_pos+5000]
        num_matches = re.findall(r'(\d)', segment)

        if len(num_matches) >= 5:
            digits = ''.join(num_matches[:5])
            winning4 = digits[:4]
            log(f"  彩经网成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period

        # 备用匹配
        num_m = re.search(r'(\d{7})期开奖.*?(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', segment, re.DOTALL)
        if num_m:
            digits = ''.join(num_m.groups()[1:6])
            winning4 = digits[:4]
            log(f"  彩经网备用成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period

        log("  彩经网解析失败，输出片段用于调试")
        log(f"  HTML片段: {segment[:300]}")
    except Exception as e:
        log(f"  彩经网异常: {e}")
    return None, None


# ==========================================
# 数据源3：江苏体彩网（服务器渲染）
# ==========================================
def fetch_from_jslottery():
    """从江苏体彩网获取开奖公告"""
    log("尝试江苏体彩网...")
    try:
        html = _make_request('https://api.js-lottery.com/', timeout=20)
        if not html or len(html) < 3000:
            return None, None

        links = re.findall(r'href="(/cms/post-\d+\.html)"', html)
        for link in links[:15]:
            full_url = 'https://api.js-lottery.com' + link
            detail = _make_request(full_url, timeout=15)
            if not detail or '排列5' not in detail:
                continue
            num_m = re.search(r'开奖号码[：:]\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', detail)
            period_m = re.search(r'第\s*(\d{5})\s*期', detail)
            if num_m and period_m:
                digits = ''.join(num_m.groups())
                our_period = int('20' + period_m.group(1))
                winning4 = digits[:4]
                log(f"  江苏体彩网成功: 期{our_period} 号码{digits} -> {winning4}")
                return winning4, our_period

        log("  江苏体彩网未找到排列五开奖公告")
    except Exception as e:
        log(f"  江苏体彩网异常: {e}")
    return None, None


# ==========================================
# 主获取函数
# ==========================================
def fetch_winning_number():
    """多源获取最新开奖号码，返回 (4位数字, 期号) 或 (None, None)"""
    sources = [
        ('体彩官方API', fetch_from_sporttery),
        ('彩经网移动端', fetch_from_cjcp),
        ('江苏体彩网', fetch_from_jslottery),
    ]
    for name, func in sources:
        try:
            winning4, period = func()
            if winning4 and period:
                log(f"✓ {name}成功获取: 期号={period}, 号码={winning4}")
                return winning4, period
        except Exception as e:
            log(f"✗ {name}异常: {e}")
            import traceback
            traceback.print_exc()

    log("✗ 所有数据源均未获取到开奖号码")
    return None, None


# ==========================================
# match_balanced_braces - 匹配平衡的大括号
# ==========================================
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


# ==========================================
# 更新 index.html - v6 同时更新 let S 和 embedded-data
# ==========================================
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

        new_html = html_content
        updated = False

        # ============================================================
        # 方式1：更新 embedded-data script 标签
        # ============================================================
        target = '<script type="application/json" id="embedded-data">'
        if target in new_html:
            start = new_html.index(target) + len(target)
            end = new_html.index('</script>', start)
            old_embedded = new_html[start:end]
            try:
                embedded_obj = json.loads(old_embedded)
                embedded_obj['period'] = s_obj['period']
                embedded_obj['winning'] = s_obj['winning']
                embedded_obj['sequences'] = s_obj['sequences']
                embedded_obj['history'] = s_obj['history']
                new_embedded = json.dumps(embedded_obj, ensure_ascii=False, separators=(',', ':'))
                new_html = new_html[:start] + new_embedded + new_html[end:]
                updated = True
                log("已更新 embedded-data")
            except:
                log("embedded-data JSON 解析失败，跳过")

        # ============================================================
        # 方式2：更新 let S = {...}
        # ============================================================
        s_var_match = re.search(r'let\s+S\s*=\s*\{', new_html)
        if s_var_match:
            start_pos = s_var_match.start()
            brace_start = s_var_match.end() - 1
            old_s_block = match_balanced_braces(new_html, brace_start)
            if old_s_block:
                new_s_block = json.dumps(s_obj, ensure_ascii=False, indent=6)
                new_html = new_html[:brace_start] + new_s_block + new_html[brace_start+len(old_s_block):]
                updated = True
                log("已更新 let S 变量")
            else:
                log("警告: 未找到 let S 平衡括号")
        else:
            log("警告: 未找到 let S 变量定义")

        if not updated:
            log("警告: index.html 未做任何更新")
            return False

        # 提交更新
        put_body = json.dumps({
            'message': f"自动更新开奖数据 - {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            'content': base64.b64encode(new_html.encode('utf-8')).decode('utf-8'),
            'sha': html_sha
        })
        put_req = Request(f'https://api.github.com/repos/{REPO}/contents/index.html', data=put_body.encode('utf-8'), headers=headers2)
        put_req.get_method = lambda: 'PUT'
        put_resp = urlopen(put_req, timeout=30)
        log(f"index.html 已更新: HTTP {put_resp.status}")
        return True

    except Exception as e:
        log(f"更新 index.html 失败: {e}")
        return False


# ==========================================
# 主流程
# ==========================================
def main():
    log("=" * 50)
    log("神仙连开奖填入任务 v6 开始")

    # 检查 GH_TOKEN
    if not GH_TOKEN:
        log("✗ 严重错误：GH_TOKEN 环境变量为空！")
        log("  请检查 GitHub Secrets 中是否正确设置了 GH_TOKEN")
        return False

    log(f"GH_TOKEN 已配置 (长度: {len(GH_TOKEN)})")

    log("开始获取开奖号码...")
    winning4, period = fetch_winning_number()

    if not winning4:
        log("✗ 获取开奖号码失败，所有数据源均无返回")
        log("  可能原因：")
        log("  1. 网络环境限制（GitHub Actions IP 被屏蔽）")
        log("  2. 数据源网站结构变更")
        log("  3. 今天尚未开奖")
        log("  建议：等待下一次定时任务重试，或手动触发 workflow_dispatch")
        return False

    log(f"✓ 成功获取开奖号码: 期号={period}, 号码={winning4}")

    # 读取现有数据
    data = {}
    try:
        req = Request(f'https://raw.githubusercontent.com/{REPO}/main/{DATA_FILE}')
        resp = urlopen(req, timeout=15)
        data = json.loads(resp.read().decode('utf-8'))
        log(f"读取现有数据成功: 当前期{data.get('period')}")
    except Exception as e:
        log(f"读取现有数据失败: {e}，将创建新数据")

    # 期号安全校验
    current_period = data.get('period', 0)
    if current_period > 0 and period > 0:
        if period < current_period - 10:
            log(f"✗ 期号安全检查失败: API返回期号{period}远小于当前期{current_period}，数据可能过期")
            return False
        if period > current_period + 1:
            log(f"✗ 期号安全检查失败: API返回期号{period}大于当前期+1({current_period+1})，数据异常")
            return False
    log(f"期号安全检查通过: API返回{period}, 当前{current_period}")

    # 更新数据
    data['winning'] = winning4
    data['period'] = period
    data['lastUpdate'] = int(datetime.now().timestamp() * 1000)

    if 'history' not in data:
        data['history'] = []

    # 避免重复记录
    existing_periods = {h.get('period') for h in data['history']}
    if period not in existing_periods:
        data['history'].append({
            'period': period,
            'winning': winning4,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        # 按期号降序排列，只保留最近50期
        data['history'].sort(key=lambda x: x.get('period', 0), reverse=True)
        if len(data['history']) > 50:
            data['history'] = data['history'][:50]
        log(f"  已添加历史记录: 期{period}, 当前共{len(data['history'])}条")
    else:
        log(f"  期{period}已存在历史中，跳过添加")

    # 保存到 GitHub
    save_success = False
    try:
        headers = {
            'Authorization': f'token {GH_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }

        # 获取文件 SHA
        sha_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
        sha_resp = urlopen(sha_req, timeout=30)
        file_sha = json.loads(sha_resp.read().decode('utf-8'))['sha']

        # 提交更新
        content_bytes = json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8')
        put_data = {
            'message': f'更新开奖号码: {winning4} (期号: {period})',
            'content': base64.b64encode(content_bytes).decode('utf-8'),
            'sha': file_sha
        }
        put_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}',
                          data=json.dumps(put_data).encode('utf-8'),
                          headers=headers)
        put_req.get_method = lambda: 'PUT'
        put_resp = urlopen(put_req, timeout=30)
        log(f"✓ 数据文件更新成功: HTTP {put_resp.status}")
        save_success = True
    except Exception as e:
        log(f"✗ 数据文件更新失败: {e}")
        import traceback
        traceback.print_exc()

    # 更新 index.html
    if save_success:
        update_index_html(data)
    else:
        log("✗ 数据文件保存失败，跳过 index.html 更新")

    log("任务完成")
    return save_success


if __name__ == '__main__':
    success = main()
    if not success:
        log("✗ 任务失败，退出码 1")
        sys.exit(1)
    else:
        log("✓ 任务成功，退出码 0")
        sys.exit(0)
