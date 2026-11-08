#!/usr/bin/env python3
"""ShowPace server. Python standard library only, so there is nothing to install.

Keeps every show, keeps each one in sync across devices (server-sent events), and keeps it private:
people with a login edit and call shows; crew get a view-only link per show (/v/<token>).

  python3 server.py                 run it (port 4320, data in ./data)
  python3 server.py --port 4321     run it on another port
  python3 server.py adduser NAME    add an admin login, or reset a password, from the command line
  python3 server.py deluser NAME    remove a login

The first time you open it in a browser, it asks you to create the admin login.
"""
import sys

if sys.version_info < (3, 8):
    sys.exit('ShowPace needs Python 3.8 or newer. You have %d.%d. Get a newer one from https://www.python.org/downloads/' % sys.version_info[:2])
import base64, csv, datetime, functools, getpass, hashlib, hmac, html, io, json, os, re, secrets, socket, threading, time, zipfile
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

DIR = os.path.dirname(os.path.abspath(__file__))
DATA = os.environ.get('SHOWPACE_DATA', os.path.join(DIR, 'data'))
SHOWS = os.path.join(DATA, 'shows')
PORT = int(os.environ.get('SHOWPACE_PORT', 4320))
SECURE = os.environ.get('SHOWPACE_SECURE') == '1'  # set behind HTTPS so the login cookie is Secure
PROXY = os.environ.get('SHOWPACE_PROXY') == '1'    # set behind a proxy (Caddy) that adds the real address to X-Forwarded-For
STATIC = {'/index.html', '/template.csv', '/qrcode.min.js'}
ID = re.compile(r'^[A-Za-z0-9_-]{6,40}$')
ITEM_ID = re.compile(r'^[A-Za-z0-9_-]{1,40}$')
NAME = re.compile(r'^[a-z0-9._-]{2,32}$')
MIN_PASS = 10
TEXT = ('cue', 'title', 'who', 'kind', 'audio', 'lx', 'vid', 'notes', 'until')
MAX_FAILS, FAIL_WINDOW = 10, 900   # wrong passwords per address per 15 minutes, then locked out
COOKIE = 'showpace'
MAX_VIEWERS = 300                    # live connections per show
CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
       "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
DEFAULTS = {'name': 'ShowPace', 'org': '', 'brand': '#1F8F4E', 'bg': '#101211', 'sessionDays': 30}
COLOUR = re.compile(r'^#[0-9a-fA-F]{6}$')

lock = threading.Condition()
shows = {}       # id -> show dict
version = {}     # id -> int, bumped on every change
viewers = {}     # id -> number of open event streams


def read_json(path, default):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):  # missing, empty or half-written: carry on without it
        return default


def write_json(path, data):
    tmp = '%s.%d.tmp' % (path, threading.get_ident())
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, separators=(',', ':'))
    for _ in range(20):
        try:
            return os.replace(tmp, path)
        except PermissionError:  # Windows: another request is reading the file this instant
            time.sleep(0.05)
    os.replace(tmp, path)


def hash_pw(pw, salt):
    return hashlib.pbkdf2_hmac('sha256', pw.encode(), bytes.fromhex(salt), 200_000).hex()


def luminance(c):
    r, g, b = (int(c[i:i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def lighter(c, f):
    return '#' + ''.join('%02X' % round(int(c[i:i + 2], 16) + (255 - int(c[i:i + 2], 16)) * f) for i in (1, 3, 5))


def settings():
    """The app's settings from data/settings.json, set on the Admin page. Anything missing or malformed falls back."""
    saved = read_json(os.path.join(DATA, 'settings.json'), {})
    try:
        return clean_settings(saved, DEFAULTS)
    except ValueError:
        return dict(DEFAULTS)


def clean_settings(body, old):
    """Only known, well-formed values, so the settings can't inject CSS or break the screens."""
    if not isinstance(body, dict):
        raise ValueError('Not settings')
    s = dict(old)
    for k in ('name', 'org'):
        if k in body:
            s[k] = ' '.join(str(body[k]).split())[:40 if k == 'name' else 80]
    s['name'] = s['name'] or DEFAULTS['name']
    for k in ('brand', 'bg'):
        if k in body:
            if not COLOUR.match(str(body[k])):
                raise ValueError('Colours look like #1F8F4E')
            s[k] = str(body[k]).upper()
    if luminance(s['bg']) > 0.2:
        raise ValueError('Pick a dark background. The screens are made for dark rooms and light text.')
    if 'sessionDays' in body:
        try:
            s['sessionDays'] = max(1, min(int(body['sessionDays']), 365))
        except (TypeError, ValueError):
            raise ValueError('Stay logged in is a number of days')
    return s


def look():
    """What every page needs to draw itself: name, organisation and colours, with lighter shades worked out here."""
    s = settings()
    return {'name': s['name'], 'org': s['org'], 'brand': s['brand'], 'brand2': lighter(s['brand'], .12),
            'brand3': lighter(s['brand'], .3), 'bg': s['bg'],
            'onBrand': '#111111' if luminance(s['brand']) > 0.6 else '#ffffff'}  # dark text on a pale colour


def favicon():
    b = look()
    letter = html.escape((b['name'].strip()[:1] or 'S').upper())
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32"><rect width="32" height="32" rx="7" fill="%s"/>'
            '<path d="M22 0h3a7 7 0 0 1 7 7v18a7 7 0 0 1-7 7H11z" fill="%s"/><text x="16" y="24.5" text-anchor="middle" '
            'font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="21" fill="%s">%s</text></svg>' % (b['brand'], b['brand2'], b['onBrand'], letter)).encode()


def load():
    os.makedirs(SHOWS, exist_ok=True)
    for name in os.listdir(SHOWS):
        if name.endswith('.json'):
            s = read_json(os.path.join(SHOWS, name), None)
            if s and ID.match(s.get('id', '')):
                shows[s['id']] = s
                version[s['id']] = 1


def save_show(s):
    write_json(os.path.join(SHOWS, s['id'] + '.json'), s)


def users():
    return read_json(os.path.join(DATA, 'users.json'), {})


def add_user(name, pw, admin):
    """Add a login, or change one. An empty password keeps the old one. Returns an error message, or None."""
    name = str(name).lower().strip()
    if not NAME.match(name):
        return 'Usernames are 2 to 32 letters or numbers (dots, dashes and underscores are fine too)'
    with lock:
        us = users()
        old = us.get(name)
        if pw:
            if len(pw) < MIN_PASS:
                return 'Use a password of at least %d characters' % MIN_PASS
            salt = secrets.token_hex(16)
            us[name] = {'salt': salt, 'hash': hash_pw(pw, salt), 'admin': bool(admin)}
        elif old:
            us[name] = dict(old, admin=bool(admin))
        else:
            return 'A new login needs a password'
        if not any(u.get('admin') for u in us.values()):
            return 'Keep at least one admin'
        write_json(os.path.join(DATA, 'users.json'), us)
    return None


def log_out(name, keep=None):
    """End every session for this login, apart from the one making the change."""
    path = os.path.join(DATA, 'sessions.json')
    with lock:
        write_json(path, {k: v for k, v in read_json(path, {}).items() if v['user'] != name or k == keep})


def summary(s):
    items = [i for i in s.get('items', []) if i.get('type') != 'header']
    return {'id': s['id'], 'title': s.get('title', ''), 'date': s.get('date', ''), 'start': s.get('start', ''),
            'archived': bool(s.get('archived')), 'segments': len(items), 'runtime': sum(i.get('dur', 0) for i in items),
            'live': s.get('live', {}).get('id') not in (None, 'END'), 'viewToken': s.get('viewToken'),
            'onCrew': bool(s.get('onCrew')), 'crewLocked': bool(s.get('crewLocked'))}


def clean(body, old):
    """Accept a show from a client: rebuild it from known fields only, so a bad or crafted file can't break it
    or smuggle code onto crew screens. The server keeps the fields only it may set."""
    if not isinstance(body, dict) or not isinstance(body.get('items'), list):
        raise ValueError
    items = []
    for it in body['items'][:2000]:
        if not isinstance(it, dict):
            continue
        x = {'id': it['id'] if isinstance(it.get('id'), str) and ITEM_ID.match(it['id']) else secrets.token_hex(4)}
        if it.get('type') == 'header':
            x['type'] = 'header'
        for k in TEXT:
            x[k] = str(it.get(k) or '')[:2000]
        try:
            x['dur'] = max(0, min(int(float(it.get('dur') or 0)), 86400))
        except (TypeError, ValueError):
            x['dur'] = 0
        items.append(x)
    live = clean_live(body.get('live'))
    return {'id': old['id'], 'viewToken': old['viewToken'],
            'title': str(body.get('title') or '')[:300], 'date': str(body.get('date') or '')[:10],
            'start': str(body.get('start') or '')[:5], 'archived': bool(body.get('archived')), 'items': items,
            'live': live,
            # only the Push live and Caller remote routes change these
            'onCrew': bool(old.get('onCrew')), 'crewLocked': bool(old.get('crewLocked')), 'remoteOn': bool(old.get('remoteOn'))}


def clean_live(l):
    """Where the show is: the live segment, when it started, its ±1m and time travel, and the segments done."""
    l = l if isinstance(l, dict) else {}
    num = lambda v: v if isinstance(v, (int, float)) and not isinstance(v, bool) and abs(v) < 1e14 else None
    seg = lambda v: v if v in (None, 'END') or (isinstance(v, str) and ITEM_ID.match(v)) else None  # an item id, or 'END'
    tt = lambda v: {'d0': num(v['d0']), 'r0': num(v['r0'])} if isinstance(v, dict) and num(v.get('d0')) is not None and num(v.get('r0')) is not None else None
    bend = lambda e: {'nudge': num(e.get('nudge')) or 0, 'travel': num(e.get('travel')) or 0, 'tt': tt(e.get('tt'))}
    log = [{'id': e['id'], 'start': num(e.get('start')), 'end': num(e.get('end')), **bend(e)}
           for e in l.get('log') if isinstance(e, dict) and seg(e.get('id'))][:2000] if isinstance(l.get('log'), list) else []
    h = l.get('hold')  # the hold timer: {at, dur in seconds}, off the schedule
    hold = {'at': num(h.get('at')), 'dur': num(h.get('dur'))} if isinstance(h, dict) and num(h.get('at')) and num(h.get('dur')) else None
    m = l.get('msg')  # a message on the speaker's clock: {text, at}; at changes to flash it again
    msg = {'text': ' '.join(m['text'].split())[:80], 'at': num(m.get('at'))} if isinstance(m, dict) and isinstance(m.get('text'), str) and m['text'].strip() and num(m.get('at')) else None
    return {'id': seg(l.get('id')), 'at': num(l.get('at')), **bend(l), 'hold': hold, 'msg': msg, 'log': log}


# ---- Importing a running order from CSV or Excel
# Template column -> the headings people actually use, so a client's sheet can be pasted in as it is.
HEADINGS = {
    'cue': ('cue', 'q', 'cue number', 'queue', 'queue number', '#'),
    'start': ('start', 'time on', 'on', 'start time', 'time', 'from'),
    'end': ('end', 'time off', 'off', 'end time', 'finish', 'to'),
    'dur': ('duration', 'dur', 'mins', 'minutes', 'length'),
    'title': ('segment', 'session', 'item', 'title', 'description'),
    'kind': ('type', 'kind'),
    'who': ('who', 'speaker', 'speakers', 'presenter', 'talent'),
    'org': ('organisation', 'organization', 'company'),
    'audio': ('audio', 'sound', 'mic', 'mics'),
    'lx': ('lighting', 'lx', 'lights'),
    'vid': ('video', 'vid', 'screens', 'vt', 'av'),
    'notes': ('notes', 'note', 'comments'),
}
KINDS = {'talk': 'talk', 'panel': 'panel', 'break': 'break', 'free': 'free', 'video': 'video', 'vt': 'video', 'music': 'music', 'other': 'other'}


def xlsx_rows(raw):
    """First sheet of an .xlsx as rows of cells. Text stays text; numbers (including Excel times) stay floats."""
    z, ns = zipfile.ZipFile(io.BytesIO(raw)), '{http://schemas.openxmlformats.org/spreadsheetml/2006/main}'
    shared = [''.join(t.text or '' for t in si.iter(ns + 't')) for si in ET.fromstring(z.read('xl/sharedStrings.xml')).iter(ns + 'si')] \
        if 'xl/sharedStrings.xml' in z.namelist() else []
    sheet = min((n for n in z.namelist() if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', n)), key=lambda n: int(re.sub(r'\D', '', n)))
    rows = []
    for row in ET.fromstring(z.read(sheet)).iter(ns + 'row'):
        cells = {}
        for c in row.iter(ns + 'c'):
            v, t = c.find(ns + 'v'), c.get('t')
            col = functools.reduce(lambda a, ch: a * 26 + ord(ch) - 64, re.match(r'[A-Z]*', c.get('r', '')).group(), 0) - 1
            col = col if col >= 0 else len(cells)
            if t == 's' and v is not None:
                cells[col] = shared[int(v.text)]
            elif t == 'inlineStr':
                cells[col] = ''.join(x.text or '' for x in c.iter(ns + 't'))
            elif v is not None:
                cells[col] = float(v.text) if t in (None, 'n') else v.text
        rows.append([cells.get(i, '') for i in range(max(cells, default=-1) + 1)])
    return rows


def clock(v):
    """Time of day in seconds: 9:00, 09:00:00, 2:30pm, or an Excel time."""
    if isinstance(v, float):
        return round(v % 1 * 86400)
    m = re.search(r'(\d{1,2})[:.](\d{2})(?::(\d{2}))?\s*([ap]m)?', str(v), re.I)
    if not m:
        return None
    h = int(m[1]) % 12 + (12 if m[4].lower() == 'pm' else 0) if m[4] else int(m[1])
    return h * 3600 + int(m[2]) * 60 + int(m[3] or 0)


def length(v):
    """A duration in seconds: 10 (minutes), 10 mins, 5:30 (m:ss), 1:05:00, or an Excel time like 00:10."""
    if isinstance(v, float):
        return round(v * 86400) if v < 1 else round(v * 60)
    v = re.sub(r'\s*mins?\.?$', '', str(v).strip().lower())
    if re.fullmatch(r'\d+(\.\d+)?', v):
        return round(float(v) * 60)
    if re.fullmatch(r'0+:\d{1,2}', v):  # 0:10 from Excel's h:mm
        return int(v.split(':')[1]) * 60
    if re.fullmatch(r'\d+(:\d{1,2}){1,2}', v):
        return functools.reduce(lambda a, b: a * 60 + int(b), v.split(':'), 0)
    return None


def import_rows(rows):
    """Rows from a spreadsheet -> (items, start time). Durations come from Duration, else Time off minus Time on,
    else the gap to the next start. A row with no segment name adds its people and mics to the row above."""
    def key(cell):
        c = re.sub(r'\(.*?\)', '', str(cell)).strip().lower().rstrip(':')
        return next((k for k, names in HEADINGS.items() if c in names), None)
    for hi, row in enumerate(rows[:30]):
        keys = [key(c) for c in row]
        if 'title' in keys and sum(k is not None for k in keys) >= 2:
            break
    else:
        raise ValueError('No heading row found. It needs a Segment column and at least one other, like Start or Duration.')
    items = []
    for row in rows[hi + 1:]:
        x = {keys[i]: row[i] for i in range(min(len(row), len(keys))) if keys[i] and row[i] not in ('', None)}
        txt = lambda k: ('%g' % x[k] if isinstance(x.get(k), float) else str(x.get(k, ''))).strip()
        who = ', '.join(filter(None, (txt('who'), txt('org'))))
        if not x:
            continue
        if not txt('title') and items and 'type' not in items[-1]:
            for k, v in (('who', who), ('audio', txt('audio')), ('lx', txt('lx')), ('vid', txt('vid')), ('notes', txt('notes'))):
                if v:
                    items[-1][k] = items[-1][k] + '; ' + v if items[-1][k] else v
            continue
        if txt('kind').lower() in ('section', 'header', 'heading'):
            items.append({'type': 'header', 'title': txt('title')})
            continue
        items.append({'cue': txt('cue'), 'title': txt('title'), 'who': who, 'kind': KINDS.get(txt('kind').lower(), ''),
                      'audio': txt('audio'), 'lx': txt('lx'), 'vid': txt('vid'), 'notes': txt('notes'),
                      'on': clock(x['start']) if 'start' in x else None, 'off': clock(x['end']) if 'end' in x else None,
                      'dur': length(x['dur']) if 'dur' in x else None})
    timed = [it for it in items if 'type' not in it]
    for n, it in enumerate(timed):
        nxt = next((t['on'] for t in timed[n + 1:] if t['on'] is not None), None)
        if it['kind'] == 'free':  # no duration: it runs until its End (or the next start)
            end = it['off'] if it['off'] is not None else nxt
            it['dur'], it['until'] = 0, '%02d:%02d' % (end // 3600, end % 3600 // 60) if end is not None else ''
        elif it['dur'] is None:
            end = it['off'] if it['off'] is not None else nxt
            it['dur'] = (end - it['on']) % 86400 if it['on'] is not None and end is not None else 0
    start = next((t['on'] for t in timed if t['on'] is not None), 9 * 3600)
    for it in timed:
        del it['on'], it['off']
    if not timed:
        raise ValueError('No segments found under the heading row.')
    return items, '%02d:%02d' % (start // 3600, start % 3600 // 60)


def read_upload(name, raw):
    ext = name.rsplit('.', 1)[-1].lower()
    if ext == 'numbers':
        raise ValueError('Numbers files cannot be read directly. In Numbers choose File, Export To, CSV (or Excel), then upload that file.')
    if ext in ('xls', 'pdf', 'doc', 'docx'):
        raise ValueError('ShowPace reads CSV or Excel (.xlsx). Save or export the running order as one of those, then upload it.')
    if ext in ('xlsx', 'xlsm'):
        return import_rows(xlsx_rows(raw))
    text = raw.decode('utf-8-sig', errors='replace')
    try:
        dialect = csv.Sniffer().sniff(text[:4096], ',;\t')
    except csv.Error:
        dialect = csv.excel
    return import_rows(list(csv.reader(io.StringIO(text), dialect)))


fails = {}  # 'address kind' -> times of recent wrong passwords


def locked_out(ip):
    with lock:
        recent = [t for t in fails.get(ip, []) if t > time.time() - FAIL_WINDOW]
        fails[ip] = recent
        return len(recent) >= MAX_FAILS


def failed(ip):
    with lock:
        fails.setdefault(ip, []).append(time.time())
    time.sleep(1)


def crew_state(s):
    """Crew links (crew view, Clock, phone remote) only open a show while it's live on the crew page.
    Otherwise they say it isn't open yet, or that it has finished once it has been run or archived."""
    if s.get('onCrew') and not s.get('archived'):
        return 'open'
    live = s.get('live') or {}
    return 'ended' if s.get('archived') or live.get('id') or live.get('log') else 'notyet'  # started at some point: it has finished


def crew_pass(sid):
    return read_json(os.path.join(DATA, 'crewpass.json'), {}).get(sid)


def crew_list():
    """The /crew page: shows pushed live and not archived. Locked shows don't reveal their link."""
    out = []
    for s in shows.values():
        if s.get('archived') or not s.get('onCrew'):
            continue
        sm = summary(s)
        x = {k: sm[k] for k in ('id', 'title', 'date', 'start', 'live')}
        x['locked'] = bool(s.get('crewLocked'))
        if not x['locked']:
            x['token'] = s['viewToken']
        out.append(x)
    return sorted(out, key=lambda x: (x['date'], x['start']))


class Handler(SimpleHTTPRequestHandler):
    server_version, sys_version = 'ShowPace', ''  # don't tell the world which Python this runs on

    def __init__(self, *a, **kw):
        super().__init__(*a, directory=DIR, **kw)

    def end_headers(self):
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')  # keeps crew links out of other sites' logs
        self.send_header('X-Robots-Tag', 'noindex, nofollow')  # private: keep it out of search engines
        self.send_header('Content-Security-Policy', CSP)  # even if something slipped through, no outside scripts or data leaks
        super().end_headers()

    def log_message(self, *a):
        pass

    # ---- helpers
    def send_json(self, code, data=None, cookie=None):
        body = json.dumps(data).encode() if data is not None else b''
        self.send_response(code)
        if cookie:
            self.send_header('Set-Cookie', cookie)
        if data is not None:
            self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        if 'application/json' not in self.headers.get('Content-Type', ''):
            raise ValueError  # also blocks cross-site form posts
        n = int(self.headers.get('Content-Length', 0))
        if n > 2_000_000:
            raise ValueError
        return json.loads(self.rfile.read(n))

    # Fixed types, so a Windows computer with odd file settings still serves scripts as scripts
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.html': 'text/html; charset=utf-8',
                      '.js': 'text/javascript; charset=utf-8', '.csv': 'text/csv; charset=utf-8'}

    def sess_id(self):
        m = re.search(r'showpace_session=([A-Za-z0-9_-]+)', self.headers.get('Cookie', ''))
        return m and m.group(1)

    def user(self):
        sess = read_json(os.path.join(DATA, 'sessions.json'), {}).get(self.sess_id())
        return sess['user'] if sess and sess['exp'] > time.time() and sess['user'] in users() else None

    def admin(self):
        u = self.user()
        return u if u and users()[u].get('admin') else None

    def ip(self):
        # Behind Caddy the real address is the last X-Forwarded-For entry (Caddy sets it). Run on its own, the header can't be trusted.
        if PROXY and self.headers.get('X-Forwarded-For'):
            return self.headers['X-Forwarded-For'].split(',')[-1].strip()
        return self.client_address[0]

    def start_session(self, name):
        """Log this browser in: a new session token in an HttpOnly cookie."""
        days, token = settings()['sessionDays'], secrets.token_urlsafe(32)
        path = os.path.join(DATA, 'sessions.json')
        with lock:
            sess = {k: v for k, v in read_json(path, {}).items() if v['exp'] > time.time()}
            sess[token] = {'user': name, 'exp': time.time() + days * 86400}
            write_json(path, sess)
        return f'showpace_session={token}; Path=/; HttpOnly; SameSite=Lax; Max-Age={days * 86400}' + ('; Secure' if SECURE else '')

    def send_bytes(self, body, ctype):
        self.send_response(200)
        self.send_header('Content-Type', ctype)
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def crew_ok(self, s):
        """A show pushed live with a crew password only reaches browsers holding its current key. Every push live makes a
        new key, so changing or adding a password always asks everyone again, even people who already had the link."""
        if not s.get('crewLocked'):
            return True
        p = crew_pass(s['id']) or {}
        m = re.search(r'(?:^|;\s*)%s_crew_%s=([A-Za-z0-9_-]+)' % (COOKIE, s['id']), self.headers.get('Cookie', ''))
        return bool(m and p.get('key') and hmac.compare_digest(p['key'], m.group(1)))

    def crew_cookie(self, s):
        """After the right password: the show's current crew key, for this browser only."""
        p = crew_pass(s['id']) or {}
        if not (s.get('crewLocked') and p.get('key')):
            return None
        return f"{COOKIE}_crew_{s['id']}={p['key']}; Path=/; HttpOnly; SameSite=Lax; Max-Age={30 * 86400}" + ('; Secure' if SECURE else '')

    def by_token(self, token):
        return next((s for s in shows.values() if hmac.compare_digest(s.get('viewToken', ''), token)), None)

    # ---- routes
    def do_GET(self):
        path = self.path.split('?')[0]
        if path in ('/', '/crew') or path.startswith(('/v/', '/r/')):
            self.path = '/index.html'
            return super().do_GET()
        if path in STATIC:
            return super().do_GET()
        if path == '/api/brand':
            return self.send_json(200, look())
        if path == '/favicon.svg':
            return self.send_bytes(favicon(), 'image/svg+xml')
        if path == '/api/time':  # every screen sets its clock by this
            return self.send_json(200, {'t': int(time.time() * 1000)})
        if path == '/api/crew':
            return self.send_json(200, crew_list())
        if path == '/api/me':  # who is logged in; with nobody set up yet, the page shows the first-run screen
            u = self.user()
            if u:
                return self.send_json(200, {'user': u, 'admin': bool(users()[u].get('admin'))})
            return self.send_json(401, {'error': 'Log in', 'setup': not users()})
        m = re.fullmatch(r'/api/view/([A-Za-z0-9_-]+)', path)
        if m:
            s = self.by_token(m.group(1))
            if not s:
                return self.send_json(404, {'error': 'This crew link is not valid'})
            if crew_state(s) != 'open':
                return self.send_json(403, {'off': crew_state(s), 'title': s.get('title', '')})
            if not self.crew_ok(s):
                return self.send_json(403, {'locked': True, 'title': s.get('title', '')})
            return self.send_json(200, s)
        m = re.fullmatch(r'/api/events/(v/)?([A-Za-z0-9_-]+)', path)
        if m:
            s = self.by_token(m.group(2)) if m.group(1) else (self.user() and shows.get(m.group(2)))
            return self.events(s['id'], crew=bool(m.group(1))) if s else self.send_json(404, {'error': 'Not found'})
        if not self.user():
            return self.send_json(401, {'error': 'Log in'})
        if path in ('/api/users', '/api/settings'):
            if not self.admin():
                return self.send_json(403, {'error': 'Admins only'})
            if path == '/api/settings':
                return self.send_json(200, settings())
            return self.send_json(200, sorted(({'name': n, 'admin': bool(u.get('admin'))} for n, u in users().items()), key=lambda x: x['name']))
        if path == '/api/shows':
            return self.send_json(200, sorted((summary(s) for s in shows.values()), key=lambda x: (x['date'], x['start'])))
        m = re.fullmatch(r'/api/shows/([A-Za-z0-9_-]+)', path)
        if m and m.group(1) in shows:
            return self.send_json(200, shows[m.group(1)])
        self.send_json(404, {'error': 'Not found'})

    def do_HEAD(self):
        self.send_error(405)

    def do_POST(self):
        path = self.path.split('?')[0]
        try:
            data = self.body()
        except Exception:
            return self.send_json(400, {'error': 'Bad request'})
        sess_path = os.path.join(DATA, 'sessions.json')
        who = self.ip() + ' ' + path.split('/')[2]  # wrong passwords count per address and per kind: login, crew, remote
        if path == '/api/login' or path == '/api/setup' or (path.startswith(('/api/crew/', '/api/remote/', '/api/view/')) and not path.endswith('/act')):  # password routes only
            if locked_out(who):
                return self.send_json(429, {'error': 'Too many wrong passwords. Wait 15 minutes and try again.'})
        if path == '/api/setup':  # first run only: the first login, always an admin
            name = str(data.get('user', '')).lower().strip()
            with lock:
                if users():
                    return self.send_json(409, {'error': 'ShowPace is already set up. Log in instead.'})
                err = add_user(name, str(data.get('pass', '')), True)
            if err:
                return self.send_json(400, {'error': err})
            return self.send_json(200, {'user': name, 'admin': True}, self.start_session(name))
        if path == '/api/login':
            name = str(data.get('user', '')).lower().strip()
            u = users().get(name)
            if not u or not hmac.compare_digest(u['hash'], hash_pw(str(data.get('pass', '')), u['salt'])):
                failed(who)
                return self.send_json(401, {'error': 'That username and password do not match'})
            return self.send_json(200, {'user': name, 'admin': bool(u.get('admin'))}, self.start_session(name))
        if path == '/api/logout':
            if self.sess_id():
                with lock:
                    sess = read_json(sess_path, {})
                    sess.pop(self.sess_id(), None)
                    write_json(sess_path, sess)
            return self.send_json(200, {}, 'showpace_session=; Path=/; Max-Age=0')
        crew_path = os.path.join(DATA, 'crewpass.json')  # kept out of the show file, which crew devices receive
        m = re.fullmatch(r'/api/crew/([A-Za-z0-9_-]+)', path) or re.fullmatch(r'/api/view/([A-Za-z0-9_-]+)', path)
        if m:  # the /crew page sends the show's id; a crew link sends its token
            s = shows.get(m.group(1)) if path.startswith('/api/crew/') else self.by_token(m.group(1))
            p = s and crew_pass(s['id'])
            if s and crew_state(s) != 'open':
                s = None
            if s and (not s.get('crewLocked') or (p and hmac.compare_digest(p['hash'], hash_pw(str(data.get('pass', '')), p['salt'])))):
                return self.send_json(200, {'token': s['viewToken']}, self.crew_cookie(s))
            failed(who)
            return self.send_json(403, {'error': 'That password is not right for this show'})
        # Caller remote: the show's crew link plus its own remote password lets a phone run the show (the live state only)
        remote_path = os.path.join(DATA, 'remote.json')
        m = re.fullmatch(r'/api/remote/([A-Za-z0-9_-]+)(/act)?', path)
        if m:
            s = self.by_token(m.group(1))
            r = s and read_json(remote_path, {}).get(s['id'])
            if m.group(2):  # a press on the phone: its new live state, with the key it got for the right password
                if not r or not hmac.compare_digest(r['key'].encode(), str(data.get('key', '')).encode()):
                    return self.send_json(403, {'error': 'This remote has been locked. Ask the show caller for the new remote password.'})
                if crew_state(s) != 'open':
                    return self.send_json(403, {'error': 'This show is not live on the crew page'})
                with lock:
                    s = shows.get(s['id'])
                    if not s:
                        return self.send_json(404, {'error': 'Not found'})
                    s['live'] = clean_live(data.get('live'))  # the running order itself can't be touched
                    s['src'] = self.headers.get('x-showpace-src', 'remote')
                    version[s['id']] += 1
                    save_show(s)
                    lock.notify_all()
                return self.send_json(200, {})
            if r and hmac.compare_digest(r['hash'], hash_pw(str(data.get('pass', '')), r['salt'])):
                return self.send_json(200, {'key': r['key']}, self.crew_cookie(s))  # the caller needs only the remote password
            failed(who)
            return self.send_json(403, {'error': 'That remote password is not right'})
        if not self.user():
            return self.send_json(401, {'error': 'Log in'})
        if path == '/api/users':  # add a login, or change one's password or admin rights
            me = self.admin()
            if not me:
                return self.send_json(403, {'error': 'Admins only'})
            name, pw = str(data.get('user', '')).lower().strip(), str(data.get('pass', ''))
            err = add_user(name, pw, bool(data.get('admin')))
            if err:
                return self.send_json(400, {'error': err})
            if pw:  # a new password logs that person out everywhere else
                log_out(name, keep=self.sess_id() if name == me else None)
            return self.send_json(200, {'user': name})
        m = re.fullmatch(r'/api/shows/([A-Za-z0-9_-]+)/remote', path)
        if m and m.group(1) in shows:  # set a new remote password (locks out old phones), or switch the remote off
            sid, pw = m.group(1), str(data.get('pass', '')).strip()
            with lock:
                remotes = read_json(remote_path, {})
                if pw:
                    salt = secrets.token_hex(16)
                    remotes[sid] = {'salt': salt, 'hash': hash_pw(pw, salt), 'key': secrets.token_urlsafe(24)}
                else:
                    remotes.pop(sid, None)
                write_json(remote_path, remotes)
                shows[sid]['remoteOn'] = bool(pw)
                save_show(shows[sid])
            return self.send_json(200, {'remoteOn': bool(pw)})
        # Push live (onto the crew page, with a password that may be empty) or take down
        m = re.fullmatch(r'/api/shows/([A-Za-z0-9_-]+)/crew', path)
        if m and m.group(1) in shows:
            sid, on = m.group(1), bool(data.get('on'))
            if on and shows[sid].get('archived'):
                return self.send_json(409, {'error': 'Restore the show before pushing it live'})
            pw = str(data.get('pass', '')).strip() if on else ''
            with lock:
                passes = read_json(crew_path, {})
                if pw:
                    salt = secrets.token_hex(16)
                    passes[sid] = {'salt': salt, 'hash': hash_pw(pw, salt), 'key': secrets.token_urlsafe(24)}  # new key: everyone asked again
                else:
                    passes.pop(sid, None)
                write_json(crew_path, passes)
                shows[sid]['onCrew'], shows[sid]['crewLocked'] = on, bool(pw)
                version[sid] += 1
                save_show(shows[sid])
                lock.notify_all()
            return self.send_json(200, {'onCrew': on, 'crewLocked': bool(pw)})
        if path == '/api/import':  # a running order from CSV or Excel becomes a new show
            name = str(data.get('name') or 'Imported show')
            try:
                items, start = read_upload(name, base64.b64decode(str(data.get('data', ''))))
            except ValueError as e:
                return self.send_json(400, {'error': str(e)})
            except Exception:
                return self.send_json(400, {'error': 'That file could not be read. Use the template, saved as CSV or Excel (.xlsx).'})
            data = {'title': re.sub(r'\.[^.]+$', '', name), 'date': str(datetime.date.today()), 'start': start, 'items': items}
            path = '/api/shows'
        if path == '/api/shows':
            sid = secrets.token_urlsafe(9)
            try:
                s = clean(data, {'id': sid, 'viewToken': secrets.token_urlsafe(18)})
            except ValueError:
                return self.send_json(400, {'error': 'Not a ShowPace show'})
            with lock:
                shows[sid], version[sid] = s, 1
                save_show(s)
            return self.send_json(201, s)
        self.send_json(404, {'error': 'Not found'})

    def do_PUT(self):
        if self.path.split('?')[0] == '/api/settings':
            if not self.admin():
                return self.send_json(403, {'error': 'Admins only'})
            try:
                with lock:
                    s = clean_settings(self.body(), settings())
                    write_json(os.path.join(DATA, 'settings.json'), s)
            except ValueError as e:
                return self.send_json(400, {'error': str(e) or 'Bad request'})
            return self.send_json(200, look())
        m = re.fullmatch(r'/api/shows/([A-Za-z0-9_-]+)', self.path.split('?')[0])
        if not m or m.group(1) not in shows:
            return self.send_json(404, {'error': 'Not found'})
        if not self.user():
            return self.send_json(401, {'error': 'Log in'})
        sid = m.group(1)
        try:
            s = clean(self.body(), shows[sid])
        except Exception:
            return self.send_json(400, {'error': 'Not a ShowPace show'})
        # Last save wins. Fine with one person calling the show; two people editing the same show at once would overwrite each other.
        if s['archived']:
            s['onCrew'] = False  # archiving takes it off the crew page, so restoring it doesn't quietly reopen it
        s['src'] = self.headers.get('x-showpace-src', '')
        with lock:
            shows[sid] = s
            version[sid] += 1
            save_show(s)
            lock.notify_all()
        self.send_json(200, {})

    def do_DELETE(self):
        """Delete an archived show (the file moves to data/deleted/, so a slip can still be undone by hand), or a login."""
        if not self.user():
            return self.send_json(401, {'error': 'Log in'})
        m = re.fullmatch(r'/api/users/([a-z0-9._-]+)', self.path.split('?')[0])
        if m:
            me, name = self.admin(), m.group(1)
            if not me:
                return self.send_json(403, {'error': 'Admins only'})
            if name == me:
                return self.send_json(400, {'error': "You can't remove your own login"})
            with lock:
                us = users()
                if name not in us:
                    return self.send_json(404, {'error': 'There is no login called ' + name})
                us.pop(name)
                if not any(u.get('admin') for u in us.values()):
                    return self.send_json(400, {'error': 'Keep at least one admin'})
                write_json(os.path.join(DATA, 'users.json'), us)
            log_out(name)
            return self.send_json(200, {})
        m = re.fullmatch(r'/api/shows/([A-Za-z0-9_-]+)', self.path.split('?')[0])
        if not m or m.group(1) not in shows:
            return self.send_json(404, {'error': 'Not found'})
        sid = m.group(1)
        if not shows[sid].get('archived'):
            return self.send_json(409, {'error': 'Archive the show before deleting it'})
        with lock:
            os.makedirs(os.path.join(DATA, 'deleted'), exist_ok=True)
            os.replace(os.path.join(SHOWS, sid + '.json'), os.path.join(DATA, 'deleted', f'{sid}-{int(time.time())}.json'))
            for f in ('crewpass.json', 'remote.json'):
                passes = read_json(os.path.join(DATA, f), {})
                if passes.pop(sid, None):
                    write_json(os.path.join(DATA, f), passes)
            del shows[sid]
            lock.notify_all()  # open crew screens let go of it
        self.send_json(200, {})

    # Server-sent events: the show on connect, then every change, plus how many devices are watching.
    def events(self, sid, crew=False):
        if viewers.get(sid, 0) >= MAX_VIEWERS:
            return self.send_json(503, {'error': 'Too many devices are watching this show'})
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream')
        self.send_header('X-Accel-Buffering', 'no')
        self.end_headers()
        with lock:
            viewers[sid] = viewers.get(sid, 0) + 1
            version[sid] += 1
            lock.notify_all()
        seen = (-1, -1)
        try:
            while True:
                with lock:
                    lock.wait_for(lambda: sid not in shows or (version[sid], viewers[sid]) != seen, timeout=15)
                    if sid not in shows:  # deleted: crew screens say it has finished
                        if crew:
                            self.wfile.write(b'data: {"off":"ended","title":""}\n\n')
                        break
                    now, s = (version[sid], viewers[sid]), shows[sid]
                    st = crew_state(s) if crew else 'open'  # not on the crew page, or no current password key: never the show
                    body = ({'off': st} if st != 'open' else {'locked': True} if crew and not self.crew_ok(s) else {'show': s})
                    if 'show' not in body:
                        body['title'] = s.get('title', '')
                    msg = json.dumps({'viewers': now[1], 't': int(time.time() * 1000), **body}, separators=(',', ':')).encode() if now != seen else None
                seen = now
                self.wfile.write(b'data: %s\n\n' % msg if msg else b': ping\n\n')
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, TimeoutError):
            pass
        finally:
            with lock:
                viewers[sid] -= 1
                version[sid] += 1
                lock.notify_all()


def set_user(name, remove=False):
    """From the command line: add an admin login or reset a password, or remove a login. Logs that person out everywhere."""
    name = name.lower().strip()
    os.makedirs(DATA, exist_ok=True)
    if remove:
        us = users()
        if us.pop(name, None) is None:
            sys.exit(f'There is no login called {name}.')
        write_json(os.path.join(DATA, 'users.json'), us)
    else:
        err = add_user(name, getpass.getpass(f'New password for {name}: '), True)
        if err:
            sys.exit(err + '.')
    log_out(name)
    print(f'{name} has been removed.' if remove else f'{name} can now log in, as an admin.')


def lan_address():
    """This computer's address on the local network, so iPads and phones on the same Wi-Fi can find it."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1))  # nothing is sent; this just picks the network card
            return s.getsockname()[0]
    except OSError:
        return None


if __name__ == '__main__':
    args = sys.argv[1:]
    if len(args) == 2 and args[0] in ('adduser', 'deluser'):
        set_user(args[1], remove=args[0] == 'deluser')
        sys.exit()
    if len(args) == 2 and args[0] == '--port' and args[1].isdigit():
        PORT = int(args[1])
    elif args:
        sys.exit(__doc__)
    load()
    try:
        srv = ThreadingHTTPServer(('0.0.0.0', PORT), Handler)
    except OSError:
        sys.exit(f'Port {PORT} is already in use. Is ShowPace already running in another window?\n'
                 f'To use another port:  python3 server.py --port {PORT + 1}')
    srv.daemon_threads = True
    if PROXY:  # in Docker behind Caddy: people use the web address, not this port
        print('ShowPace is running behind Caddy. Open your web address in a browser.', flush=True)
    else:
        lan = lan_address()
        print(f'\nShowPace is running.\n  On this computer:  http://localhost:{PORT}')
        if lan and not lan.startswith('127.'):
            print(f'  On other devices:  http://{lan}:{PORT}   (same Wi-Fi)')
        if not users():
            print('  First time? Open it in your browser and create the admin login.')
        print('  Press Ctrl+C to stop it.\n', flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
