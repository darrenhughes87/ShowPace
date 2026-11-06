"""Run with: python3 test_server.py  (uses a temporary data folder, never touches your shows)"""
import json, os, tempfile, threading, urllib.request, urllib.error

os.environ['SHOWPACE_DATA'] = tempfile.mkdtemp()
os.environ['SHOWPACE_PROXY'] = '1'  # so the tests can play different addresses
import server

server.load()
srv = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
srv.daemon_threads = True
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f'http://127.0.0.1:{srv.server_address[1]}'


def call(path, method='GET', data=None, cookie='', ctype='application/json', ip='127.0.0.1'):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(base + path, method=method, data=body, headers={'Cookie': cookie, 'Content-Type': ctype, 'X-Forwarded-For': ip})
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            return r.status, r.headers, json.loads(raw) if raw and 'json' in r.headers.get('Content-Type', '') else raw
    except urllib.error.HTTPError as e:
        return e.code, e.headers, None


# First run: nobody yet, so the page asks for the admin login. It only works once.
assert call('/api/shows')[0] == 401, 'shows need a login'
assert call('/api/me')[0] == 401
assert call('/api/setup', 'POST', {'user': 'Sam', 'pass': 'short'})[0] == 400, 'passwords need 10 characters'
assert call('/api/setup', 'POST', {'user': 'x', 'pass': 'correct horse battery'})[0] == 400, 'usernames need 2 characters'
st, h, me = call('/api/setup', 'POST', {'user': 'Sam', 'pass': 'correct horse battery'})
assert st == 200 and me == {'user': 'sam', 'admin': True} and 'HttpOnly' in h['Set-Cookie']
assert call('/api/setup', 'POST', {'user': 'eve', 'pass': 'correct horse battery'})[0] == 409, 'setup only works once'
assert call('/api/login', 'POST', {'user': 'sam', 'pass': 'wrong'})[0] == 401, 'wrong password refused'
st, h, _ = call('/api/login', 'POST', {'user': 'Sam', 'pass': 'correct horse battery'})
assert st == 200 and 'HttpOnly' in h['Set-Cookie']
cookie = h['Set-Cookie'].split(';')[0]
assert call('/api/me', cookie=cookie)[2] == {'user': 'sam', 'admin': True}

# Admin: add people, and only admins can
assert call('/api/users', 'POST', {'user': 'jo', 'pass': 'another good one', 'admin': False}, cookie)[0] == 200
assert call('/api/users', 'POST', {'user': 'Bad Name!', 'pass': 'another good one'}, cookie)[0] == 400
assert call('/api/users', cookie=cookie)[2] == [{'name': 'jo', 'admin': False}, {'name': 'sam', 'admin': True}]
jo = call('/api/login', 'POST', {'user': 'jo', 'pass': 'another good one'})[1]['Set-Cookie'].split(';')[0]
assert call('/api/me', cookie=jo)[2] == {'user': 'jo', 'admin': False}
assert call('/api/users', cookie=jo)[0] == 403 and call('/api/settings', cookie=jo)[0] == 403, 'not an admin'
assert call('/api/users', 'POST', {'user': 'jo', 'pass': 'x' * 12, 'admin': True}, jo)[0] == 403
assert call('/api/users', 'POST', {'user': 'sam', 'pass': '', 'admin': False}, cookie)[0] == 400, 'keep at least one admin'
assert call('/api/users/sam', 'DELETE', cookie=cookie)[0] == 400, "can't remove yourself"
assert call('/api/users', 'POST', {'user': 'jo', 'pass': 'a brand new one'}, cookie)[0] == 200
assert call('/api/me', cookie=jo)[0] == 401, 'a new password logs them out'
assert call('/api/users/jo', 'DELETE', cookie=cookie)[0] == 200 and call('/api/login', 'POST', {'user': 'jo', 'pass': 'a brand new one'})[0] == 401

# Settings: name, colours and how long logins last. Bad values are refused.
assert call('/api/brand')[2] == {'name': 'ShowPace', 'org': '', 'brand': '#1F8F4E', 'brand2': '#3A9C63', 'brand3': '#62B183', 'bg': '#101211', 'onBrand': '#ffffff'}
assert call('/api/settings', 'PUT', {'bg': 'red; } body { display:none'}, cookie)[0] == 400
assert call('/api/settings', 'PUT', {'bg': '#FFFFFF'}, cookie)[0] == 400, 'dark backgrounds only'
st, _, b = call('/api/settings', 'PUT', {'name': '  Cue  Desk ', 'org': 'Acme Audio', 'brand': '#f2c14e', 'sessionDays': 7}, cookie)
assert st == 200 and b['name'] == 'Cue Desk' and b['brand'] == '#F2C14E' and b['onBrand'] == '#111111', 'dark text on a pale colour'
assert call('/api/settings', cookie=cookie)[2]['sessionDays'] == 7
assert b'>C</text>' in call('/favicon.svg')[2] and b'#F2C14E' in call('/favicon.svg')[2]
assert call('/api/settings', 'PUT', {'name': '', 'brand': '#1F8F4E', 'org': '', 'sessionDays': 30}, cookie)[2]['name'] == 'ShowPace', 'an empty name goes back to ShowPace'

st, _, show = call('/api/shows', 'POST', {'title': 'Test', 'items': [{'id': 'a', 'dur': 60}]}, cookie)
assert st == 201 and show['viewToken'] and show['id']
assert call('/api/shows', 'POST', {'title': 'x'}, cookie)[0] == 400, 'rejects junk'
assert call('/api/shows', 'POST', {'title': 'x', 'items': []}, cookie, ctype='text/plain')[0] == 400, 'needs JSON'

show['title'] = 'Changed'; show['viewToken'] = 'hijack'
assert call(f'/api/shows/{show["id"]}', 'PUT', show, cookie)[0] == 200
st, _, crew = call(f'/api/view/{call("/api/shows", cookie=cookie)[2][0]["viewToken"]}')
assert st == 200 and crew['title'] == 'Changed' and crew['viewToken'] != 'hijack', 'crew link works, token not changeable'
assert call(f'/api/shows/{show["id"]}', 'PUT', show)[0] == 401, 'crew cannot edit'
assert call('/api/view/not-a-real-token')[0] == 404
for secret in ('/data/users.json', '/server.py', '/data/sessions.json'):
    assert call(secret)[0] in (401, 404) and call(secret, cookie=cookie)[0] == 404, secret
assert call('/')[0] == 200 and call('/v/anything')[0] == 200, 'app served'
# /crew: only shows pushed live; straight in unless pushed with a password
st, _, gig = call('/api/shows', 'POST', {'title': 'Tonight', 'items': []}, cookie)
assert call('/api/crew')[2] == [], 'nothing on the crew page until pushed live'
assert call(f'/api/crew/{gig["id"]}', 'POST', {'pass': ''})[0] == 403, 'cannot open a show that is not pushed live'
assert call(f'/api/shows/{gig["id"]}/crew', 'POST', {'on': True, 'pass': ''})[0] == 401, 'only staff push live'
assert call(f'/api/shows/{gig["id"]}/crew', 'POST', {'on': True, 'pass': ''}, cookie)[2] == {'onCrew': True, 'crewLocked': False}
assert call('/api/crew')[2][0]['token'] == gig['viewToken'], 'empty password: straight in'
call(f'/api/shows/{gig["id"]}/crew', 'POST', {'on': True, 'pass': 'stage door'}, cookie)
locked = call('/api/crew')[2][0]
assert locked['locked'] and 'token' not in locked, 'a locked show hides its link'
assert call(f'/api/crew/{gig["id"]}', 'POST', {'pass': 'wrong'})[0] == 403
assert call(f'/api/crew/{gig["id"]}', 'POST', {'pass': 'stage door'})[2]['token'] == gig['viewToken']
gig2 = call(f'/api/shows/{gig["id"]}', cookie=cookie)[2]
assert 'stage door' not in json.dumps(gig2) and 'hash' not in json.dumps(gig2), 'password never sent with the show'
gig2['crewLocked'] = False; gig2['onCrew'] = False
call(f'/api/shows/{gig["id"]}', 'PUT', gig2, cookie)
assert call('/api/crew')[2][0]['locked'], 'saving the show cannot change its crew page settings'
assert call(f'/api/shows/{gig["id"]}/crew', 'POST', {'on': False}, cookie)[2] == {'onCrew': False, 'crewLocked': False}
assert call('/api/crew')[2] == [], 'take down removes it'
assert call('/data/crewpass.json', cookie=cookie)[0] == 404
assert call('/crew')[0] == 200 and 'noindex' in call('/crew')[1]['X-Robots-Tag']

# Bad or crafted show data is rebuilt from known fields only
st, _, bad = call('/api/shows', 'POST', {'title': 'X', 'evil': 1, 'items': [
    {'id': 'x"><script>', 'kind': '"><img src=x onerror=alert(1)>', 'dur': 'lots', 'title': 5},
    'not a row', {'id': 'ok_1', 'type': 'header', 'title': 'Section'}]}, cookie)
assert st == 201 and 'evil' not in bad and len(bad['items']) == 2, 'unknown fields and junk rows dropped'
assert bad['items'][0]['id'] != 'x"><script>' and bad['items'][0]['dur'] == 0 and bad['items'][0]['title'] == '5'
assert bad['items'][1] == {'id': 'ok_1', 'type': 'header', **{k: (('Section') if k == 'title' else '') for k in server.TEXT}, 'dur': 0}

# Every page carries a security policy
assert "default-src 'self'" in call('/')[1]['Content-Security-Policy']

assert call('/data/settings.json')[0] in (401, 404) and call('/data/../server.py')[0] in (401, 404)

# Lockout after repeated wrong passwords, per address
server.MAX_FAILS = 3
for _ in range(3):
    assert call('/api/login', 'POST', {'user': 'sam', 'pass': 'nope'}, ip='9.9.9.9')[0] == 401
assert call('/api/login', 'POST', {'user': 'sam', 'pass': 'correct horse battery'}, ip='9.9.9.9')[0] == 429, 'locked out'
assert call('/api/login', 'POST', {'user': 'sam', 'pass': 'correct horse battery'}, ip='8.8.8.8')[0] == 200, 'others unaffected'
assert call('/api/crew/nope', 'POST', {'pass': 'x'}, ip='9.9.9.9')[0] == 403, 'crew typos are counted apart from logins'
assert call('/api/login', 'POST', {'user': 'sam', 'pass': 'x'}, ip='1.1.1.1, 9.9.9.9')[0] == 429, 'the address Caddy adds is the one counted'
assert call('/server.py', 'HEAD')[0] == 405
import time
assert abs(call('/api/time')[2]['t'] - time.time() * 1000) < 2000, 'the server tells screens the time'
assert server.length('0:10') == 600 and server.length('5:30') == 330 and server.length('10') == 600, 'a CSV 0:10 is ten minutes, as in Excel'
open(os.path.join(server.DATA, 'sessions.json'), 'w').close()
assert call('/api/me', cookie=cookie)[0] == 401, 'an empty sessions file logs people out instead of breaking'
cookie = call('/api/login', 'POST', {'user': 'sam', 'pass': 'correct horse battery'}, ip='8.8.8.8')[1]['Set-Cookie'].split(';')[0]

# Uploading a running order: the template itself, a client's own headings, Excel, and files ShowPace can't read
import base64, io, zipfile
up = lambda name, raw: call('/api/import', 'POST', {'name': name, 'data': base64.b64encode(raw).decode()}, cookie)
assert call('/template.csv')[0] == 200
st, _, t = up('Template.csv', open(os.path.join(server.DIR, 'template.csv'), 'rb').read())
segs = [i for i in t['items'] if i.get('type') != 'header']
assert st == 201 and t['title'] == 'Template' and t['start'] == '09:00' and t['items'][1]['type'] == 'header'
assert [i['dur'] // 60 for i in segs] == [60, 10, 30, 15, 0, 20], 'end minus start, minutes, minutes, end minus start'
assert segs[4]['kind'] == 'free' and segs[4]['until'] == '11:30', 'free time runs until its End'
assert segs[2]['kind'] == 'panel' and segs[2]['audio'] == 'HH1; HH2' and 'Alex Reid, Northfield Labs' in segs[2]['who'], 'speaker rows join the panel'
client = 'Session;Time on;Time off;Speaker;Organisation;Mic\nWelcome;10:00;10:10;Sam Jones;Riverside Council;LEC\nKeynote;10:10;;Alex;Northfield Labs;LEC\nLunch;11:00;12:00;;;\n'
st, _, c = up('Client.csv', client.encode())
assert st == 201 and [i['dur'] // 60 for i in c['items']] == [10, 50, 60] and c['items'][0]['who'] == 'Sam Jones, Riverside Council', \
    "a client's own headings, semicolons, and the gap to the next start"


def xlsx(rows):
    cells = lambda r, n: ''.join(f'<c r="{chr(65 + i)}{n}"' + (f'><v>{v}</v></c>' if isinstance(v, float) else f' t="inlineStr"><is><t>{v}</t></is></c>')
                                 for i, v in enumerate(r) if v != '')
    sheet = ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + ''.join(f'<row r="{n}">{cells(r, n)}</row>' for n, r in enumerate(rows, 1)) + '</sheetData></worksheet>')
    b = io.BytesIO()
    with zipfile.ZipFile(b, 'w') as z:
        z.writestr('xl/worksheets/sheet1.xml', sheet)
    return b.getvalue()


st, _, x = up('Gig.xlsx', xlsx([['Running order: Gig'], ['Start', 'Mins', 'Session', 'Speaker'], [0.375, 60.0, 'Doors', ''], [0.4166666667, 10.0, 'Welcome', 'Sam'], ['', '', '', 'Alex']]))
assert st == 201 and x['start'] == '09:00' and [i['dur'] // 60 for i in x['items']] == [60, 10] and x['items'][1]['who'] == 'Sam; Alex', \
    'Excel times, and a title row above the headings'
assert up('Gig.numbers', b'x')[0] == 400 and up('Rubbish.csv', b'no headings here\n1,2,3')[0] == 400

# Caller remote: its own password; the phone sends the live state; a new password locks old phones out
tok, sid_ = t['viewToken'], t['id']
assert call(f'/api/shows/{sid_}/remote', 'POST', {'pass': 'on stage'})[0] == 401, 'staff set it'
assert call(f'/api/shows/{sid_}/remote', 'POST', {'pass': 'on stage'}, cookie)[2] == {'remoteOn': True}
assert call(f'/api/remote/{tok}', 'POST', {'pass': 'wrong'}, ip='5.5.5.5')[0] == 403
key = call(f'/api/remote/{tok}', 'POST', {'pass': 'on stage'}, ip='5.5.5.5')[2]['key']
live = lambda: call(f'/api/view/{tok}')[2]['live']
press = lambda l, k=None: call(f'/api/remote/{tok}/act', 'POST', {'key': k or key, 'live': l})[0]
first = [i['id'] for i in t['items'] if i.get('type') != 'header'][0]
assert press({'id': first, 'at': 1000, 'log': [], 'nudge': 60000}) == 200 and live()['id'] == first and live()['nudge'] == 60000
assert call(f'/api/remote/{tok}/act', 'POST', {'key': key, 'live': {'id': None, 'log': 'junk'}, 'items': []})[0] == 200
assert live()['log'] == [] and len(call(f'/api/view/{tok}')[2]['items']) == len(t['items']), 'the remote can only change the live state'
assert press({'id': first}, 'not-the-key') == 403
assert press({'id': first, 'at': '<b>', 'log': [None, 5, {'id': first, 'start': 1, 'end': 2, 'nudge': 60}], 'junk': 1}) == 200
assert live() == {'id': first, 'at': None, 'nudge': 0, 'travel': 0, 'tt': None, 'hold': None, 'msg': None, 'log': [{'id': first, 'start': 1, 'end': 2, 'nudge': 60, 'travel': 0, 'tt': None}]}, 'only known live fields get through'
assert press({'id': first, 'hold': {'at': 5000, 'dur': 600}}) == 200 and live()['hold'] == {'at': 5000, 'dur': 600}
assert press({'id': first, 'hold': {'at': 'x', 'dur': 600}}) == 200 and live()['hold'] is None, 'a broken hold is dropped'
assert press({'id': first, 'msg': {'text': '  Wrap   up ' + 'x' * 100, 'at': 7000}}) == 200 and live()['msg'] == {'text': 'Wrap up ' + 'x' * 72, 'at': 7000}
assert press({'id': first, 'msg': {'text': '   ', 'at': 7000}}) == 200 and live()['msg'] is None, 'an empty message is dropped'
assert press({'id': first, 'msg': {'text': 5, 'at': 1}}) == 200 and live()['msg'] is None
assert press({'id': 'END'}) == 200 and live()['id'] == 'END'
assert call(f'/api/remote/{tok}/act', 'POST', {'key': 'ünïcode', 'live': {}})[0] == 403
shown = call(f'/api/shows/{sid_}', cookie=cookie)[2]
assert shown['src'] == 'remote' and 'key' not in json.dumps(shown) and 'on stage' not in json.dumps(shown), 'the key never travels with the show'
shown['remoteOn'] = False
call(f'/api/shows/{sid_}', 'PUT', shown, cookie)
assert call(f'/api/shows/{sid_}', cookie=cookie)[2]['remoteOn'], 'saving the show cannot switch the remote off'
call(f'/api/shows/{sid_}/remote', 'POST', {'pass': 'new one'}, cookie)
assert press({'id': first}) == 403, 'a new password locks out phones using the old one'
assert call('/r/anything')[0] == 200

# Deleting: only archived shows, only staff, and the file is kept in data/deleted
gone = x['id']
assert call(f'/api/shows/{gone}', 'DELETE')[0] == 401, 'staff only'
assert call(f'/api/shows/{gone}', 'DELETE', cookie=cookie)[0] == 409, 'archive first'
x['archived'] = True
call(f'/api/shows/{gone}', 'PUT', x, cookie)
assert call(f'/api/shows/{gone}', 'DELETE', cookie=cookie)[0] == 200
assert call(f'/api/shows/{gone}', cookie=cookie)[0] == 404 and gone not in [s['id'] for s in call('/api/shows', cookie=cookie)[2]]
assert any(f.startswith(gone) for f in os.listdir(os.path.join(server.DATA, 'deleted'))), 'kept for undo'

# Removing a login from the command line logs that person out everywhere
server.set_user('sam', remove=True)
assert call('/api/me', cookie=cookie)[0] == 401, 'logged out everywhere'
assert call('/api/login', 'POST', {'user': 'sam', 'pass': 'correct horse battery'}, ip='7.7.7.7')[0] == 401, 'login gone'

call('/api/logout', 'POST', {}, cookie)
assert call('/api/shows', cookie=cookie)[0] == 401, 'logged out'
print('server test passed')
