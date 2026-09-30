"""
Room Rent Management App — Room 33
Flask backend: SQLite locally, PostgreSQL (Supabase) in production.
"""
from flask import (Flask, abort, render_template, request, redirect,
                   url_for, send_file, flash, session, jsonify)
import os, io, hmac, secrets
from datetime import datetime
from xml.sax.saxutils import escape
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

from app_config import DB_PATH, ROOM_NAME
from db import get_db, init_schema

# ─── App setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=os.environ.get('RENDER', '') != '',
)

MONTHS = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
MONTH_NAMES = {
    'jan':'January','feb':'February','mar':'March','apr':'April',
    'may':'May','jun':'June','jul':'July','aug':'August',
    'sep':'September','oct':'October','nov':'November','dec':'December'
}
ADMIN_PASSWORD_HASH = os.environ.get(
    'ADMIN_PASSWORD_HASH',
    generate_password_hash('admin1234')   # default — override in .env
)

# ─── CSRF + Auth ───────────────────────────────────────────────────────────────
@app.before_request
def protect():
    if request.method == 'POST' and request.endpoint != 'login':
        token = request.form.get('csrf_token', '')
        expected = session.get('csrf_token', '')
        if not expected or not hmac.compare_digest(token, expected):
            abort(400, 'Security token mismatch. Reload the page and try again.')
    if request.endpoint in ('login', 'static', 'health'):
        return
    if not session.get('authenticated'):
        return redirect(url_for('login', next=request.path))

@app.context_processor
def inject_globals():
    token = session.get('csrf_token')
    if not token:
        token = secrets.token_urlsafe(32)
        session['csrf_token'] = token
    return {'csrf_token': token, 'room_name': ROOM_NAME,
            'months': MONTHS, 'month_names': MONTH_NAMES}

# ─── Auth routes ───────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        pw = request.form.get('password', '')
        if check_password_hash(ADMIN_PASSWORD_HASH, pw):
            session['authenticated'] = True
            session.permanent = True
            return redirect(request.args.get('next') or url_for('dashboard'))
        flash('Wrong password', 'error')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/health')
def health():
    return 'OK', 200

# ─── Helpers ───────────────────────────────────────────────────────────────────
def _month_order_sql(backend='sq'):
    """Inline CASE for ordering months."""
    return ("CASE month WHEN 'jan' THEN 1 WHEN 'feb' THEN 2 WHEN 'mar' THEN 3 "
            "WHEN 'apr' THEN 4 WHEN 'may' THEN 5 WHEN 'jun' THEN 6 "
            "WHEN 'jul' THEN 7 WHEN 'aug' THEN 8 WHEN 'sep' THEN 9 "
            "WHEN 'oct' THEN 10 WHEN 'nov' THEN 11 WHEN 'dec' THEN 12 END")

def get_client_full(client_id, year=2025):
    with get_db() as conn:
        conn.execute("SELECT * FROM clients WHERE id=?", (client_id,))
        client = conn.fetchone()
        if not client:
            return None
        conn.execute(
            "SELECT amount FROM old_balances WHERE client_id=? AND year=?",
            (client_id, year))
        old_bal = conn.fetchone()
        conn.execute(
            f"SELECT * FROM payments WHERE client_id=? AND year=? ORDER BY {_month_order_sql()}",
            (client_id, year))
        payments = conn.fetchall()

    payment_map   = {p['month']: dict(p) for p in payments}
    total_due     = sum(float(p['amount_due'])  for p in payments)
    total_paid    = sum(float(p['amount_paid']) for p in payments)
    total_balance = sum(float(p['balance'])     for p in payments)
    ob = float(old_bal['amount']) if old_bal else 0
    total_balance += ob

    return {
        'client': dict(client),
        'old_balance': ob,
        'payments': payment_map,
        'total_due': total_due,
        'total_paid': total_paid,
        'total_balance': total_balance,
    }

# ─── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/')
def dashboard():
    year = int(request.args.get('year', datetime.now().year))
    show_hidden = request.args.get('show_hidden') == '1'

    with get_db() as conn:
        if show_hidden:
            conn.execute("SELECT * FROM clients WHERE active=1 ORDER BY id")
        else:
            conn.execute("SELECT * FROM clients WHERE active=1 AND is_hidden=0 ORDER BY id")
        clients = conn.fetchall()

    summary = []
    total_due_all = total_paid_all = total_balance_all = 0

    for c in clients:
        with get_db() as conn:
            conn.execute(
                "SELECT amount FROM old_balances WHERE client_id=? AND year=?",
                (c['id'], year))
            old_bal = conn.fetchone()
            conn.execute(
                "SELECT COALESCE(SUM(amount_due),0) as due, "
                "       COALESCE(SUM(amount_paid),0) as paid, "
                "       COALESCE(SUM(balance),0) as bal "
                "FROM payments WHERE client_id=? AND year=?",
                (c['id'], year))
            stats = conn.fetchone()

        due  = float(stats['due'])
        paid = float(stats['paid'])
        bal  = float(stats['bal']) + (float(old_bal['amount']) if old_bal else 0)
        total_due_all     += due
        total_paid_all    += paid
        total_balance_all += bal
        summary.append({
            'id': c['id'], 'name': c['name'],
            'mobile': c['mobile'], 'room_no': c['room_no'],
            'is_hidden': c['is_hidden'],
            'due': due, 'paid': paid, 'balance': bal
        })

    return render_template('dashboard.html',
        summary=summary, year=year,
        total_due=total_due_all, total_paid=total_paid_all,
        total_balance=total_balance_all,
        show_hidden=show_hidden,
    )

# ─── Client detail ─────────────────────────────────────────────────────────────
@app.route('/client/<int:client_id>')
def client_detail(client_id):
    year = int(request.args.get('year', datetime.now().year))
    data = get_client_full(client_id, year)
    if not data:
        flash('Client not found', 'error')
        return redirect(url_for('dashboard'))
    return render_template('client_detail.html', data=data, year=year)

# ─── Add client ────────────────────────────────────────────────────────────────
@app.route('/client/add', methods=['GET', 'POST'])
def add_client():
    if request.method == 'POST':
        with get_db() as conn:
            conn.execute("SELECT COALESCE(MAX(id),0)+1 FROM clients")
            new_id = conn.fetchone()[0]
            conn.execute("""
                INSERT INTO clients (id, name, mobile, room_no, monthly_rent, notes)
                VALUES (?,?,?,?,?,?)
            """, (
                new_id,
                request.form['name'].strip().upper(),
                request.form.get('mobile','').strip(),
                request.form.get('room_no', ROOM_NAME).strip() or ROOM_NAME,
                float(request.form.get('monthly_rent', 525)),
                request.form.get('notes','').strip()
            ))
        flash(f'Client added — ID #{new_id}', 'success')
        return redirect(url_for('client_detail', client_id=new_id))
    return render_template('add_client.html', default_room=ROOM_NAME)

# ─── Edit client ───────────────────────────────────────────────────────────────
@app.route('/client/<int:client_id>/edit', methods=['GET', 'POST'])
def edit_client(client_id):
    with get_db() as conn:
        conn.execute("SELECT * FROM clients WHERE id=?", (client_id,))
        client = conn.fetchone()
    if not client:
        flash('Client not found', 'error')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        with get_db() as conn:
            conn.execute("""
                UPDATE clients SET name=?,mobile=?,room_no=?,monthly_rent=?,notes=?
                WHERE id=?
            """, (
                request.form['name'].strip().upper(),
                request.form.get('mobile','').strip(),
                request.form.get('room_no', ROOM_NAME).strip() or ROOM_NAME,
                float(request.form.get('monthly_rent', 525)),
                request.form.get('notes','').strip(),
                client_id
            ))
        flash('Client updated', 'success')
        return redirect(url_for('client_detail', client_id=client_id))
    return render_template('edit_client.html', client=dict(client))

# ─── Hide / Restore / Delete ──────────────────────────────────────────────────
@app.route('/client/<int:client_id>/hide', methods=['POST'])
def hide_client(client_id):
    with get_db() as conn:
        conn.execute("UPDATE clients SET is_hidden=1 WHERE id=?", (client_id,))
    flash('Client hidden from list', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/client/<int:client_id>/restore', methods=['POST'])
def restore_client(client_id):
    with get_db() as conn:
        conn.execute("UPDATE clients SET is_hidden=0 WHERE id=?", (client_id,))
    flash('Client restored', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/client/<int:client_id>/delete', methods=['POST'])
def delete_client(client_id):
    with get_db() as conn:
        conn.execute("DELETE FROM payments WHERE client_id=?", (client_id,))
        conn.execute("DELETE FROM old_balances WHERE client_id=?", (client_id,))
        conn.execute("DELETE FROM clients WHERE id=?", (client_id,))
    flash('Client permanently deleted', 'success')
    return redirect(url_for('dashboard'))

# ─── Record payment ────────────────────────────────────────────────────────────
@app.route('/payment/record', methods=['POST'])
def record_payment():
    client_id      = int(request.form['client_id'])
    year           = int(request.form['year'])
    month          = request.form['month']
    paid           = float(request.form['amount_paid'])
    due            = float(request.form.get('amount_due', 525))
    notes          = request.form.get('notes', '')
    paid_date      = request.form.get('paid_date', '') or datetime.now().strftime('%Y-%m-%d')
    payment_method = request.form.get('payment_method', 'cash')

    with get_db() as conn:
        conn.execute(
            "SELECT id, amount_paid, amount_due FROM payments "
            "WHERE client_id=? AND year=? AND month=?",
            (client_id, year, month))
        existing = conn.fetchone()

        if existing:
            new_paid = float(existing['amount_paid']) + paid
            new_due  = float(existing['amount_due'])
            balance  = new_due - new_paid
            conn.execute("""
                UPDATE payments
                SET amount_paid=?, balance=?, paid_date=?, payment_method=?, notes=?
                WHERE id=?
            """, (new_paid, balance, paid_date, payment_method, notes, existing['id']))
        else:
            balance = due - paid
            conn.execute("""
                INSERT INTO payments
                  (client_id,year,month,amount_due,amount_paid,balance,paid_date,payment_method,notes)
                VALUES (?,?,?,?,?,?,?,?,?)
            """, (client_id, year, month, due, paid, balance,
                  paid_date, payment_method, notes))

    flash(f'Payment of AED {paid:.0f} recorded for {MONTH_NAMES[month]} {year}', 'success')
    return redirect(url_for('client_detail', client_id=client_id, year=year))

# ─── Search ────────────────────────────────────────────────────────────────────
@app.route('/search')
def search():
    q = request.args.get('q', '').strip()
    results = []
    if q:
        with get_db() as conn:
            if q.isdigit():
                conn.execute(
                    "SELECT * FROM clients WHERE (id=? OR mobile LIKE ?) AND active=1 ORDER BY id",
                    (int(q), f'%{q}%'))
            else:
                conn.execute(
                    "SELECT * FROM clients WHERE name LIKE ? AND active=1 ORDER BY id",
                    (f'%{q.upper()}%',))
            results = [dict(r) for r in conn.fetchall()]
    return render_template('search.html', results=results, query=q)

# ─── Dues report ───────────────────────────────────────────────────────────────
@app.route('/dues')
def dues_report():
    year = int(request.args.get('year', datetime.now().year))
    with get_db() as conn:
        conn.execute("SELECT * FROM clients WHERE active=1 AND is_hidden=0 ORDER BY id")
        clients = conn.fetchall()
    dues = []
    for c in clients:
        with get_db() as conn:
            conn.execute(
                "SELECT amount FROM old_balances WHERE client_id=? AND year=?",
                (c['id'], year))
            old_bal = conn.fetchone()
            conn.execute(
                "SELECT COALESCE(SUM(balance),0) as bal FROM payments WHERE client_id=? AND year=?",
                (c['id'], year))
            stats = conn.fetchone()
        bal = float(stats['bal']) + (float(old_bal['amount']) if old_bal else 0)
        if bal > 0:
            dues.append({'id': c['id'], 'name': c['name'],
                         'mobile': c['mobile'], 'balance': bal})
    dues.sort(key=lambda x: x['balance'], reverse=True)
    return render_template('dues.html', dues=dues, year=year,
                           total=sum(d['balance'] for d in dues))

# ─── PDF Receipt ───────────────────────────────────────────────────────────────
@app.route('/client/<int:client_id>/receipt/<int:year>/<month>')
def generate_receipt(client_id, year, month):
    from pdf_generator import create_receipt_pdf
    data = get_client_full(client_id, year)
    if not data:
        flash('Client not found', 'error')
        return redirect(url_for('dashboard'))
    buf = create_receipt_pdf(data, year, month, MONTH_NAMES, ROOM_NAME)
    fname = (f"Receipt_{data['client']['name'].replace(' ','_')}"
             f"_{MONTH_NAMES[month]}_{year}.pdf")
    return send_file(io.BytesIO(buf), mimetype='application/pdf',
                     as_attachment=True, download_name=fname)

@app.route('/client/<int:client_id>/receipt-all/<int:year>')
def generate_full_statement(client_id, year):
    from pdf_generator import create_full_statement_pdf
    data = get_client_full(client_id, year)
    if not data:
        flash('Client not found', 'error')
        return redirect(url_for('dashboard'))
    buf = create_full_statement_pdf(data, year, MONTHS, MONTH_NAMES, ROOM_NAME)
    fname = f"Statement_{data['client']['name'].replace(' ','_')}_{year}.pdf"
    return send_file(io.BytesIO(buf), mimetype='application/pdf',
                     as_attachment=True, download_name=fname)

# ─── Import Excel data ─────────────────────────────────────────────────────────
@app.route('/admin/import', methods=['GET', 'POST'])
def import_excel():
    """Import or re-import data from Excel files."""
    message = None
    if request.method == 'POST':
        year = int(request.form.get('year', 2026))
        password = request.form.get('password', '9745437665')
        try:
            count = _do_import(year, password)
            message = ('success', f'✅ Imported {count} payment records for {year}')
        except Exception as e:
            message = ('error', f'Error: {e}')
    return render_template('import.html', message=message)

def _do_import(year, password='9745437665'):
    import msoffcrypto, openpyxl
    months = ['jan','feb','mar','apr','may','jun','jul','aug','sep','oct','nov','dec']
    fname = os.path.join(os.path.dirname(__file__), '..', f'ROOM RENT JAN TO DEC {year}.xlsx')
    if not os.path.exists(fname):
        raise FileNotFoundError(f'File not found: {fname}')

    with open(fname, 'rb') as f:
        office = msoffcrypto.OfficeFile(f)
        office.load_key(password=password)
        dec = io.BytesIO()
        office.decrypt(dec)
    dec.seek(0)
    wb = openpyxl.load_workbook(dec, data_only=True)
    rent_ws = wb['Rent']
    paid_ws = wb['Paid']

    paid_lookup = {}
    for row in paid_ws.iter_rows(min_row=5, max_row=paid_ws.max_row, values_only=True):
        no = row[1]
        if no is None: continue
        paid_lookup[no] = {'old_bal': row[3] or 0, 'months': list(row[4:16])}

    # Clear existing data for the year
    with get_db() as conn:
        conn.execute("DELETE FROM payments WHERE year=?", (year,))
        conn.execute("DELETE FROM old_balances WHERE year=?", (year,))

    count = 0
    for row in rent_ws.iter_rows(min_row=5, max_row=rent_ws.max_row, values_only=True):
        no   = row[1]
        name = row[2]
        if no is None or name is None or str(name).startswith('='): continue
        name = str(name).strip()
        if name in ('', 'A'): continue

        old_due  = row[3] or 0
        mon_dues = list(row[4:16])

        # Upsert client
        with get_db() as conn:
            conn.execute("SELECT id, name FROM clients WHERE id=?", (no,))
            existing = conn.fetchone()
        if not existing:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO clients (id, name, monthly_rent, room_no) VALUES (?,?,525,?)",
                    (no, name, ROOM_NAME))
        elif existing['name'].strip() in ('A', ''):
            with get_db() as conn:
                conn.execute("UPDATE clients SET name=? WHERE id=?", (name, no))

        # Old balance
        paid_old = paid_lookup.get(no, {}).get('old_bal', 0)
        ob_net   = old_due - paid_old
        if old_due != 0 or paid_old != 0:
            with get_db() as conn:
                conn.execute(
                    "INSERT INTO old_balances (client_id, year, amount) VALUES (?,?,?) "
                    "ON CONFLICT(client_id) DO UPDATE SET amount=EXCLUDED.amount, year=EXCLUDED.year"
                    if os.environ.get('DATABASE_URL') else
                    "INSERT OR REPLACE INTO old_balances (client_id, year, amount) VALUES (?,?,?)",
                    (no, year, ob_net))

        # Monthly payments
        paid_months = paid_lookup.get(no, {}).get('months', [None]*12)
        for i, month in enumerate(months):
            due  = mon_dues[i] or 0
            paid = paid_months[i] or 0
            if due == 0 and paid == 0: continue
            with get_db() as conn:
                conn.execute("""
                    INSERT INTO payments (client_id,year,month,amount_due,amount_paid,balance)
                    VALUES (?,?,?,?,?,?)
                """, (no, year, month, due, paid, due - paid))
            count += 1

    return count

# ─── Backup / export ───────────────────────────────────────────────────────────
@app.route('/admin/backup')
def backup():
    with get_db() as conn:
        conn.execute("SELECT * FROM clients ORDER BY id")
        clients = conn.fetchall()
    return render_template('backup.html', clients=clients)

# ─── Startup ───────────────────────────────────────────────────────────────────
def create_app():
    os.makedirs(os.path.join(os.path.dirname(__file__), 'data'), exist_ok=True)
    init_schema()
    return app

if __name__ == '__main__':
    create_app()
    print(f"🏠 Room 33 — Rent Manager  →  http://localhost:8080")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)), debug=False)
