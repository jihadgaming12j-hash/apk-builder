import os, re, sys, json, shutil, subprocess, zipfile, io, urllib.request

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'android'))
MAIN = os.path.join(ROOT, 'app', 'src', 'main')
env = os.environ

JAVA_KEYWORDS = set('''abstract assert boolean break byte case catch char class const continue default do double
else enum extends final finally float for goto if implements import instanceof int interface long native new
package private protected public return short static strictfp super switch synchronized this throw throws
transient try void volatile while true false null'''.split())


def fail(msg):
    print('ERROR:', msg)
    sys.exit(1)


def download(url, limit):
    req = urllib.request.Request(url, headers={'User-Agent': 'MrAiPrime-Builder'})
    with urllib.request.urlopen(req, timeout=90) as r:
        data = r.read(limit + 1)
    if len(data) > limit:
        fail('file too large')
    return data


def xml_escape(s):
    s = s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    s = s.replace('\\', '\\\\').replace("'", "\\'").replace('"', '\\"')
    if s[:1] in ('@', '?'):
        s = '\\' + s
    return s


# ---- inputs -------------------------------------------------------------
name = re.sub(r'[\x00-\x1f%]', '', env.get('APP_NAME', '')).strip()[:40] or 'My App'

app_id = env.get('APP_ID', '').strip().lower()
if not re.fullmatch(r'[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+', app_id):
    fail('invalid package name')
app_id = '.'.join(p + 'app' if p in JAVA_KEYWORDS else p for p in app_id.split('.'))

orient = env.get('ORIENT', 'unspecified')
if orient not in ('unspecified', 'portrait', 'landscape'):
    orient = 'unspecified'
refresh = env.get('REFRESH', 'true') == 'true'
mode = env.get('MODE', 'url')

# ---- start page ---------------------------------------------------------
if mode == 'file':
    src = env.get('SOURCE_URL', '').strip()
    if not re.match(r'https?://\S+$', src):
        fail('invalid source url')
    data = download(src, 40 * 1024 * 1024)
    www = os.path.join(MAIN, 'assets', 'www')
    shutil.rmtree(www, ignore_errors=True)
    os.makedirs(www)
    if data[:2] == b'PK':
        total = 0
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                p = os.path.normpath(info.filename)
                if info.is_dir() or p.startswith('..') or os.path.isabs(p) or p.startswith('__MACOSX'):
                    continue
                total += info.file_size
                if total > 200 * 1024 * 1024:
                    fail('zip too large after extraction')
                dest = os.path.join(www, p)
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with z.open(info) as s, open(dest, 'wb') as d:
                    shutil.copyfileobj(s, d)
    else:
        with open(os.path.join(www, 'index.html'), 'wb') as f:
            f.write(data)
    entries = [e for e in os.listdir(www) if e != '__MACOSX']
    if 'index.html' not in entries and len(entries) == 1 and os.path.isdir(os.path.join(www, entries[0])):
        inner = os.path.join(www, entries[0])
        for e in os.listdir(inner):
            shutil.move(os.path.join(inner, e), os.path.join(www, e))
        os.rmdir(inner)
    if not os.path.exists(os.path.join(www, 'index.html')):
        fail('index.html not found in the uploaded source')
    start = 'file:///android_asset/www/index.html'
else:
    start = env.get('START_URL', '').strip()
    if not re.match(r'https?://\S+$', start):
        fail('invalid website url')

with open(os.path.join(MAIN, 'assets', 'config.json'), 'w') as f:
    json.dump({'url': start, 'refresh': refresh}, f)

# ---- app name -----------------------------------------------------------
with open(os.path.join(MAIN, 'res', 'values', 'strings.xml'), 'w', encoding='utf-8') as f:
    f.write('<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <string name="app_name">%s</string>\n</resources>\n' % xml_escape(name))

# ---- icon ---------------------------------------------------------------
icon_dir = os.path.join(MAIN, 'res', 'mipmap-xxxhdpi')
os.makedirs(icon_dir, exist_ok=True)
icon_out = os.path.join(icon_dir, 'ic_launcher.png')
ok = False
icon_url = env.get('ICON_URL', '').strip()
if re.match(r'https?://\S+$', icon_url):
    try:
        raw = download(icon_url, 8 * 1024 * 1024)
        with open('/tmp/icon.bin', 'wb') as f:
            f.write(raw)
        r = subprocess.run(['convert', '/tmp/icon.bin[0]', '-resize', '192x192', '-background', 'none',
                            '-gravity', 'center', '-extent', '192x192', icon_out])
        ok = r.returncode == 0 and os.path.exists(icon_out)
    except Exception as e:
        print('icon download failed, using default:', e)
if not ok:
    r = subprocess.run(['convert', '-size', '192x192', 'gradient:#7c3aed-#2563eb', icon_out])
    if r.returncode != 0:
        fail('could not create icon')

# ---- pass final values to later steps ----------------------------------
with open(env['GITHUB_ENV'], 'a') as f:
    f.write('FINAL_APP_ID=%s\nFINAL_ORIENT=%s\n' % (app_id, orient))
print('Prepared:', name, app_id, orient, 'refresh=%s' % refresh, start)
