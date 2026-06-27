#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
神仙连 - 每日开奖号码自动填入脚本 v8
数据源优先级：
1. 体彩官方API
2. 彩经网移动端
3. 江苏体彩网（精确匹配排列5数据）
4. 500彩票网（备用）
v8 修复：
- 修复江苏体彩网解析：同一页面含排三和排五，需精确定位排列5段落
- 放宽期号安全检查
- 添加HTTP请求重试
"""
import json
import os
import base64
import ssl
import re
import sys
import time
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

GH_TOKEN = os.environ.get('GH_TOKEN', os.environ.get('GIST_TOKEN', ''))
REPO = 'ebupuba099-lang/shenxianlian'
DATA_FILE = 'data/sxl_data.json'


def log(msg):
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{now}] {msg}", flush=True)


def _make_request(url, timeout=20, parse_json=False, extra_headers=None, retries=2):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        'Cache-Control': 'no-cache',
        'Connection': 'keep-alive',
    }
    if extra_headers:
        headers.update(extra_headers)

    for attempt in range(retries):
        try:
            req = Request(url, headers=headers)
            resp = urlopen(req, timeout=timeout, context=ctx)
            raw = resp.read().decode('utf-8', errors='replace')
            if parse_json:
                return json.loads(raw)
            return raw
        except HTTPError as e:
            if attempt < retries - 1:
                log(f"  请求失败 [{url[:50]}]: HTTP {e.code}, 重试 {attempt+2}/{retries}...")
                time.sleep(2)
                continue
            log(f"  请求失败 [{url[:50]}]: HTTP {e.code}")
            return None
        except URLError as e:
            if attempt < retries - 1:
                log(f"  请求失败 [{url[:50]}]: {e.reason}, 重试 {attempt+2}/{retries}...")
                time.sleep(2)
                continue
            log(f"  请求失败 [{url[:50]}]: {e.reason}")
            return None
        except Exception as e:
            log(f"  请求失败 [{url[:50]}]: {e}")
            return None
    return None


# ==========================================
# 数据源1：体彩官方API
# ==========================================
def fetch_from_sporttery():
    """从体彩官方API获取排列5开奖"""
    log("尝试体彩官方API...")
    try:
        result = _make_request(
            'https://webapi.sporttery.cn/gateway/lottery/getHistoryPageListV1.qry?gameNo=350133&provinceId=0&pageSize=1&is11=0',
            timeout=20,
            parse_json=True,
            retries=3
        )
        if result and result.get('value') and result['value'].get('list'):
            latest = result['value']['list'][0]
            result_str = latest.get('lotteryDrawResult', '')
            draw_num = latest.get('lotteryDrawNum', '')
            if result_str:
                digits = result_str.replace(' ', '')
                if len(digits) >= 5:
                    period = int('20' + draw_num) if draw_num else None
                    winning4 = digits[:4]
                    log(f"  体彩官方API成功: 期{period} 号码{result_str} -> 前4位{winning4}")
                    return winning4, period
    except Exception as e:
        log(f"  体彩官方API异常: {e}")
    return None, None


# ==========================================
# 数据源2：彩经网移动端
# ==========================================
def fetch_from_cjcp():
    """从彩经网移动端获取排列5开奖号码"""
    log("尝试彩经网移动端...")
    try:
        html = _make_request('https://m.cjcp.cn/kaijiang/pl5/', timeout=20, retries=2)
        if not html or len(html) < 5000:
            html = _make_request('https://m.cjcp.com.cn/kaijiang/pl5/', timeout=20, retries=2)
        if not html or len(html) < 5000:
            log("  彩经网返回内容过短或为空")
            return None, None

        if '排列5' not in html and '排列五' not in html:
            log("  彩经网返回内容不包含排列5信息")
            return None, None

        period_m = re.search(r'(\d{7})期开奖', html)
        if not period_m:
            period_m = re.search(r'第\s*(\d{7})\s*期', html)
        if not period_m:
            period_m = re.search(r'(\d{7})', html[:2000])
        if not period_m:
            log("  未找到期号")
            return None, None
        
        our_period = int(period_m.group(1))
        period_pos = period_m.start()
        segment = html[max(0,period_pos-200):period_pos+5000]
        
        num_matches = re.findall(r'(\d)', segment)
        if len(num_matches) >= 5:
            digits = ''.join(num_matches[:5])
            winning4 = digits[:4]
            log(f"  彩经网成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period

        num_m = re.search(r'(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', segment)
        if num_m:
            digits = ''.join(num_m.groups())
            winning4 = digits[:4]
            log(f"  彩经网成功: 期{our_period} 号码{digits} -> {winning4}")
            return winning4, our_period

        log(f"  彩经网解析失败，片段: {segment[:200]}")
    except Exception as e:
        log(f"  彩经网异常: {e}")
    return None, None


# ==========================================
# 数据源3：江苏体彩网（精确解析排列5）
# ==========================================
def fetch_from_jslottery():
    """
    从江苏体彩网获取排列5开奖公告。
    关键：同一页面可能包含排三和排五数据，需要精确定位排列5段落。
    """
    log("尝试江苏体彩网...")
    try:
        html = _make_request('https://api.js-lottery.com/', timeout=20, retries=2)
        if not html or len(html) < 3000:
            return None, None

        links = re.findall(r'href="(/cms/post-\d+\.html)"', html)
        # 去重
        links = list(dict.fromkeys(links))
        log(f"  找到 {len(links)} 个唯一文章链接")

        for link in links[:20]:
            full_url = 'https://api.js-lottery.com' + link
            detail = _make_request(full_url, timeout=15)
            if not detail:
                continue
            
            # 必须包含排列5相关文字
            if '排列5' not in detail and '排列五' not in detail:
                continue
            
            # ==========================================================
            # 精确定位排列5数据段落
            # 页面结构：<title>排列5第26167期开奖公告</title>
            # 开奖号码在正文中：本期开奖号码：0 1 2 3 1
            # 必须通过title/h1中的排列5标记来确认这是排列5页面
            # ==========================================================
            
            # 检查页面标题是否明确是排列5
            title_match = re.search(r'排列[5五]第\s*(\d{5})\s*期', detail)
            h1_match = re.search(r'排列[5五]第\s*(\d{5})\s*期', detail)
            
            if not title_match and not h1_match:
                # 不是排列5开奖公告页面，跳过
                continue
            
            period_str = (title_match or h1_match).group(1)
            our_period = int('20' + period_str) if len(period_str) == 5 else int(period_str)
            
            # 搜索开奖号码（支持两种格式）
            # 格式1：开奖号码：0 1 2 3 1
            # 格式2：本期开奖号码：0 1 2 3 1
            num_m = re.search(r'(?:本期)?开奖号码[：:]\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', detail)
            
            if num_m:
                digits = ''.join(num_m.groups())
                winning4 = digits[:4]
                log(f"  江苏体彩网排列5: 期{our_period} 号码{digits} -> 前4位{winning4}")
                return winning4, our_period
            
            # 备用：搜索所有开奖号码，找排列5的（期号范围2026130+）
            all_nums = re.findall(r'(?:本期)?开奖号码[：:]\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)', detail)
            if all_nums and our_period >= 2026130:
                digits = ''.join(all_nums[0])
                winning4 = digits[:4]
                log(f"  江苏体彩网备用: 期{our_period} 号码{digits} -> 前4位{winning4}")
                return winning4, our_period

        log("  江苏体彩网未找到排列五开奖公告")
    except Exception as e:
        log(f"  江苏体彩网异常: {e}")
    return None, None


# ==========================================
# 数据源4：500彩票网（备用）
# ==========================================
def fetch_from_500():
    """从500彩票网获取排列五开奖"""
    log("尝试500彩票网...")
    try:
        html = _make_request('https://datachart.500.com/plw/history/newinc/history.php?start=1&end=1', timeout=15, retries=2)
        if not html or len(html) < 100:
            return None, None
        
        match = re.search(r'(\d{7}),(\d),(\d),(\d),(\d)', html)
        if match:
            period = int(match.group(1))
            digits = ''.join(match.groups()[1:5])
            log(f"  500彩票网成功: 期{period} 号码{digits}")
            return digits, period
        log("  500彩票网解析失败")
    except Exception as e:
        log(f"  500彩票网异常: {e}")
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
        ('500彩票网', fetch_from_500),
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
# match_balanced_braces
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
# 更新 index.html
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

        # 更新 embedded-data
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

        # 更新 let S
        s_var_match = re.search(r'let\s+S\s*=\s*\{', new_html)
        if s_var_match:
            brace_start = s_var_match.end() - 1
            old_s_block = match_balanced_braces(new_html, brace_start)
            if old_s_block:
                new_s_block = json.dumps(s_obj, ensure_ascii=False, indent=6)
                new_html = new_html[:brace_start] + new_s_block + new_html[brace_start+len(old_s_block):]
                updated = True
                log("已更新 let S 变量")

        if not updated:
            log("警告: index.html 未做任何更新")
            return False

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
    log("神仙连开奖填入任务 v8 开始")

    if not GH_TOKEN:
        log("✗ 严重错误：GH_TOKEN 环境变量为空！")
        return False

    log(f"GH_TOKEN 已配置 (长度: {len(GH_TOKEN)})")

    log("开始获取开奖号码...")
    winning4, period = fetch_winning_number()

    if not winning4:
        log("✗ 获取开奖号码失败，所有数据源均无返回")
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

    # 期号安全校验（排列5期号范围：2026000-2027000）
    current_period = data.get('period', 0)
    if current_period > 0 and period > 0:
        if period < 2026000 or period > 2027000:
            log(f"✗ 期号格式异常: {period}，不在排列5期号范围")
            return False
        if period < current_period - 10:
            log(f"✗ 期号安全检查失败: API返回期号{period}比当前期{current_period}小超过10期")
            return False
        if period > current_period + 2:
            log(f"✗ 期号安全检查失败: API返回期号{period}大于当前期+2({current_period+2})")
            return False
        log(f"期号安全检查通过: API返回{period}, 当前{current_period}")
    else:
        log(f"期号安全检查跳过: API返回{period}, 当前{current_period}")

    # 更新数据
    data['winning'] = winning4
    data['period'] = period
    data['lastUpdate'] = int(datetime.now().timestamp() * 1000)

    if 'history' not in data:
        data['history'] = []

    existing_periods = {h.get('period') for h in data['history']}
    if period not in existing_periods:
        data['history'].append({
            'period': period,
            'winning': winning4,
            'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })
        data['history'].sort(key=lambda x: x.get('period', 0), reverse=True)
        if len(data['history']) > 50:
            data['history'] = data['history'][:50]
        log(f"  已添加历史记录: 期{period}, 共{len(data['history'])}条")
    else:
        log(f"  期{period}已存在，跳过添加")

    # 保存到 GitHub
    save_success = False
    try:
        headers = {
            'Authorization': f'token {GH_TOKEN}',
            'Accept': 'application/vnd.github.v3+json'
        }
        sha_req = Request(f'https://api.github.com/repos/{REPO}/contents/{DATA_FILE}', headers=headers)
        sha_resp = urlopen(sha_req, timeout=30)
        file_sha = json.loads(sha_resp.read().decode('utf-8'))['sha']

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

    if save_success:
        update_index_html(data)
    else:
        log("✗ 跳过 index.html 更新")

    log("任务完成")
    return save_success


if __name__ == '__main__':
    success = main()
    sys.exit(0 if success else 1)
