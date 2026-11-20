import gzip
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_snapshot as U

ROOT = U.ROOT
OUT = os.path.join(ROOT, 'lawdb')
SITE = 'https://www.law.go.kr'

LAWS = [
    '건축법', '건축법 시행령', '건축법 시행규칙',
    '국토의 계획 및 이용에 관한 법률', '국토의 계획 및 이용에 관한 법률 시행령',
    '주차장법', '주차장법 시행령', '주차장법 시행규칙',
    '건축물의 피난ㆍ방화구조 등의 기준에 관한 규칙', '건축물의 설비기준 등에 관한 규칙',
    '주택건설기준 등에 관한 규정', '장애인ㆍ노인ㆍ임산부 등의 편의증진 보장에 관한 법률 시행규칙',
]
TYPES = [
    ('건축', re.compile(r'^건축 ?조례$')),
    ('계획', re.compile(r'^(도시ㆍ군|도시·군|도시|군)? ?계획 ?조례$')),
    ('주차', re.compile(r'^주차장 ?(설치 ?및 ?관리 ?(에 ?관한 ?)?)?조례$')),
]
TYPE_LABEL = {'건축': '건축 조례', '계획': '도시계획 조례', '주차': '주차장 조례'}
QUERIES = ['건축 조례', '도시계획 조례', '군계획 조례', '계획조례', '주차장 설치', '주차장 조례']


def as_list(v):
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def ordin_type(org, name):
    org, name = org.strip(), name.strip()
    last = org.split()[-1] if org else ''
    if name.startswith(org):
        rest = name[len(org):]
    elif last and name.startswith(last):
        rest = name[len(last):]
    else:
        return None
    rest = rest.strip()
    for t, rx in TYPES:
        if rx.match(rest):
            return t
    return None


def fetch_bundle():
    laws, ordin = [], []
    for name in LAWS:
        s = U.get('lawSearch.do', {'target': 'law', 'query': name, 'display': '50'})
        hit = next((h for h in U.each_dict(s) if U.norm(h.get('법령명한글')) == U.norm(name)), None)
        if not hit:
            U.log('법령 없음:', name)
            continue
        body = U.get('lawService.do', {'target': 'law', 'MST': hit['법령일련번호']})['법령']
        body.pop('개정문', None)
        body.pop('제개정이유', None)
        laws.append({'meta': hit, 'body': body})
    U.log(f'법령 {len(laws)}개')
    found = {}
    for q in QUERIES:
        page, total = 1, 1
        while (page - 1) * 100 < total:
            s = U.get('lawSearch.do', {'target': 'ordin', 'query': q, 'display': '100', 'page': str(page)})
            root = s.get('OrdinSearch', {})
            total = int(root.get('totalCnt') or 0)
            for x in as_list(root.get('law')):
                if x.get('자치법규종류') != '조례':
                    continue
                t = ordin_type(x.get('지자체기관명', ''), x.get('자치법규명', ''))
                if t:
                    found[x['자치법규ID']] = (t, x)
            page += 1
    U.log(f'조례 {len(found)}개 조회 시작')
    for i, (t, x) in enumerate(found.values(), 1):
        try:
            d = U.get('lawService.do', {'target': 'ordin', 'MST': x['자치법규일련번호']})
            body = d.get('LawService', d)
            body.pop('개정문', None)
            body.pop('제개정이유', None)
            ordin.append({'type': t, 'meta': x, 'body': body})
        except U.AuthError:
            raise
        except Exception as e:
            U.log('조례 실패:', x.get('자치법규명'), str(e)[:80])
        if i % 50 == 0:
            U.log(f'{i}/{len(found)}')
    return {'generated': datetime.now().strftime('%Y-%m-%d %H:%M'), 'laws': laws, 'ordin': ordin}


def flat(o, acc=None):
    acc = [] if acc is None else acc
    if isinstance(o, str):
        acc.append(o)
    elif isinstance(o, list):
        for v in o:
            flat(v, acc)
    return acc


def link(u):
    u = str(u or '').strip()
    if not u:
        return None
    if u.startswith('/'):
        return SITE + u
    return u.replace('http://', 'https://')


def ymd(s):
    s = str(s or '')
    return f'{s[:4]}.{int(s[4:6])}.{int(s[6:])}' if len(s) == 8 and s.isdigit() else s


def law_doc(item):
    meta, body = item['meta'], item['body']
    parts = []
    for h in as_list((body.get('조문') or {}).get('조문단위')):
        if str(h.get('조문여부')) == '전문':
            parts.append({'k': 'h', 't': U.clean(h.get('조문내용'))})
        else:
            parts.append({'k': 'a', 't': U.jo_title(h), 'x': U.clean('\n'.join(U.texts(h)))})
    for b in as_list((body.get('부칙') or {}).get('부칙단위')):
        lines = flat(b.get('부칙내용'))
        title = f"부칙 <제{str(b.get('부칙공포번호', '')).lstrip('0')}호, {ymd(b.get('부칙공포일자'))}>"
        parts.append({'k': 'b', 't': title, 'x': U.clean('\n'.join(lines))})
    for y in as_list((body.get('별표') or {}).get('별표단위')):
        no, g = U.to_i(y.get('별표번호')), U.to_i(y.get('별표가지번호'))
        kind = str(y.get('별표구분') or '별표')
        p = {'k': 'y', 't': f"{kind} {no}{'의' + str(g) if g else ''} {y.get('별표제목', '')}".strip()}
        if kind != '서식':
            p['x'] = U.clean('\n'.join(flat(y.get('별표내용'))))
        if link(y.get('별표서식PDF파일링크')):
            p['pdf'] = link(y.get('별표서식PDF파일링크'))
        if link(y.get('별표서식파일링크')):
            p['hwp'] = link(y.get('별표서식파일링크'))
        parts.append(p)
    name = meta['법령명한글']
    return {
        'name': name, 'kind': meta.get('법령구분명', ''), 'eff': str(meta.get('시행일자', '')),
        'prom': str(meta.get('공포일자', '')), 'url': SITE + '/법령/' + name.replace(' ', ''), 'parts': parts,
    }


def breaks(t):
    t = re.sub(r'\s*([①-⑳])', r'\n\1', t)
    t = re.sub(r'(?<=[가-힣\)\]>.」])\s*(?=\d{1,2}\. (?!\d))', '\n', t)
    t = re.sub(r'(?<=[가-힣\)\]>.」])\s+(?=[가-하]\. )', '\n', t)
    return t.strip()


def ordin_doc(item):
    meta, body = item['meta'], item['body']
    parts = []
    for h in as_list((body.get('조문') or {}).get('조')):
        text = U.clean(h.get('조내용'))
        if str(h.get('조문여부')) == 'N':
            parts.append({'k': 'h', 't': text})
            continue
        m = re.match(r'^(제\d+조(?:의\d+)?(?:\([^)]*\))?)', text)
        parts.append({'k': 'a', 't': m.group(1) if m else (h.get('조제목') or text[:20]), 'x': breaks(text)})
    bu = body.get('부칙') or {}
    texts, dates, nums = as_list(bu.get('부칙내용')), as_list(bu.get('부칙공포일자')), as_list(bu.get('부칙공포번호'))
    for i, t in enumerate(texts):
        d = dates[i] if i < len(dates) else ''
        n = nums[i] if i < len(nums) else ''
        parts.append({'k': 'b', 't': f"부칙 <제{str(n).lstrip('0')}호, {ymd(d)}>", 'x': U.clean('\n'.join(flat(t)))})
    ys = body.get('별표단위') or (body.get('별표') or {}).get('별표단위')
    for y in as_list(ys):
        no, g = U.to_i(y.get('별표번호')), U.to_i(y.get('별표가지번호'))
        kind = str(y.get('별표구분') or '별표')
        p = {'k': 'y', 't': f"{kind} {no}{'의' + str(g) if g else ''} {y.get('별표제목', '')}".strip()}
        x = U.clean('\n'.join(flat(y.get('별표내용'))))
        if x:
            p['x'] = x
        f = link(y.get('별표첨부파일명'))
        if f:
            p['pdf' if str(y.get('별표첨부파일구분', '')).lower() == 'pdf' else 'hwp'] = f
        parts.append(p)
    name = meta['자치법규명']
    return {
        'name': name, 'kind': TYPE_LABEL[item['type']], 'org': meta.get('지자체기관명', ''),
        'eff': str(meta.get('시행일자', '')), 'prom': str(meta.get('공포일자', '')),
        'url': SITE + '/자치법규/' + name.replace(' ', ''), 'parts': parts,
    }


def write(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(obj, f, ensure_ascii=False, separators=(',', ':'))


def build(bundle):
    old = {}
    idx_path = os.path.join(OUT, 'index.json')
    if os.path.exists(idx_path):
        with open(idx_path, encoding='utf-8') as f:
            old = json.load(f)
    tmp = OUT + '_tmp'
    shutil.rmtree(tmp, ignore_errors=True)
    index = {'laws': [], 'sido': {}}
    for it in bundle['laws']:
        doc = law_doc(it)
        file = f"law/{it['meta']['법령ID']}.json"
        write(os.path.join(tmp, file), doc)
        index['laws'].append({'name': doc['name'], 'kind': doc['kind'], 'eff': doc['eff'], 'file': file})
    order = {'건축': 0, '계획': 1, '주차': 2}
    for it in sorted(bundle['ordin'], key=lambda x: (x['meta'].get('지자체기관명', ''), order[x['type']])):
        doc = ordin_doc(it)
        file = f"ordin/{it['meta']['자치법규ID']}.json"
        write(os.path.join(tmp, file), doc)
        org = doc['org'].split()
        sido, sgg = org[0], ' '.join(org[1:])
        index['sido'].setdefault(sido, {}).setdefault(sgg, []).append(
            {'type': it['type'], 'name': doc['name'], 'eff': doc['eff'], 'file': file})
    index['sido'] = {k: dict(sorted(v.items())) for k, v in sorted(index['sido'].items())}
    same = {k: old.get(k) for k in ('laws', 'sido')} == index
    index['generated'] = old.get('generated') if same and old.get('generated') else bundle['generated']
    write(os.path.join(tmp, 'index.json'), index)
    shutil.rmtree(OUT, ignore_errors=True)
    os.rename(tmp, OUT)
    n = sum(len(v) for s in index['sido'].values() for v in s.values())
    U.log(f"lawdb: 법령 {len(index['laws'])}개, 조례 {n}개, 변경 {'없음' if same else '있음'}")
    return not same


def main():
    args = [a for a in sys.argv[1:] if not a.startswith('--')]
    push = '--push' in sys.argv
    if args:
        opener = gzip.open if args[0].endswith('.gz') else open
        with opener(args[0], 'rt', encoding='utf-8') as f:
            bundle = json.load(f)
        if 'T' in bundle.get('generated', ''):
            bundle['generated'] = datetime.now().strftime('%Y-%m-%d %H:%M')
    else:
        U.OC = U.load_oc()
        if push:
            U.git('pull', '--rebase', '--autostash')
        try:
            bundle = fetch_bundle()
        except U.AuthError as e:
            sys.exit(f'인증 실패: {e}')
    changed = build(bundle)
    if push and changed:
        U.git('add', 'lawdb')
        r = U.git('commit', '-m', f"법령·조례 데이터 갱신 {bundle['generated']}")
        U.log(r.stdout.strip()[:200] or r.stderr.strip()[:200])
        r = U.git('push')
        U.log('push 완료' if r.returncode == 0 else 'push 실패: ' + r.stderr.strip())


if __name__ == '__main__':
    main()
