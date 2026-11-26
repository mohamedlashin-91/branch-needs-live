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
       s.json            for the area / supervisor overviews: o = {store: its own changed items (new quantity)},
                         na = stores not in this stock file (kept on the morning stock)
If any step fails, nothing is published and the site keeps the last good live stock (or the morning stock).
Env: STOCK_URL (repository secret). Output folder: site/
"""
import hashlib, json, os, re, subprocess, sys, time, urllib.parse, urllib.request
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


def download(url, path, tries=4):
    if os.environ.get('LOCAL_STOCK'):                     # local test: use a stock file already downloaded
        return datetime.strptime(os.environ['LOCAL_STOCK_TIME'], '%Y-%m-%d %H:%M').replace(tzinfo=RIYADH), os.environ['LOCAL_STOCK']
    for k in range(tries):
        t0 = datetime.now(RIYADH)
        r = subprocess.run(['curl', '-sS', '--fail', '--max-time', '900', '-o', path, '-X', 'POST',
                            '--data-urlencode', 'warehouse_option=all', '--data-urlencode', 'warehouse_codes=',
                            '--data-urlencode', 'sku_option=all', '--data-urlencode', 'skus=',
                            '--data-urlencode', 'download_excel=1', url], capture_output=True, text=True)
        n = os.path.getsize(path) if os.path.exists(path) else 0
        ok = r.returncode == 0 and n > 1_000_000
        kind = ''
        if n and not ok:                                  # say what came back, without printing any of it
            head = open(path, 'rb').read(400).lower()
            kind = ' (a web page, not the Excel file)' if b'<html' in head or b'<!doctype' in head else ' (not the Excel file)'
        print(f'download try {k + 1}: exit {r.returncode}, {n} bytes{kind}, {(datetime.now(RIYADH) - t0).seconds}s')
        if ok:
            return t0, path
        if k < tries - 1:
            time.sleep(60 * (k + 1))                      # the website is sometimes busy: wait 1, 2, 3 minutes
    sys.exit('stock website did not answer - nothing published this time')


def publish_off(why):
    """Kill switch: publish only a meta.json the site will not accept (sx 'off'), so pages show the morning numbers."""
    url = os.environ['STOCK_URL'].strip()
    key = hashlib.sha256((url + '|bn-live').encode()).hexdigest()[:24]
    print(f'::add-mask::{key}'); print(f'::add-mask::{urllib.parse.urlparse(url).hostname}')
    os.makedirs(f'{OUT}/{key}', exist_ok=True)
    json.dump({'t': datetime.now(RIYADH).strftime('%Y-%m-%d %H:%M'), 'sx': 'off'}, open(f'{OUT}/{key}/meta.json', 'w'))
    open(f'{OUT}/index.html', 'w').write('<!doctype html><title>.</title>')
    open(f'{OUT}/robots.txt', 'w').write('User-agent: *\nDisallow: /\n')
    open(f'{OUT}/.nojekyll', 'w').write('')
    print('live stock switched off:', why)


def main():
    if os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'OFF')):
        return publish_off('live/OFF is present')
    url = os.environ['STOCK_URL'].strip()
    key = hashlib.sha256((url + '|bn-live').encode()).hexdigest()[:24]
    print(f'::add-mask::{key}'); print(f'::add-mask::{urllib.parse.urlparse(url).hostname}')
    ref = json.load(open('ref.json')) if os.path.exists('ref.json') else get_json(f'{SITE}lr_{key}.json')
    sx, codes, BR = ref['sx'], ref['codes'], ref['br']
    print(f'::add-mask::{sx}')
    si_of = {c: i for i, c in enumerate(codes)}
    print('build of', ref.get('built'), 'morning stock', ref.get('stock_date'), ref.get('stock_time'), '|', len(BR), 'branches')

    # morning stock per (si, item) from the morning Find Item files (cached for this build)
    mdir = f'morning/{sx}'
    os.makedirs(mdir, exist_ok=True)
    qm, spm = {}, {}
    for k in range(100):
        f = f'{mdir}/{k:02d}.json'
        if not os.path.exists(f):
            json.dump(get_json(f'{SITE}x_{sx}_{k:02d}.json'), open(f, 'w'))
        for it, L in json.load(open(f)).items():
            for si, q, sp in L:
                qm[(si, it)] = q
                if sp:
                    spm[(si, it)] = sp
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
    tm, tn = {}, {}
    for (si, _), q in qm.items():
        tm[si] = tm.get(si, 0) + q
    for (si, _), q in qn.items():
        tn[si] = tn.get(si, 0) + max(q, 0)
    bad = sorted(si for si in in_file if tm.get(si, 0) >= 50 and tn.get(si, 0) < 0.2 * tm[si])
    if bad:
        print('branch columns that look empty or broken, kept on the morning stock:', ', '.join(codes[i] for i in bad))
        in_file -= set(bad)
        qn = {k_: v for k_, v in qn.items() if k_[0] in in_file}
    dup = len(items) - len(set(items))
    if dup:
        print('duplicate item rows in the file:', dup)

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

    # transfer lines: how much of each planned line is still worth moving now (same answer for both branches)
    # v = [sender spare now or -1, receiver need/room now or -1, receiver stock increase]; the page takes
    # min(planned qty, sender spare, receiver need/room - or planned qty minus the increase when unknown)
    pc = {}
    PN, PR, PS = ref.get('pn', {}), ref.get('pr', {}), ref.get('ps', {})
    dlt = lambda si, it: (qn.get((si, it), 0) - qm.get((si, it), 0)) if si in in_file else 0
    nl = 0
    for S, R, it, qx in ref.get('pl', []):
        dS, dR = dlt(S, it), dlt(R, it)
        if not dS and not dR:
            continue
        b0 = spm.get((S, it))
        if b0 is None:
            b0 = PS.get(str(S), {}).get(it)
        sc = -1 if b0 is None or not dS else max(0, b0 + dS)         # -1: unknown or unchanged since the morning
        n = PN.get(str(R), {}).get(it)
        if n is not None:
            dem, soh, ordm, need = n
            if dR:
                q = qn.get((R, it), 0)
                ordn = max(0, ordm - max(0, q - soh)); pos = q + ordn
                rc = 0 if pos >= 0.5 * dem else max(1, int(round(need + (soh + ordm - pos))))
            else:
                rc = -1
        elif dR and str(R) in PR and it in PR[str(R)]:
            rc = max(0, PR[str(R)][it] - dR)
        else:
            rc = -1
        ri = max(0, dR)
        cap = min(sc if sc >= 0 else qx, rc if rc >= 0 else max(0, qx - ri))
        if cap >= qx:
            continue
        v = [sc, rc, ri]
        pc.setdefault(S, {})[f'{R}:{it}'] = v
        pc.setdefault(R, {})[f'{S}:{it}'] = v
        nl += 1
    print(f'transfer lines checked {len(ref.get("pl", []))}, reduced now {nl}')
    for c, v in BR.items():
        me, its = v['me'], set(v['it'])
        own = {it: qn.get((me, it), 0) for it in chg.get(me, {})}
        dd = {}
        for p in v['P']:
            x = {it: dq for it, dq in chg.get(p, {}).items() if it in its}
            if x:
                dd[str(p)] = x
        json.dump({'t': tstr, 'sx': sx, 'o': own, 'd': dd, 'pc': pc.get(me, {})}, open(f'{OUT}/{key}/b/{c}.json', 'w'), separators=(',', ':'))
    so, na = {}, []
    for c, v in BR.items():
        if v['me'] in in_file:
            its = set(v['it'])
            so[c] = {it: qn.get((v['me'], it), 0) for it in chg.get(v['me'], {}) if it in its}
        else:
            na.append(c)
    json.dump({'t': tstr, 'sx': sx, 'o': so, 'na': sorted(na)}, open(f'{OUT}/{key}/s.json', 'w'), separators=(',', ':'))
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
