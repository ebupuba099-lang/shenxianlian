/**
 * 排列5开奖数据代理 API
 * 部署到 Vercel 后访问: https://your-project.vercel.app/api/pl5
 * 
 * 本地数据源: 彩经网 + 江苏体彩网
 * Vercel 免费额度: 每月100万次请求，完全够用
 */

export default async function handler(req, res) {
  // CORS
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET');

  try {
    const result = await fetchPl5Data();
    if (result) {
      return res.status(200).json({ success: true, ...result });
    }
    return res.status(404).json({ success: false, error: '所有数据源均失败' });
  } catch (e) {
    return res.status(500).json({ success: false, error: e.message });
  }
}

async function fetchPl5Data() {
  const sources = [
    fetchCjcp,      // 彩经网
    fetchJsLottery, // 江苏体彩网
    fetch500,       // 500彩票网
  ];

  for (const fn of sources) {
    try {
      const result = await fn();
      if (result && result.winning) {
        return result;
      }
    } catch (e) {
      console.error(fn.name, e.message);
    }
  }
  return null;
}

// ========== 数据源1: 彩经网移动端 ==========
async function fetchCjcp() {
  const urls = [
    'https://m.cjcp.com.cn/kaijiang/pl5/',
    'https://m.cjcp.cn/kaijiang/pl5/'
  ];
  
  for (const url of urls) {
    try {
      const resp = await fetch(url, {
        headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
      });
      if (!resp.ok) continue;
      
      const html = await resp.text();
      if (html.length < 3000) continue;
      
      const m = html.match(/第\s*(\d{7})\s*期[\s\S]*?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)/);
      if (m) {
        const period = parseInt(m[1]);
        const digits = m.slice(2).join('');
        if (period > 2026000 && period < 2027000) {
          return { period, winning: digits.slice(0, 4), full: digits, source: '彩经网' };
        }
      }
    } catch (e) {
      continue;
    }
  }
  return null;
}

// ========== 数据源2: 江苏体彩网 ==========
async function fetchJsLottery() {
  try {
    // 获取文章列表
    const listResp = await fetch('https://api.js-lottery.com/', {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
    });
    if (!listResp.ok) return null;
    
    const listHtml = await listResp.text();
    const postIds = [...listHtml.matchAll(/post-(\d+)\.html/g)].map(m => m[1]);
    
    for (const id of postIds.slice(0, 5)) {
      try {
        const detailResp = await fetch(`https://api.js-lottery.com/post-${id}.html`, {
          headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
        });
        if (!detailResp.ok) continue;
        
        const html = await detailResp.text();
        
        // 检查是否是排列5
        const titleMatch = html.match(/排列[5五]第\s*(\d{5})\s*期/);
        if (!titleMatch) continue;
        
        const period = parseInt('20' + titleMatch[1]);
        const numMatch = html.match(/(?:本期)?开奖号码[：:]?\s*(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)/);
        if (numMatch) {
          const digits = numMatch.slice(1).join('');
          if (period > 2026000 && period < 2027000) {
            return { period, winning: digits.slice(0, 4), full: digits, source: '江苏体彩网' };
          }
        }
      } catch (e) {
        continue;
      }
    }
  } catch (e) {
    return null;
  }
  return null;
}

// ========== 数据源3: 500彩票网 ==========
async function fetch500() {
  try {
    const resp = await fetch('https://datachart.500.com/plw/history/newinc/history.php?start=26001&end=26999', {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' }
    });
    if (!resp.ok) return null;
    
    const html = await resp.text();
    const rows = [...html.matchAll(/(\d{5})\s+(\d)\s+(\d)\s+(\d)\s+(\d)\s+(\d)/g)];
    if (rows.length > 0) {
      const last = rows[rows.length - 1];
      const period = parseInt('20' + last[1]);
      const digits = last.slice(2).join('');
      if (period > 2026000 && period < 2027000) {
        return { period, winning: digits.slice(0, 4), full: digits, source: '500彩票网' };
      }
    }
  } catch (e) {
    return null;
  }
  return null;
}
