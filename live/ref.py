"""Reads the day's link file once (saved as ref.json for build_live.py) and gives the cache a name for this build.
Nothing secret is printed: the hidden folder name and the build token are masked in the logs."""
import hashlib, json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_live import SITE, get_json

url = os.environ['STOCK_URL'].strip()
key = hashlib.sha256((url + '|bn-live').encode()).hexdigest()[:24]
print(f'::add-mask::{key}')
ref = get_json(f'{SITE}lr_{key}.json')
print(f"::add-mask::{ref['sx']}")
json.dump(ref, open('ref.json', 'w'))
with open(os.environ.get('GITHUB_OUTPUT', '/dev/null'), 'a') as f:
    f.write('build=' + hashlib.sha256(ref['sx'].encode()).hexdigest()[:12] + '\n')
print('link file of', ref.get('built'), '-', len(ref['br']), 'branches')
