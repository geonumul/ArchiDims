import json
import os
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'plugin', 'kg_arch_dims', 'data.json')
OUT = os.path.join(ROOT, 'law_snapshot.json')
CONF = os.path.join(ROOT, 'tools', 'config.local.json')
BASE = 'https://www.law.go.kr/DRF/'
DATA_DATE = '20261120'
LAW_RE = re.compile(r'(법|규칙|규정|시행령|최저주거기준|NFTC|지침|승강기 안전)')


def log(*a):
    print(datetime.now().strftime('%H:%M:%S'), *a, flush=True)


def load_oc():
    oc = os.environ.get('LAW_OC', '').strip()
    if oc:
        return oc
    if os.path.exists(CONF):
        with open(CONF, encoding='utf-8') as f:
            oc = json.load(f).get('oc', '').strip()
    if not oc and sys.stdin.isatty():
        oc = input('법제처 OPEN API 인증키(OC): ').strip()
        os.makedirs(os.path.dirname(CONF), exist_ok=True)
        with open(CONF, 'w', encoding='utf-8') as f:
            json.dump({'oc': oc}, f)
    if not oc:
        sys.exit('인증키(OC)가 없습니다. tools/config.local.json 에 {"oc": "..."} 를 넣으세요.')
    return oc


OC = None


class AuthError(Exception):
    pass


def get(path, params):
    q = urllib.parse.urlencode({'OC': OC, 'type': 'JSON', **params})
    req = urllib.request.Request(BASE + path + '?' + q, headers={'User-Agent': 'Mozilla/5.0'})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read().decode('utf-8', 'replace')
            break
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2)
    time.sleep(0.3)
    try:
        data = json.loads(body)
    except ValueError:
        raise RuntimeError('JSON 아님: ' + re.sub(r'<[^>]+>', ' ', body)[:150])
    if isinstance(data, dict) and '실패' in str(data.get('result', '')) and len(data) <= 3:
        raise AuthError(f"{data.get('result')} {data.get('msg', '')}")
    return data


def norm(s):
    return re.sub(r'[\s·ㆍ・‧]', '', str(s or ''))


def parse_src(src):
    s = str(src or '').strip()
    info = {}
    m = re.search(r'\s*별표\s*(\d+)(?:의\s*(\d+))?\s*$', s)
    if m:
        info['byul'] = (int(m.group(1)), int(m.group(2) or 0))
        s = s[:m.start()]
    m = re.search(r'\s*제\s*(\d+)\s*조(?:\s*의\s*(\d+))?\s*$', s)
    if m:
        info['jo'] = (int(m.group(1)), int(m.group(2) or 0))
        s = s[:m.start()]
    s = re.sub(r'\s*\([^)]*\)\s*$', '', s).strip()
    info['name'] = s
    info['kind'] = 'law' if re.search(r'(법|법률|시행령|시행규칙|규칙|규정)$', s) else 'admrul'
    return info


def each_dict(o):
    if isinstance(o, dict):
        yield o
        for v in o.values():
            yield from each_dict(v)
    elif isinstance(o, list):
        for v in o:
            yield from each_dict(v)


def texts(o, inside=False, acc=None):
    acc = [] if acc is None else acc
    if isinstance(o, dict):
        for k, v in o.items():
            hit = str(k).endswith('내용')
            if isinstance(v, str):
                if hit:
                    acc.append(v)
            else:
                texts(v, hit, acc)
    elif isinstance(o, list):
        for v in o:
            if isinstance(v, str):
                if inside:
                    acc.append(v)
            else:
                texts(v, inside, acc)
    return acc


def clean(s):
    s = re.sub(r'<br\s*/?>', '\n', str(s or ''), flags=re.I)
    s = re.sub(r'<[^>]+>', '', s)
    for a, b in (('&nbsp;', ' '), ('&lt;', '<'), ('&gt;', '>'), ('&amp;', '&'), ('&quot;', '"')):
        s = s.replace(a, b)
    s = re.sub(r'[ \t]+', ' ', s)
    s = re.sub(r'\n\s*\n+', '\n', s)
    return s.strip()


def to_i(v):
    try:
        return int(str(v).strip() or 0)
    except ValueError:
        return 0


_search = {}
_full = {}


def find_law(name):
    key = norm(name)
    if key in _search:
        return _search[key]
    pick = None
    for q in (name.replace('·', 'ㆍ'), ' '.join(re.sub(r'[·ㆍ]', ' ', name).split()[:3])):
        data = get('lawSearch.do', {'target': 'law', 'query': q, 'display': '50'})
        lst = [h for h in each_dict(data) if h.get('법령명한글')]
        pick = next((h for h in lst if norm(h['법령명한글']) == key), None) or \
            next((h for h in lst if key in norm(h['법령명한글'])), None)
        if pick:
            break
    res = None if not pick else {
        'name': pick['법령명한글'], 'mst': str(pick.get('법령일련번호', '')),
        'eff': str(pick.get('시행일자', '')), 'prom': str(pick.get('공포일자', ''))}
    _search[key] = res
    return res


def full_law(mst):
    if mst not in _full:
        _full[mst] = get('lawService.do', {'target': 'law', 'MST': mst})
    return _full[mst]


def jo_title(h):
    no, g = to_i(h.get('조문번호')), to_i(h.get('조문가지번호'))
    t = f"제{no}조" + (f"의{g}" if g else '')
    return f"{t}({h['조문제목']})" if h.get('조문제목') else t


def jo_units(data):
    return [h for h in each_dict(data) if '조문번호' in h and str(h.get('조문여부', '')) != '전문']


def article(data, jo):
    for h in jo_units(data):
        if to_i(h.get('조문번호')) == jo[0] and to_i(h.get('조문가지번호')) == jo[1]:
            return [{'title': jo_title(h), 'text': clean('\n'.join(texts(h)))}]
    return []


def hint_articles(data, hints):
    hs = list(dict.fromkeys(w for w in hints if len(w) >= 2))
    scored = []
    for h in jo_units(data):
        title, body = str(h.get('조문제목', '')), ' '.join(texts(h))
        sc = sum((5 if w in title else 0) + (1 if w in body else 0) for w in hs)
        if sc > 0:
            scored.append((sc, h))
    scored.sort(key=lambda x: -x[0])
    return [{'title': jo_title(h), 'text': clean('\n'.join(texts(h)))} for _, h in scored[:2]]


def byul(data, b):
    lst = [h for h in each_dict(data) if '별표번호' in h]
    u = next((h for h in lst if to_i(h['별표번호']) == b[0] and to_i(h.get('별표가지번호')) == b[1]
              and str(h.get('별표구분', '')) != '서식'), None) or \
        next((h for h in lst if to_i(h['별표번호']) == b[0]), None)
    if not u:
        return []
    title = f"별표 {b[0]}" + (f"의{b[1]}" if b[1] else '') + f" {u.get('별표제목', '')}"
    return [{'title': title.strip(), 'text': clean('\n'.join(texts(u)))}]


def web_url(name, info):
    seg = ['법령', name.replace(' ', '')]
    if info.get('jo'):
        jo = info['jo']
        seg.append(f"제{jo[0]}조" + (f"의{jo[1]}" if jo[1] else ''))
    return 'https://www.law.go.kr/' + '/'.join(urllib.parse.quote(x) for x in seg)


def hints_of(d):
    words = [d['c']] + (d.get('k') or '').split() + re.sub(r'[()·,~]', ' ', d['n']).split()
    return [w for w in words if len(w) >= 2]


def build_item(d):
    info = parse_src(d['src'])
    if info['kind'] == 'admrul':
        data = get('lawSearch.do', {'target': 'admrul', 'query': info['name'], 'display': '10'})
        lst = [h for h in each_dict(data) if h.get('행정규칙명')][:6]
        items = []
        for h in lst:
            link = str(h.get('행정규칙상세링크', ''))
            items.append({'title': h['행정규칙명'], 'text': f"시행 {h.get('시행일자', '')} · {h.get('행정규칙종류', '')}".strip(),
                          'url': ('https://www.law.go.kr' + re.sub(r'OC=[^&]*&?', '', link).replace('type=XML', 'type=HTML')) if link else None})
        return {'ok': True, 'admrul': True, 'law': info['name'], 'items': items,
                'url': 'https://www.law.go.kr/행정규칙/' + urllib.parse.quote(info['name'].replace(' ', '')),
                'error': None if items else '행정규칙 검색 결과가 없습니다'}, None
    law = find_law(info['name'])
    if not law:
        return {'ok': False, 'error': f"'{info['name']}' 법령을 찾지 못했습니다"}, None
    data = full_law(law['mst'])
    if info.get('byul'):
        items = byul(data, info['byul'])
    elif info.get('jo'):
        items = article(data, info['jo'])
    else:
        items = hint_articles(data, hints_of(d))
    res = {'ok': True, 'law': law['name'], 'eff': law['eff'], 'prom': law['prom'], 'items': items,
           'url': web_url(law['name'], info), 'changed': law['eff'] > DATA_DATE}
    if not items:
        res['error'] = '해당 조문을 찾지 못했습니다. 법령 사이트에서 확인하세요.'
    return res, law


def build():
    with open(DATA, encoding='utf-8') as f:
        data = json.load(f)
    targets = [d for d in data if d.get('src') and LAW_RE.search(d['src'])]
    log(f'법정 항목 {len(targets)}개')
    snap = {'version': 1, 'dataDate': DATA_DATE, 'laws': {}, 'items': {}}
    fails = 0
    for i, d in enumerate(targets, 1):
        try:
            res, law = build_item(d)
        except AuthError as e:
            sys.exit(f'인증 실패: {e}\n등록한 IP의 PC에서 실행했는지, 신청이 승인됐는지 확인하세요.')
        except Exception as e:
            res, law = {'ok': False, 'error': str(e)[:200]}, None
        if not res.get('ok') or res.get('error'):
            fails += 1
        snap['items'][d['c'] + '|' + d['n']] = res
        if law:
            snap['laws'][norm(law['name'])] = {'name': law['name'], 'eff': law['eff'], 'changed': law['eff'] > DATA_DATE}
        if i % 20 == 0:
            log(f'{i}/{len(targets)}')
    arts, idx = {}, {}
    for r in snap['items'].values():
        if r.get('admrul') or not r.get('items'):
            continue
        ids = []
        for a in r['items']:
            key = r['law'] + '|' + a['title']
            if key not in idx:
                idx[key] = 'a' + str(len(idx))
                arts[idx[key]] = a
            ids.append(idx[key])
        r['items'] = ids
    snap['version'] = 2
    snap['arts'] = arts
    snap['generated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    log(f'완료: 항목 {len(snap["items"])}개, 법령 {len(snap["laws"])}개, 확인 필요 {fails}개')
    return snap


def same_as_existing(snap):
    if not os.path.exists(OUT):
        return False
    try:
        with open(OUT, encoding='utf-8') as f:
            old = json.load(f)
    except ValueError:
        return False
    a = dict(old); b = dict(snap)
    a.pop('generated', None); b.pop('generated', None)
    return a == b


def git(*args):
    return subprocess.run(['git', '-C', ROOT, *args], capture_output=True, text=True, encoding='utf-8')


def main():
    global OC
    OC = load_oc()
    push = '--push' in sys.argv
    if push:
        git('pull', '--rebase', '--autostash')
    snap = build()
    if same_as_existing(snap):
        log('변경 없음. 파일을 그대로 둡니다.')
        return
    with open(OUT, 'w', encoding='utf-8') as f:
        json.dump(snap, f, ensure_ascii=False, separators=(',', ':'))
    log('저장:', OUT)
    if push:
        changed = [v['name'] for v in snap['laws'].values() if v['changed']]
        msg = f"법령 스냅샷 갱신 {snap['generated']}" + (f" (개정: {', '.join(changed[:5])})" if changed else '')
        git('add', 'law_snapshot.json')
        r = git('commit', '-m', msg)
        log(r.stdout.strip() or r.stderr.strip())
        r = git('push')
        log('push 완료' if r.returncode == 0 else 'push 실패: ' + r.stderr.strip())


if __name__ == '__main__':
    main()
