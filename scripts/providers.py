#!/usr/bin/env python3
"""查詢每部片在台灣的正版觀看管道（TMDB Watch Providers，資料由 JustWatch 提供），存成 providers.json。

每次只重新查「從沒查過」或「超過 STALE_DAYS 天沒查」的片，所以每天執行時，
新片當天就會有資料，舊片大約每週輪一次。

需要的環境變數：TMDB_API_KEY
"""
import json, os, sys, time, datetime
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update  # 共用 tmdb() 和 get()

ROOT = update.ROOT
OUT = os.path.join(ROOT, 'providers.json')
IDS = os.path.join(ROOT, 'data', 'tmdb_ids.json')
REGION = 'TW'
STALE_DAYS = 7
MAX_PER_RUN = int(os.environ.get('PROVIDERS_MAX', '2000'))
KINDS = ['flatrate', 'free', 'ads', 'rent', 'buy']


def main():
    if not update.KEY:
        print('沒有 TMDB_API_KEY，略過觀看管道查詢', file=sys.stderr)
        return
    films = json.load(open(update.FILMS, encoding='utf-8'))['films']
    ids = json.load(open(IDS)) if os.path.exists(IDS) else {}
    data = json.load(open(OUT, encoding='utf-8')) if os.path.exists(OUT) else {}
    data.setdefault('p', {})      # 平台：id -> [名稱, logo 路徑]
    data.setdefault('f', {})      # 片：slug -> {at, link, flatrate:[id], ...}
    today = datetime.date.today()
    cutoff = (today - datetime.timedelta(days=STALE_DAYS)).isoformat()

    todo = []
    for f in films:
        tid = f.get('tm') or ids.get(f['slug'])
        if not tid:
            continue
        rec = data['f'].get(f['slug'])
        if rec is None or rec.get('at', '') < cutoff:
            todo.append((rec is not None, f['slug'], tid))
    todo.sort()  # 沒查過的先查
    todo = todo[:MAX_PER_RUN]
    print(f'需要查詢 {len(todo)} 部')

    done = 0
    for _, slug, tid in todo:
        try:
            res = update.tmdb(f'/movie/{tid}/watch/providers')
        except RuntimeError as e:
            print(e, file=sys.stderr)
            continue
        tw = (res or {}).get('results', {}).get(REGION, {})
        rec = {'at': today.isoformat()}
        if tw.get('link'):
            rec['link'] = tw['link']
        for k in KINDS:
            lst = sorted(tw.get(k, []), key=lambda x: x.get('display_priority', 99))
            if lst:
                rec[k] = [p['provider_id'] for p in lst]
                for p in lst:
                    data['p'][str(p['provider_id'])] = [p['provider_name'], p.get('logo_path') or '']
        data['f'][slug] = rec
        done += 1
        time.sleep(0.05)

    data['updated'] = today.isoformat()
    json.dump(data, open(OUT, 'w', encoding='utf-8'), ensure_ascii=False, separators=(',', ':'))
    have = sum(1 for r in data['f'].values() if any(k in r for k in KINDS))
    print(f'查詢 {done} 部；目前 {len(data["f"])} 部有紀錄，其中 {have} 部在台灣有正版管道')


if __name__ == '__main__':
    main()
