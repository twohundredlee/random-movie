#!/usr/bin/env python3
"""每天由 GitHub Actions 執行：讀 Letterboxd RSS，把新看的片、評分、評論併進 films.json。

需要的環境變數：
  TMDB_API_KEY  TMDB 的 API Key（v3）或 Read Access Token（v4，eyJ 開頭）
  LB_USER       Letterboxd 帳號（預設 twohundredlee）
"""
import json, os, re, sys, html, time, urllib.request, urllib.error
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILMS = os.path.join(ROOT, 'films.json')
SEEN = os.path.join(ROOT, 'data', 'seen.json')
USER = os.environ.get('LB_USER', 'twohundredlee')
KEY = os.environ.get('TMDB_API_KEY', '').strip()
UA = 'Mozilla/5.0 (compatible; letterboxd-picker/1.0; +https://github.com/%s)' % USER
NS = {'lb': 'https://letterboxd.com', 'tmdb': 'https://themoviedb.org'}
CJK = re.compile(r'[一-鿿]')
COUNTRY = {'United States of America': 'USA', 'United Kingdom': 'UK'}


def get(url, headers=None, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': UA, **(headers or {})})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            err = e
        except Exception as e:  # 連線錯誤
            err = e
        time.sleep(3 * (i + 1))
    raise RuntimeError(f'抓取失敗：{url}（{err}）')


def tmdb(path, **params):
    if not KEY:
        return None
    headers = {'Accept': 'application/json'}
    if KEY.startswith('eyJ'):
        headers['Authorization'] = 'Bearer ' + KEY
    else:
        params['api_key'] = KEY
    q = '&'.join(f'{k}={urllib.request.quote(str(v))}' for k, v in params.items())
    raw = get(f'https://api.themoviedb.org/3{path}?{q}', headers)
    return json.loads(raw) if raw else None


def text(el, tag):
    x = el.find(tag, NS)
    return (x.text or '').strip() if x is not None and x.text else ''


def review_from(desc):
    """從 RSS description 取出評論文字；只有『Watched on …』代表沒寫評論。"""
    paras = re.findall(r'<p>(.*?)</p>', desc or '', flags=re.S)
    out = []
    for p in paras:
        if '<img' in p:
            continue
        t = html.unescape(re.sub(r'<br\s*/?>', '\n', p))
        t = re.sub(r'<[^>]+>', '', t).strip()
        if not t or re.match(r'^Watched on \w+ \w+ \d+, \d{4}\.?$', t) or t == 'This review may contain spoilers.':
            continue
        out.append(t)
    return '\n\n'.join(out)


def film_info(tid, name, year):
    """用 TMDB 補齊新片資料（中文片名、簡介、導演、主演、片長、類型、海報）。"""
    f = {'n': name, 'y': year, 'o': '', 'dir': [], 'g': [], 'c': [], 'cast': [], 'rt': '', 'tl': '', 'syn': '', 'avg': None}
    if not tid:
        return f
    zh = tmdb(f'/movie/{tid}', language='zh-TW', append_to_response='credits')
    en = tmdb(f'/movie/{tid}', language='en-US')
    if not zh or not en:
        return f
    f['o'] = zh.get('original_title') or ''
    if f['o'] == name:
        f['o'] = ''
    crew = zh.get('credits', {}).get('crew', [])
    f['dir'] = [c['name'] for c in crew if c.get('job') == 'Director']
    f['cast'] = [c['name'] for c in zh.get('credits', {}).get('cast', [])[:5]]
    f['g'] = [g['name'] for g in en.get('genres', [])]
    f['c'] = [COUNTRY.get(c['name'], c['name']) for c in en.get('production_countries', [])]
    f['rt'] = str(en.get('runtime') or '') if en.get('runtime') else ''
    f['tl'] = en.get('tagline') or ''
    f['syn'] = en.get('overview') or ''
    if zh.get('poster_path') or en.get('poster_path'):
        f['img'] = 'https://image.tmdb.org/t/p/w342' + (zh.get('poster_path') or en.get('poster_path'))
    tw = (zh.get('title') or '').strip()
    if tw and CJK.search(tw) and tw != name:
        f['tw'] = tw
    elif f['o'] and CJK.search(f['o']) and {'Taiwan', 'Hong Kong', 'China'} & set(f['c']):
        f['tw'] = f['o']
    if zh.get('tagline') and zh['tagline'] != f['tl']:
        f['twtl'] = zh['tagline']
    if zh.get('overview') and zh['overview'] != f['syn']:
        f['twsyn'] = zh['overview']
    return f


def main():
    data = json.load(open(FILMS, encoding='utf-8'))
    films = data['films']
    by_slug = {f['slug']: f for f in films}
    seen = set(json.load(open(SEEN))) if os.path.exists(SEEN) else set()

    rss = get(f'https://letterboxd.com/{USER}/rss/')
    items = ET.fromstring(rss).findall('./channel/item')
    print(f'RSS 共 {len(items)} 筆')

    added, changed = [], 0
    for it in reversed(items):  # 舊的先處理，新片最後會排在最前面
        guid = text(it, 'guid')
        if not guid.startswith(('letterboxd-review-', 'letterboxd-watch-')) or guid in seen:
            continue
        m = re.search(r'/film/([^/]+)/', text(it, 'link'))
        if not m:
            continue
        slug = m.group(1)
        name, year = text(it, 'lb:filmTitle'), text(it, 'lb:filmYear')
        watched = text(it, 'lb:watchedDate')
        rating = text(it, 'lb:memberRating')
        rev = review_from(text(it, 'description'))
        f = by_slug.get(slug)
        if f is None:
            info = film_info(text(it, 'tmdb:movieId'), name, year)
            f = {'slug': slug, **info, 'r': None, 'lk': False, 'rev': [], 'w': watched, 'dc': 0, 's': None}
            films.insert(0, f)
            by_slug[slug] = f
            added.append(f.get('tw') or name)
        if rating:
            f['r'] = float(rating)
        if text(it, 'lb:memberLike') == 'Yes':
            f['lk'] = True
        if rev and not any(x['t'] == rev for x in f['rev']):
            f['rev'].insert(0, {'d': watched, 't': rev, 'rw': text(it, 'lb:rewatch') == 'Yes'})
            f['rev'].sort(key=lambda x: x['d'], reverse=True)
        if watched and (not f.get('w') or watched < f['w']):
            f['w'] = watched
        f['dc'] = (f.get('dc') or 0) + 1
        seen.add(guid)
        changed += 1
        time.sleep(0.3)

    if not changed:
        print('沒有新紀錄')
        return
    json.dump(data, open(FILMS, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    os.makedirs(os.path.dirname(SEEN), exist_ok=True)
    json.dump(sorted(seen), open(SEEN, 'w'), indent=0)
    print(f'更新 {changed} 筆紀錄，新增 {len(added)} 部：{"、".join(added) or "無"}')


if __name__ == '__main__':
    try:
        main()
    except RuntimeError as e:
        print(e, file=sys.stderr)
        sys.exit(1)
