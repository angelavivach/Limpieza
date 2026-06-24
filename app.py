"""
Gmail Cleaner — versión cloud (Railway / Render)
Configurar variables de entorno antes de desplegar:
  APP_PASSWORD        → contraseña para entrar a la app
  SECRET_KEY          → cualquier texto aleatorio largo
  GOOGLE_CLIENT_ID    → Client ID de Google Cloud Console
  GOOGLE_CLIENT_SECRET→ Client Secret de Google Cloud Console
  REDIRECT_URI        → https://TU-DOMINIO.railway.app/auth/callback
"""

import json, os, time, functools
from flask import (Flask, request, redirect, session,
                   jsonify, send_from_directory, url_for)
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Config ──────────────────────────────────────────────────────────────────
app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('SECRET_KEY', 'cambia-esto-en-produccion')

SCOPES       = ['https://www.googleapis.com/auth/gmail.modify']
APP_PASSWORD = os.environ.get('APP_PASSWORD', 'admin')
CLIENT_ID    = os.environ.get('GOOGLE_CLIENT_ID', '')
CLIENT_SECRET= os.environ.get('GOOGLE_CLIENT_SECRET', '')
REDIRECT_URI = os.environ.get('REDIRECT_URI', 'http://localhost:8765/auth/callback')
TOKENS_DIR   = os.environ.get('TOKENS_DIR', os.path.join(os.path.dirname(__file__), 'tokens'))
EXCLUIR      = '-is:starred'

os.makedirs(TOKENS_DIR, exist_ok=True)

FILTROS = {
    "promociones": 'category:promotions',
    "baja":        'unsubscribe OR "darse de baja" OR "cancelar suscripción" OR "darte de baja"',
    "aliexpress":  'from:aliexpress',
    "paypal":      'from:paypal',
    "amazon":      'from:amazon',
    "noreply":     'from:noreply',
    "dhl":         'from:dhl OR from:"DHL Paket"',
    "gls":         'from:gls OR from:gls-group OR "GLS"',
    "correos":     'from:correos OR from:correoexpress',
    "pedidos":     '"confirmación de pedido" OR "order confirmation" OR "confirmación de compra" OR "tu pedido" OR "your order" OR "envío" OR "recoger tu pedido"',
    "vinted":      'from:vinted OR from:noreply@vinted.es OR "vinted.es" OR "vinted.com"',
    "wallapop":    'from:wallapop OR from:noreply@wallapop.com OR "wallapop.com"',
    "spotify":     'from:spotify OR from:no-reply@spotify.com',
    "google":      'from:no-reply@accounts.google.com OR from:googleplay-noreply@google.com OR "política de privacidad de google" OR "recordatorio de google"',
    "noleidos":    None,
}

# ── Helpers auth ─────────────────────────────────────────────────────────────
def requires_login(f):
    @functools.wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def token_path(email):
    safe = email.replace('@', '_at_').replace('.', '_')
    return os.path.join(TOKENS_DIR, f'{safe}.json')


def make_flow(state=None):
    client_config = {"web": {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
        "redirect_uris": [REDIRECT_URI],
    }}
    return Flow.from_client_config(
        client_config, scopes=SCOPES,
        redirect_uri=REDIRECT_URI, state=state
    )


def get_service(email):
    path = token_path(email)
    if not os.path.exists(path):
        return None
    creds = Credentials.from_authorized_user_file(path, SCOPES)
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(path, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds) if creds and creds.valid else None


def listar_cuentas():
    cuentas = []
    for fname in os.listdir(TOKENS_DIR):
        if not fname.endswith('.json'):
            continue
        email = fname[:-5].replace('_at_', '@')
        parts = email.split('@')
        if len(parts) == 2:
            email = parts[0].replace('_', '.') + '@' + parts[1].replace('_', '.')
        cuentas.append({'email': email})
    return cuentas


# ── Gmail helpers ─────────────────────────────────────────────────────────────
def _buscar_todos(svc, query=None, label_ids=None):
    mensajes, page_token = [], None
    while True:
        kwargs = dict(userId='me', maxResults=500)
        if page_token:   kwargs['pageToken']  = page_token
        if label_ids:    kwargs['labelIds']   = label_ids
        if query:        kwargs['q']          = query
        resp  = svc.users().messages().list(**kwargs).execute()
        mensajes.extend(resp.get('messages', []))
        page_token = resp.get('nextPageToken')
        if not page_token:
            break
    return mensajes


def _get_labels(svc, msg_id):
    try:
        return svc.users().messages().get(
            userId='me', id=msg_id, format='minimal'
        ).execute().get('labelIds', [])
    except Exception:
        return []


def _obtener_resumen(svc, msg_id):
    msg = svc.users().messages().get(
        userId='me', id=msg_id, format='metadata',
        metadataHeaders=['From', 'Subject', 'Date']
    ).execute()
    h = {x['name']: x['value'] for x in msg['payload'].get('headers', [])}
    return {'id': msg_id, 'from': h.get('From',''), 'subject': h.get('Subject',''), 'date': h.get('Date','')}


def _mover_a_papelera(svc, msg_id):
    for intento in range(5):
        try:
            svc.users().messages().trash(userId='me', id=msg_id).execute()
            return True
        except HttpError as e:
            if e.resp.status in (429, 500, 503):
                time.sleep(2 ** intento)
            else:
                return False
    return False


def listar_mensajes(svc, filtros_str, max_results=300):
    keys = [k for k in filtros_str.split(',') if k]
    tiene_noleidos = 'noleidos' in keys
    otras = [k for k in keys if k != 'noleidos' and FILTROS.get(k)]
    ids_vistos, mensajes = set(), []

    if otras:
        q = '(' + ' OR '.join(FILTROS[k] for k in otras) + f') {EXCLUIR}'
        for m in _buscar_todos(svc, query=q):
            if m['id'] not in ids_vistos:
                ids_vistos.add(m['id'])
                mensajes.append(m)

    if tiene_noleidos:
        for m in _buscar_todos(svc, label_ids=['UNREAD']):
            if m['id'] not in ids_vistos:
                if 'STARRED' not in _get_labels(svc, m['id']):
                    ids_vistos.add(m['id'])
                    mensajes.append(m)

    return mensajes


# ── Rutas: login ──────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = ''
    if request.method == 'POST':
        if request.form.get('password') == APP_PASSWORD:
            session['logged_in'] = True
            return redirect('/')
        error = 'Contraseña incorrecta'
    return f'''<!DOCTYPE html>
<html lang="es">
<head><meta charset="UTF-8"><title>Gmail Cleaner · Acceso</title>
<style>
  *{{box-sizing:border-box;margin:0;padding:0}}
  body{{background:#0f1117;color:#e8eaf0;font-family:-apple-system,sans-serif;
       display:flex;align-items:center;justify-content:center;min-height:100vh}}
  .card{{background:#1a1d27;border:1px solid #2e3248;border-radius:12px;padding:40px;
         width:340px;text-align:center}}
  .logo{{font-size:36px;margin-bottom:12px}}
  h1{{font-size:22px;font-weight:700;margin-bottom:6px}}
  p{{color:#7b829a;font-size:14px;margin-bottom:28px}}
  input{{width:100%;background:#22263a;border:1.5px solid #2e3248;border-radius:8px;
         padding:12px 14px;color:#e8eaf0;font-size:15px;margin-bottom:12px;outline:none}}
  input:focus{{border-color:#4fffb0}}
  button{{width:100%;background:#4fffb0;color:#0f1117;border:none;border-radius:8px;
          padding:13px;font-size:15px;font-weight:700;cursor:pointer}}
  .err{{color:#ff4f6b;font-size:13px;margin-top:8px}}
</style></head>
<body><div class="card">
  <div class="logo">🧹</div>
  <h1>Gmail Cleaner</h1>
  <p>Introduce la contraseña para acceder</p>
  <form method="POST">
    <input type="password" name="password" placeholder="Contraseña" autofocus>
    <button type="submit">Entrar</button>
    {"<p class='err'>"+error+"</p>" if error else ""}
  </form>
</div></body></html>'''


@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')


# ── Rutas: OAuth Google ───────────────────────────────────────────────────────
@app.route('/auth/start')
@requires_login
def auth_start():
    flow = make_flow()
    auth_url, state = flow.authorization_url(access_type='offline', prompt='consent')
    session['oauth_state'] = state
    return redirect(auth_url)


@app.route('/auth/callback')
@requires_login
def auth_callback():
    flow = make_flow(state=session.get('oauth_state'))
    flow.fetch_token(authorization_response=request.url.replace('http://', 'https://') if 'localhost' not in request.url else request.url)
    creds = flow.credentials
    svc   = build('gmail', 'v1', credentials=creds)
    email = svc.users().getProfile(userId='me').execute()['emailAddress']
    with open(token_path(email), 'w') as f:
        f.write(creds.to_json())
    session['active_account'] = email
    return redirect('/')


# ── Rutas: app principal ──────────────────────────────────────────────────────
@app.route('/')
@app.route('/LimpGmailAvd')
@requires_login
def index():
    return send_from_directory('static', 'index.html')


# ── API ───────────────────────────────────────────────────────────────────────
@app.route('/api/cuentas')
@requires_login
def api_cuentas():
    return jsonify({'cuentas': listar_cuentas(), 'activa': session.get('active_account')})


@app.route('/api/seleccionar-cuenta', methods=['POST'])
@requires_login
def api_seleccionar_cuenta():
    email = request.json.get('email')
    svc   = get_service(email)
    if not svc:
        return jsonify({'ok': False, 'error': 'Token inválido'}), 400
    session['active_account'] = email
    return jsonify({'ok': True, 'email': email})


@app.route('/api/eliminar-cuenta', methods=['POST'])
@requires_login
def api_eliminar_cuenta():
    email = request.json.get('email', '')
    path  = token_path(email)
    if os.path.exists(path):
        os.remove(path)
    if session.get('active_account') == email:
        session.pop('active_account', None)
    return jsonify({'ok': True})


@app.route('/api/buscar')
@requires_login
def api_buscar():
    email = session.get('active_account')
    svc   = get_service(email)
    if not svc:
        return jsonify({'error': 'No hay cuenta activa'}), 400
    filtros_str = request.args.get('filtros', '')
    try:
        msgs   = listar_mensajes(svc, filtros_str, max_results=300)
        correos = []
        for m in msgs:
            try:
                correos.append(_obtener_resumen(svc, m['id']))
            except Exception:
                pass
        return jsonify({'total': len(msgs), 'correos': correos})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/borrar')
@requires_login
def api_borrar():
    email = session.get('active_account')
    svc   = get_service(email)
    if not svc:
        return jsonify({'error': 'No hay cuenta activa'}), 400
    filtros_str = request.args.get('filtros', '')
    try:
        msgs = listar_mensajes(svc, filtros_str, max_results=9999)
        ok   = sum(1 for m in msgs if _mover_a_papelera(svc, m['id']))
        return jsonify({'borrados': ok, 'total': len(msgs)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/borrar-ids', methods=['POST'])
@requires_login
def api_borrar_ids():
    email = session.get('active_account')
    svc   = get_service(email)
    if not svc:
        return jsonify({'error': 'No hay cuenta activa'}), 400
    ids = request.json.get('ids', [])
    ok  = sum(1 for i in ids if _mover_a_papelera(svc, i))
    return jsonify({'borrados': ok, 'total': len(ids)})


@app.route('/api/borrar-noleidos')
@requires_login
def api_borrar_noleidos():
    email = session.get('active_account')
    svc   = get_service(email)
    if not svc:
        return jsonify({'error': 'No hay cuenta activa'}), 400
    try:
        candidatos = _buscar_todos(svc, label_ids=['UNREAD'])
        ok = 0
        for m in candidatos:
            if 'STARRED' not in _get_labels(svc, m['id']):
                if _mover_a_papelera(svc, m['id']):
                    ok += 1
        return jsonify({'borrados': ok, 'total': len(candidatos)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8765)), debug=False)
