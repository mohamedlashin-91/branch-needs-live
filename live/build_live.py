"""Branch Needs - half-hourly live branch stock (runs on GitHub Actions, published on GitHub Pages).

Each run:
  1. reads the day's link file from the Branch Needs site (which items / partners each branch shows, and the
     Find Item token of the morning build), plus the morning stock (Find Item files, cached once per build);
  2. downloads the store website's stock export (all branches, all items) - retried if the website is slow;
  3. publishes, under a hidden folder, only BRANCH stock (warehouse columns are dropped):
       meta.json         time of this stock, morning build token
       b/<store>.json    for each of your branches: o = its own items whose stock changed since the morning
                         (new quantity), d = {partner si: {item: change since the morning}} for its partners / items
       i/<00-99>.json    Find Item: {item: [[si, quantity], ...]} for every catalog branch that holds it now
If any step fails, nothing is published and the site keeps the last good live stock (or the morning stock).
Env: STOCK_URL (repository secret). Output folder: site/
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.request
from datetime import datetime, timedelta, timezone
import numpy as np
from python_calamine import CalamineWorkbook

SITE = 'https://branch-needs.web.app/data/'
RIYADH = timezone(timedelta(hours=3))
OUT = 'site'


def get_json(url, tries=3):
    if os.environ.get('LOCAL_SITE'):                      # local test: read the site files from a folder
        return json.load(open(os.path.join(os.environ['LOCAL_SITE'], url.rsplit('/', 1)[-1]), encoding='utf-8'))
    for k in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'Cache-Control': 'no-cache'}), timeout=120) as r:
                return json.loads(r.read().decode('utf-8'))
        except Exception as e:
            if k == tries - 1:
                raise
            print('retry', type(e).__name__); time.sleep(10)


def code(v):
    if isinstance(v, float) and v == int(v):
        return str(int(v))
    return str(v).strip()


def download(url, path, tries=3):
    if os.environ.get('LOCAL_STOCK'):                     # local test: use a stock file already downloaded
        return datetime.strptime(os.environ['LOCAL_STOCK_TIME'], '%Y-%m-%d %H:%M').replace(tzinfo=RIYADH), os.environ['LOCAL_STOCK']
    for k in range(tries):
        t0 = datetime.now(RIYADH)
        r = subprocess.run(['curl', '-sS', '--fail', '--max-time', '1200', '-o', path, '-X', 'POST',
                            '--data-urlencode', 'warehouse_option=all', '--data-urlencode', 'warehouse_codes=',
                            '--data-urlencode', 'sku_option=all', '--data-urlencode', 'skus=',
                            '--data-urlencode', 'download_excel=1', url], capture_output=True, text=True)
        ok = r.returncode == 0 and os.path.exists(path) and os.path.getsize(path) > 1_000_000
        print(f'download try {k + 1}: exit {r.returncode}, {os.path.getsize(path) if os.path.exists(path) else 0} bytes, '
              f'{(datetime.now(RIYADH) - t0).seconds}s', (r.stderr or '').strip()[:120])
        if ok:
            return t0, path
        time.sleep(60)
    sys.exit('stock website did not answer - nothing published this time')


def main():
    url = os.environ['STOCK_URL'].strip()
    key = hashlib.sha256((url + '|bn-live').encode()).hexdigest()[:24]
    print(f'::add-mask::{key}')
    ref = json.load(open('ref.json')) if os.path.exists('ref.json') else get_json(f'{SITE}lr_{key}.json')
    sx, codes, BR = ref['sx'], ref['codes'], ref['br']
    print(f'::add-mask::{sx}')
    si_of = {c: i for i, c in enumerate(codes)}
    print('build of', ref.get('built'), 'morning stock', ref.get('stock_date'), ref.get('stock_time'), '|', len(BR), 'branches')

    # morning stock per (si, item) from the morning Find Item files (cached for this build)
    mdir = f'morning/{sx}'
    os.makedirs(mdir, exist_ok=True)
    qm = {}
    for k in range(100):
        f = f'{mdir}/{k:02d}.json'
        if not os.path.exists(f):
            json.dump(get_json(f'{SITE}x_{sx}_{k:02d}.json'), open(f, 'w'))
        for it, L in json.load(open(f)).items():
            for si, q, _ in L:
                qm[(si, it)] = q
    print('morning stock lines', len(qm))

    t0, path = download(url, 'stock.xlsx')
    wb = CalamineWorkbook.from_path(path)
    r = wb.get_sheet_by_name(wb.sheet_names[0]).to_python()
    hdr = [str(x).strip() for x in r[0]]
    cols = [j for j, h in enumerate(hdr) if re.match(r'^\d{5}-\d{4}$', h) and h in si_of]   # branches only (no WAH warehouses)
    items = [code(row[0]) for row in r[2:]]
    A = np.array([[row[j] if isinstance(row[j], (int, float)) else 0 for j in cols] for row in r[2:]], dtype=float)
    A = np.rint(np.nan_to_num(A)).astype(int)
    sis = [si_of[hdr[j]] for j in cols]
    print(f'stock rows {len(items)}, catalog branches in the file {len(cols)} of {len(codes)}')
    if len(items) < 20000 or len(cols) < 0.8 * len(codes):
        sys.exit('stock file looks incomplete - nothing published this time')
    qn = {}
    nz = np.nonzero(A)
    for a, b in zip(*nz):
        qn[(sis[b], items[a])] = int(A[a, b])
    in_file = set(sis)

    # changes since the morning, per branch (si): {item: new - morning}
    chg = {}
    for k_ in set(qm) | set(qn):
        if k_[0] not in in_file:          # branch missing from this file: keep its morning stock
            continue
        dq = qn.get(k_, 0) - qm.get(k_, 0)
        if dq:
            chg.setdefault(k_[0], {})[k_[1]] = dq
    tstr = t0.strftime('%Y-%m-%d %H:%M')
    os.makedirs(f'{OUT}/{key}/b', exist_ok=True); os.makedirs(f'{OUT}/{key}/i', exist_ok=True)
    for c, v in BR.items():
        me, its = v['me'], set(v['it'])
        own = {it: qn.get((me, it), 0) for it in chg.get(me, {})}
        dd = {}
        for p in v['P']:
            x = {it: dq for it, dq in chg.get(p, {}).items() if it in its}
            if x:
                dd[str(p)] = x
        json.dump({'t': tstr, 'sx': sx, 'o': own, 'd': dd}, open(f'{OUT}/{key}/b/{c}.json', 'w'), separators=(',', ':'))
    sh = {}
    for (si, it), q in qn.items():
        if q >= 1:
            sh.setdefault(it[-2:].zfill(2), {}).setdefault(it, []).append([si, q])
    for k in range(100):
        s = sh.get(f'{k:02d}', {})
        for it in s:
            s[it].sort(key=lambda z: -z[1])
        json.dump(s, open(f'{OUT}/{key}/i/{k:02d}.json', 'w'), separators=(',', ':'))
    miss = sorted(set(range(len(codes))) - in_file)        # branches missing from this file keep their morning stock on the site
    json.dump({'t': tstr, 'sx': sx, 'rows': len(items), 'branches': len(cols), 'miss': miss, 'changed': sum(len(v) for v in chg.values())},
              open(f'{OUT}/{key}/meta.json', 'w'))
    open(f'{OUT}/index.html', 'w').write('<!doctype html><title>.</title>')
    open(f'{OUT}/robots.txt', 'w').write('User-agent: *\nDisallow: /\n')
    open(f'{OUT}/.nojekyll', 'w').write('')
    print(f'published stock of {tstr}: {len(BR)} branch files, {sum(len(v) for v in chg.values())} changed lines since the morning')


if __name__ == '__main__':
    main()
