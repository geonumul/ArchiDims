import json
import os
import re
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import update_snapshot as U

LAWDB = os.path.join(U.ROOT, 'lawdb')


def forms(d):
    out = []
    for k in ('min', 'rec', 'max'):
        v = d.get(k)
        for x in (v if isinstance(v, list) else [v]):
            if isinstance(x, (int, float)) and d.get('u', 'mm') == 'mm':
                g = lambda n: ('%g' % n)
                out += [g(x / 10) + '센티미터', g(x / 1000) + '미터', g(x) + '밀리미터', g(x / 10) + ' 이', g(x / 1000) + ' 이', g(x / 1000) + ' ']
            elif isinstance(x, (int, float)):
                out.append('%g' % x)
                if x >= 1000 and x % 100 == 0:
                    out.append(('%d천' % (x // 1000)) + (('%d' % (x % 1000)) if x % 1000 else ''))
            elif isinstance(x, str):
                m = re.search(r'1/(\d+)', x)
                if m:
                    out += ['1:' + m.group(1), '1 : ' + m.group(1), m.group(1) + '분의 1']
    return out


def main():
    with open(U.DATA, encoding='utf-8') as f:
        data = json.load(f)
    with open(os.path.join(LAWDB, 'index.json'), encoding='utf-8') as f:
        index = json.load(f)
    old = {}
    if os.path.exists(U.OUT):
        with open(U.OUT, encoding='utf-8') as f:
            old = json.load(f)
    docs = {}
    for l in index['laws']:
        with open(os.path.join(LAWDB, l['file']), encoding='utf-8') as f:
            docs[U.norm(l['name'])] = json.load(f)
    snap = {'version': 2, 'dataDate': U.DATA_DATE, 'laws': {}, 'items': {}, 'arts': {}}
    idx, miss, kept = {}, [], 0
    for d in data:
        src = d.get('src')
        if not src or not U.LAW_RE.search(src):
            continue
        key = d['c'] + '|' + d['n']
        info = U.parse_src(src)
        doc = docs.get(U.norm(info['name']))
        if not doc:
            o = (old.get('items') or {}).get(key)
            if o:
                if not o.get('admrul'):
                    o = dict(o, items=[(old.get('arts') or {}).get(i, i) if isinstance(i, str) else i for i in o.get('items', [])])
                snap['items'][key] = o
                kept += 1
            continue
        arts = [p for p in doc['parts'] if p['k'] == 'a']
        if info.get('byul'):
            b = info['byul']
            pat = re.compile(r'^별표 %d%s ' % (b[0], '의%d' % b[1] if b[1] else ''))
            items = [p for p in doc['parts'] if p['k'] == 'y' and pat.match(p['t'] + ' ')][:1]
        elif info.get('jo'):
            j = info['jo']
            head = '제%d조%s' % (j[0], '의%d' % j[1] if j[1] else '')
            items = [p for p in arts if p['t'].split('(')[0] == head][:1]
        else:
            hs = list(dict.fromkeys(U.hints_of(d)))
            sc = sorted(((sum((5 if w in p['t'] else 0) + (1 if w in p['x'] else 0) for w in hs), i) for i, p in enumerate(arts)), reverse=True)
            items = [arts[i] for s, i in sc[:2] if s > 0]
        seg = ['법령', doc['name'].replace(' ', '')]
        if info.get('jo'):
            seg.append(head)
        res = {'ok': True, 'law': doc['name'], 'eff': doc['eff'], 'prom': doc['prom'],
               'url': 'https://www.law.go.kr/' + '/'.join(U.urllib.parse.quote(x) for x in seg), 'changed': doc['eff'] > U.DATA_DATE}
        if not items:
            res['error'] = '해당 조문을 찾지 못했습니다. 법령 사이트에서 확인하세요.'
            miss.append(key + ' :: 조문 없음 ' + src)
        ids = []
        for p in items:
            k = doc['name'] + '|' + p['t']
            if k not in idx:
                idx[k] = 'a' + str(len(idx))
                snap['arts'][idx[k]] = {'title': p['t'], 'text': p.get('x', '')}
            ids.append(idx[k])
        res['items'] = ids
        snap['items'][key] = res
        snap['laws'][U.norm(doc['name'])] = {'name': doc['name'], 'eff': doc['eff'], 'changed': doc['eff'] > U.DATA_DATE}
        text = '\n'.join(p.get('x', '') for p in items).replace(',', '')
        text = text.replace('천', '000') if False else text
        f = forms(d)
        if items and f and not any(x in text for x in f):
            miss.append(key + ' :: 수치 불일치 ' + str([d.get(k) for k in ('min', 'rec', 'max') if d.get(k) is not None]))
    a = {k: v for k, v in old.items() if k != 'generated'}
    if a == snap:
        U.log('스냅샷 변경 없음')
    else:
        snap['generated'] = index.get('generated') or datetime.now().strftime('%Y-%m-%d %H:%M')
        with open(U.OUT, 'w', encoding='utf-8') as f:
            json.dump(snap, f, ensure_ascii=False, separators=(',', ':'))
        U.log(f"스냅샷 저장: 항목 {len(snap['items'])}개 (기존 유지 {kept}개), 조문 {len(snap['arts'])}개")
    for m in miss:
        U.log('확인 필요:', m)


if __name__ == '__main__':
    main()
