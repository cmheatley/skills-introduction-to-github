import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, g
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'lib-order-sys-change-in-prod')

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'instance', 'library.db')


def get_db():
    if 'db' not in g:
        os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
        g.db = sqlite3.connect(DATABASE)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def _migrate_db():
    if not os.path.exists(DATABASE):
        return
    conn = sqlite3.connect(DATABASE)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(orders)")]
    if 'resource_type' not in cols:
        conn.execute("ALTER TABLE orders ADD COLUMN resource_type TEXT NOT NULL DEFAULT 'New'")
        conn.commit()
    conn.close()


_migrate_db()


@app.teardown_appcontext
def close_db(e=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def role_required(*roles):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if 'user_id' not in session:
                return redirect(url_for('login'))
            if session.get('role') not in roles:
                flash('You do not have permission to access this page.', 'error')
                return redirect(url_for('orders_summary'))
            return f(*args, **kwargs)
        return decorated
    return decorator


# ── AUTH ─────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('orders_summary') if 'user_id' in session else url_for('login'))


@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('orders_summary'))
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        db = get_db()
        user = db.execute(
            'SELECT * FROM users WHERE username=? AND active=1', (username,)
        ).fetchone()
        if user and check_password_hash(user['password_hash'], password):
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            session['full_name'] = f"{user['first_name']} {user['last_name']}"
            return redirect(url_for('orders_summary'))
        flash('Invalid username or password.', 'error')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# ── ORDERS ────────────────────────────────────────────────────────────────────

@app.route('/orders')
@login_required
def orders_summary():
    db = get_db()
    status_filter = request.args.get('status', 'NEW')
    year_filter = request.args.get('year', 'current')

    fiscal_years = db.execute(
        'SELECT * FROM fiscal_years ORDER BY start_date DESC'
    ).fetchall()
    today = date.today().isoformat()
    current_year = db.execute(
        'SELECT * FROM fiscal_years WHERE start_date<=? AND end_date>=? LIMIT 1',
        (today, today)
    ).fetchone()

    conditions, params = [], []
    if status_filter != 'ALL':
        conditions.append('o.status=?')
        params.append(status_filter)

    if year_filter == 'current' and current_year:
        conditions.append('o.fiscal_year_id=?')
        params.append(current_year['id'])
    elif year_filter not in ('current', 'all'):
        conditions.append('o.fiscal_year_id=?')
        params.append(year_filter)

    where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

    orders = db.execute(f'''
        SELECT o.*,
               u1.first_name||' '||u1.last_name AS librarian_name,
               u2.first_name||' '||u2.last_name AS acq_tech_name,
               u3.first_name||' '||u3.last_name AS cat_name,
               dst.name AS destination_name,
               dept.name AS department_name,
               p.name AS program_name,
               fy.label AS fiscal_year_label,
               (SELECT COUNT(*) FROM order_items WHERE order_id=o.id) AS item_count
        FROM orders o
        LEFT JOIN users u1 ON o.librarian_id=u1.id
        LEFT JOIN users u2 ON o.acquisition_tech_id=u2.id
        LEFT JOIN users u3 ON o.cataloging_personnel_id=u3.id
        LEFT JOIN destinations dst ON o.destination_id=dst.id
        LEFT JOIN departments dept ON o.department_id=dept.id
        LEFT JOIN programs p ON o.program_id=p.id
        LEFT JOIN fiscal_years fy ON o.fiscal_year_id=fy.id
        {where}
        ORDER BY o.request_date DESC, o.id DESC
    ''', params).fetchall()

    order_alerts = {}
    for o in orders:
        alerts = []
        if db.execute(
            'SELECT 1 FROM course_reserves WHERE order_id=? AND is_course_reserve=1', (o['id'],)
        ).fetchone():
            alerts.append('course_reserve')
        if db.execute(
            'SELECT 1 FROM faculty_requests WHERE order_id=? AND (notify_faculty=1 OR preview_item=1 OR hold_item=1)',
            (o['id'],)
        ).fetchone():
            alerts.append('faculty')
        order_alerts[o['id']] = alerts

    return render_template(
        'orders/summary.html',
        orders=orders,
        status_filter=status_filter,
        year_filter=year_filter,
        fiscal_years=fiscal_years,
        current_year=current_year,
        order_alerts=order_alerts,
    )


@app.route('/orders/new', methods=['GET', 'POST'])
@login_required
def order_new():
    db = get_db()
    if request.method == 'POST':
        today = date.today().isoformat()
        current_year = db.execute(
            'SELECT * FROM fiscal_years WHERE start_date<=? AND end_date>=? LIMIT 1',
            (today, today)
        ).fetchone()
        fy_id = current_year['id'] if current_year else None

        cur = db.execute('''
            INSERT INTO orders
              (status, resource_type, request_date, librarian_id, acquisition_tech_id,
               cataloging_personnel_id, destination_id, department_id, program_id, fiscal_year_id)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        ''', (
            'NEW',
            request.form.get('resource_type', 'New'),
            request.form.get('request_date', today),
            request.form.get('librarian_id') or None,
            request.form.get('acquisition_tech_id') or None,
            request.form.get('cataloging_personnel_id') or None,
            request.form.get('destination_id') or None,
            request.form.get('department_id') or None,
            request.form.get('program_id') or None,
            fy_id,
        ))
        order_id = cur.lastrowid

        faculty_name = request.form.get('faculty_name', '').strip()
        db.execute('''
            INSERT INTO faculty_requests
              (order_id, faculty_name, faculty_email, faculty_phone,
               notify_faculty, preview_item, hold_item)
            VALUES (?,?,?,?,?,?,?)
        ''', (
            order_id, faculty_name,
            request.form.get('faculty_email', ''),
            request.form.get('faculty_phone', ''),
            1 if request.form.get('notify_faculty') else 0,
            1 if request.form.get('preview_item') else 0,
            1 if request.form.get('hold_item') else 0,
        ))

        is_cr = 1 if request.form.get('course_reserve') == 'yes' else 0
        db.execute('''
            INSERT INTO course_reserves (order_id, is_course_reserve, course_name, course_number)
            VALUES (?,?,?,?)
        ''', (
            order_id, is_cr,
            request.form.get('course_name', '') if is_cr else '',
            request.form.get('course_number', '') if is_cr else '',
        ))

        title = request.form.get('title', '').strip()
        if title:
            db.execute('''
                INSERT INTO order_items
                  (order_id, title, material_type_id, quantity, vendor_id,
                   source_url, requestor_notes, item_status)
                VALUES (?,?,?,?,?,?,?,?)
            ''', (
                order_id, title,
                request.form.get('material_type_id') or None,
                int(request.form.get('quantity', 1)),
                request.form.get('vendor_id') or None,
                request.form.get('source_url', ''),
                request.form.get('requestor_notes', ''),
                'Not Yet Ordered',
            ))

        db.commit()
        flash('Order created successfully!', 'success')
        return redirect(url_for('order_detail', order_id=order_id))

    users = db.execute(
        'SELECT * FROM users WHERE active=1 ORDER BY last_name, first_name'
    ).fetchall()
    destinations = db.execute('SELECT * FROM destinations ORDER BY name').fetchall()
    departments = db.execute('SELECT * FROM departments ORDER BY name').fetchall()
    programs = db.execute('SELECT * FROM programs ORDER BY name').fetchall()
    vendors = db.execute('SELECT * FROM vendors WHERE active=1 ORDER BY name').fetchall()
    material_types = db.execute('SELECT * FROM material_types ORDER BY name').fetchall()

    return render_template(
        'orders/form.html',
        users=users,
        destinations=destinations,
        departments=departments,
        programs=programs,
        vendors=vendors,
        material_types=material_types,
        today=date.today().isoformat(),
    )


@app.route('/orders/<int:order_id>')
@login_required
def order_detail(order_id):
    db = get_db()
    order = db.execute('''
        SELECT o.*,
               u1.first_name||' '||u1.last_name AS librarian_name,
               u2.first_name||' '||u2.last_name AS acq_tech_name,
               u3.first_name||' '||u3.last_name AS cat_name,
               dst.name AS destination_name,
               dept.name AS department_name,
               p.name AS program_name
        FROM orders o
        LEFT JOIN users u1 ON o.librarian_id=u1.id
        LEFT JOIN users u2 ON o.acquisition_tech_id=u2.id
        LEFT JOIN users u3 ON o.cataloging_personnel_id=u3.id
        LEFT JOIN destinations dst ON o.destination_id=dst.id
        LEFT JOIN departments dept ON o.department_id=dept.id
        LEFT JOIN programs p ON o.program_id=p.id
        WHERE o.id=?
    ''', (order_id,)).fetchone()

    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('orders_summary'))

    items = db.execute('''
        SELECT oi.*, mt.name AS material_type_name, v.name AS vendor_name
        FROM order_items oi
        LEFT JOIN material_types mt ON oi.material_type_id=mt.id
        LEFT JOIN vendors v ON oi.vendor_id=v.id
        WHERE oi.order_id=?
        ORDER BY oi.id
    ''', (order_id,)).fetchall()

    faculty_request = db.execute(
        'SELECT * FROM faculty_requests WHERE order_id=?', (order_id,)
    ).fetchone()
    course_reserve = db.execute(
        'SELECT * FROM course_reserves WHERE order_id=?', (order_id,)
    ).fetchone()

    budget = None
    if order['department_id']:
        today = date.today().isoformat()
        fy = db.execute(
            'SELECT * FROM fiscal_years WHERE start_date<=? AND end_date>=? LIMIT 1',
            (today, today)
        ).fetchone()
        if fy:
            row = db.execute(
                'SELECT * FROM department_budgets WHERE department_id=? AND fiscal_year_id=?',
                (order['department_id'], fy['id'])
            ).fetchone()
            spent = db.execute('''
                SELECT COALESCE(SUM(oi.item_amount * oi.quantity),0) AS s
                FROM order_items oi JOIN orders o ON oi.order_id=o.id
                WHERE o.department_id=? AND o.fiscal_year_id=? AND o.status!='CANCELLED'
            ''', (order['department_id'], fy['id'])).fetchone()['s']
            allocated = row['amount_allocated'] if row else 0.0
            budget = {'allocated': allocated, 'spent': spent, 'remaining': allocated - spent}

    return render_template(
        'orders/detail.html',
        order=order, items=items,
        faculty_request=faculty_request,
        course_reserve=course_reserve,
        budget=budget,
    )


@app.route('/orders/<int:order_id>/edit', methods=['GET', 'POST'])
@login_required
def order_edit(order_id):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('orders_summary'))

    if request.method == 'POST':
        db.execute('''
            UPDATE orders SET status=?, resource_type=?, request_date=?, librarian_id=?,
              acquisition_tech_id=?, cataloging_personnel_id=?,
              destination_id=?, department_id=?, program_id=?, date_fulfilled=?
            WHERE id=?
        ''', (
            request.form.get('status'),
            request.form.get('resource_type', 'New'),
            request.form.get('request_date'),
            request.form.get('librarian_id') or None,
            request.form.get('acquisition_tech_id') or None,
            request.form.get('cataloging_personnel_id') or None,
            request.form.get('destination_id') or None,
            request.form.get('department_id') or None,
            request.form.get('program_id') or None,
            request.form.get('date_fulfilled') or None,
            order_id,
        ))

        db.execute('''
            UPDATE faculty_requests SET faculty_name=?, faculty_email=?, faculty_phone=?,
              notify_faculty=?, preview_item=?, hold_item=?
            WHERE order_id=?
        ''', (
            request.form.get('faculty_name', '').strip(),
            request.form.get('faculty_email', ''),
            request.form.get('faculty_phone', ''),
            1 if request.form.get('notify_faculty') else 0,
            1 if request.form.get('preview_item') else 0,
            1 if request.form.get('hold_item') else 0,
            order_id,
        ))

        is_cr = 1 if request.form.get('course_reserve') == 'yes' else 0
        db.execute('''
            UPDATE course_reserves SET is_course_reserve=?, course_name=?, course_number=?
            WHERE order_id=?
        ''', (
            is_cr,
            request.form.get('course_name', '') if is_cr else '',
            request.form.get('course_number', '') if is_cr else '',
            order_id,
        ))

        db.commit()
        flash('Order updated successfully!', 'success')
        return redirect(url_for('order_detail', order_id=order_id))

    faculty_request = db.execute(
        'SELECT * FROM faculty_requests WHERE order_id=?', (order_id,)
    ).fetchone()
    course_reserve = db.execute(
        'SELECT * FROM course_reserves WHERE order_id=?', (order_id,)
    ).fetchone()
    users = db.execute(
        'SELECT * FROM users WHERE active=1 ORDER BY last_name, first_name'
    ).fetchall()
    destinations = db.execute('SELECT * FROM destinations ORDER BY name').fetchall()
    departments = db.execute('SELECT * FROM departments ORDER BY name').fetchall()
    programs = db.execute('SELECT * FROM programs ORDER BY name').fetchall()

    return render_template(
        'orders/edit.html',
        order=order,
        faculty_request=faculty_request,
        course_reserve=course_reserve,
        users=users,
        destinations=destinations,
        departments=departments,
        programs=programs,
    )


@app.route('/orders/<int:order_id>/delete', methods=['POST'])
@login_required
@role_required('admin', 'librarian')
def order_delete(order_id):
    db = get_db()
    db.execute('DELETE FROM orders WHERE id=?', (order_id,))
    db.commit()
    flash('Order deleted.', 'success')
    return redirect(url_for('orders_summary'))


@app.route('/orders/<int:order_id>/items/new', methods=['GET', 'POST'])
@login_required
def item_new(order_id):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('orders_summary'))

    if request.method == 'POST':
        db.execute('''
            INSERT INTO order_items
              (order_id, title, material_type_id, quantity, vendor_id, source_url,
               requestor_notes, po_num, item_amount, date_ordered, date_received,
               date_catalogued, tech_notes, item_status)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ''', (
            order_id,
            request.form.get('title'),
            request.form.get('material_type_id') or None,
            int(request.form.get('quantity', 1)),
            request.form.get('vendor_id') or None,
            request.form.get('source_url', ''),
            request.form.get('requestor_notes', ''),
            request.form.get('po_num', '') or None,
            float(request.form.get('item_amount', 0) or 0),
            request.form.get('date_ordered') or None,
            request.form.get('date_received') or None,
            request.form.get('date_catalogued') or None,
            request.form.get('tech_notes', ''),
            request.form.get('item_status', 'Not Yet Ordered'),
        ))
        _recalc_total(db, order_id)
        db.commit()
        flash('Item added successfully!', 'success')
        return redirect(url_for('order_detail', order_id=order_id))

    vendors = db.execute('SELECT * FROM vendors WHERE active=1 ORDER BY name').fetchall()
    material_types = db.execute('SELECT * FROM material_types ORDER BY name').fetchall()
    return render_template(
        'orders/item_form.html',
        order=order, item=None,
        vendors=vendors, material_types=material_types,
    )


@app.route('/orders/<int:order_id>/items/<int:item_id>/edit', methods=['GET', 'POST'])
@login_required
def item_edit(order_id, item_id):
    db = get_db()
    order = db.execute('SELECT * FROM orders WHERE id=?', (order_id,)).fetchone()
    item = db.execute(
        'SELECT * FROM order_items WHERE id=? AND order_id=?', (item_id, order_id)
    ).fetchone()
    if not order or not item:
        flash('Not found.', 'error')
        return redirect(url_for('orders_summary'))

    if request.method == 'POST':
        db.execute('''
            UPDATE order_items SET title=?, material_type_id=?, quantity=?, vendor_id=?,
              source_url=?, requestor_notes=?, po_num=?, item_amount=?,
              date_ordered=?, date_received=?, date_catalogued=?, tech_notes=?, item_status=?
            WHERE id=? AND order_id=?
        ''', (
            request.form.get('title'),
            request.form.get('material_type_id') or None,
            int(request.form.get('quantity', 1)),
            request.form.get('vendor_id') or None,
            request.form.get('source_url', ''),
            request.form.get('requestor_notes', ''),
            request.form.get('po_num', '') or None,
            float(request.form.get('item_amount', 0) or 0),
            request.form.get('date_ordered') or None,
            request.form.get('date_received') or None,
            request.form.get('date_catalogued') or None,
            request.form.get('tech_notes', ''),
            request.form.get('item_status', 'Not Yet Ordered'),
            item_id, order_id,
        ))
        _recalc_total(db, order_id)
        db.commit()
        flash('Item updated successfully!', 'success')
        return redirect(url_for('order_detail', order_id=order_id))

    vendors = db.execute('SELECT * FROM vendors WHERE active=1 ORDER BY name').fetchall()
    material_types = db.execute('SELECT * FROM material_types ORDER BY name').fetchall()
    return render_template(
        'orders/item_form.html',
        order=order, item=item,
        vendors=vendors, material_types=material_types,
    )


@app.route('/orders/<int:order_id>/items/<int:item_id>/delete', methods=['POST'])
@login_required
def item_delete(order_id, item_id):
    db = get_db()
    db.execute('DELETE FROM order_items WHERE id=? AND order_id=?', (item_id, order_id))
    _recalc_total(db, order_id)
    db.commit()
    flash('Item deleted.', 'success')
    return redirect(url_for('order_detail', order_id=order_id))


def _recalc_total(db, order_id):
    db.execute('''
        UPDATE orders SET order_total=(
            SELECT COALESCE(SUM(item_amount*quantity),0)
            FROM order_items WHERE order_id=?
        ) WHERE id=?
    ''', (order_id, order_id))


# ── FINANCIALS ────────────────────────────────────────────────────────────────

@app.route('/financials/budget')
@login_required
def budget():
    db = get_db()
    budget_type = request.args.get('type', 'department')
    year_filter = request.args.get('year', 'current')

    fiscal_years = db.execute(
        'SELECT * FROM fiscal_years ORDER BY start_date DESC'
    ).fetchall()
    today = date.today().isoformat()
    current_year = db.execute(
        'SELECT * FROM fiscal_years WHERE start_date<=? AND end_date>=? LIMIT 1',
        (today, today)
    ).fetchone()

    if year_filter == 'current':
        fy = current_year
    elif year_filter == 'all':
        fy = current_year
    else:
        fy = db.execute('SELECT * FROM fiscal_years WHERE id=?', (year_filter,)).fetchone()

    budget_data = []
    total_allocated = total_spent = 0.0

    if budget_type == 'department':
        rows = db.execute('SELECT * FROM departments ORDER BY name').fetchall()
        for row in rows:
            br = db.execute(
                'SELECT * FROM department_budgets WHERE department_id=? AND fiscal_year_id=?',
                (row['id'], fy['id'] if fy else 0)
            ).fetchone() if fy else None
            spent = db.execute('''
                SELECT COALESCE(SUM(oi.item_amount*oi.quantity),0) AS s
                FROM order_items oi JOIN orders o ON oi.order_id=o.id
                WHERE o.department_id=? AND o.fiscal_year_id=? AND o.status!='CANCELLED'
            ''', (row['id'], fy['id'] if fy else 0)).fetchone()['s'] if fy else 0.0
            allocated = br['amount_allocated'] if br else 0.0
            effective = br['effective_date'] if br else (fy['start_date'] if fy else '')
            total_allocated += allocated
            total_spent += spent
            budget_data.append({
                'entity': row, 'entity_type': 'department',
                'allocated': allocated, 'spent': spent,
                'remaining': allocated - spent,
                'effective_date': effective,
                'budget_id': br['id'] if br else None,
            })
    else:
        rows = db.execute('SELECT * FROM vendors WHERE active=1 ORDER BY name').fetchall()
        for row in rows:
            br = db.execute(
                'SELECT * FROM vendor_budgets WHERE vendor_id=? AND fiscal_year_id=?',
                (row['id'], fy['id'] if fy else 0)
            ).fetchone() if fy else None
            spent = db.execute('''
                SELECT COALESCE(SUM(oi.item_amount*oi.quantity),0) AS s
                FROM order_items oi JOIN orders o ON oi.order_id=o.id
                WHERE oi.vendor_id=? AND o.fiscal_year_id=? AND o.status!='CANCELLED'
            ''', (row['id'], fy['id'] if fy else 0)).fetchone()['s'] if fy else 0.0
            allocated = br['amount_allocated'] if br else 0.0
            effective = br['effective_date'] if br else (fy['start_date'] if fy else '')
            total_allocated += allocated
            total_spent += spent
            budget_data.append({
                'entity': row, 'entity_type': 'vendor',
                'allocated': allocated, 'spent': spent,
                'remaining': allocated - spent,
                'effective_date': effective,
                'budget_id': br['id'] if br else None,
            })

    return render_template(
        'financials/budget.html',
        budget_type=budget_type,
        budget_data=budget_data,
        fiscal_years=fiscal_years,
        current_year=current_year,
        selected_year=fy,
        year_filter=year_filter,
        total_allocated=total_allocated,
        total_spent=total_spent,
        total_remaining=total_allocated - total_spent,
    )


@app.route('/financials/budget/update', methods=['POST'])
@login_required
@role_required('admin', 'librarian')
def budget_update():
    db = get_db()
    budget_type = request.form.get('budget_type', 'department')
    fy_id = request.form.get('fiscal_year_id')
    amount = float(request.form.get('amount', 0) or 0)
    effective_date = request.form.get('effective_date', date.today().isoformat())

    if budget_type == 'department':
        entity_id = request.form.get('department_id')
        existing = db.execute(
            'SELECT id FROM department_budgets WHERE department_id=? AND fiscal_year_id=?',
            (entity_id, fy_id)
        ).fetchone()
        if existing:
            db.execute(
                'UPDATE department_budgets SET amount_allocated=?, effective_date=? WHERE id=?',
                (amount, effective_date, existing['id'])
            )
        else:
            db.execute(
                'INSERT INTO department_budgets (fiscal_year_id, department_id, amount_allocated, effective_date) VALUES (?,?,?,?)',
                (fy_id, entity_id, amount, effective_date)
            )
    else:
        entity_id = request.form.get('vendor_id')
        existing = db.execute(
            'SELECT id FROM vendor_budgets WHERE vendor_id=? AND fiscal_year_id=?',
            (entity_id, fy_id)
        ).fetchone()
        if existing:
            db.execute(
                'UPDATE vendor_budgets SET amount_allocated=?, effective_date=? WHERE id=?',
                (amount, effective_date, existing['id'])
            )
        else:
            db.execute(
                'INSERT INTO vendor_budgets (fiscal_year_id, vendor_id, amount_allocated, effective_date) VALUES (?,?,?,?)',
                (fy_id, entity_id, amount, effective_date)
            )

    db.commit()
    flash('Budget updated successfully!', 'success')
    return redirect(url_for('budget', type=budget_type))


# ── API ───────────────────────────────────────────────────────────────────────

@app.route('/api/departments/<int:destination_id>')
@login_required
def api_departments(destination_id):
    db = get_db()
    rows = db.execute(
        'SELECT * FROM departments WHERE destination_id=? ORDER BY name', (destination_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route('/api/programs/<int:department_id>')
@login_required
def api_programs(department_id):
    db = get_db()
    rows = db.execute(
        'SELECT * FROM programs WHERE department_id=? ORDER BY name', (department_id,)
    ).fetchall()
    return jsonify([dict(r) for r in rows])


# ── ADMIN ─────────────────────────────────────────────────────────────────────

@app.route('/admin')
@login_required
@role_required('admin')
def admin():
    return redirect(url_for('admin_users'))


@app.route('/admin/users')
@login_required
@role_required('admin')
def admin_users():
    db = get_db()
    users = db.execute('SELECT * FROM users ORDER BY last_name, first_name').fetchall()
    return render_template('admin/users.html', users=users)


@app.route('/admin/users/new', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_user_new():
    if request.method == 'POST':
        db = get_db()
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        if not username or not password:
            flash('Username and password are required.', 'error')
            return render_template('admin/user_form.html', user=None)
        if db.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            flash('Username already exists.', 'error')
            return render_template('admin/user_form.html', user=None)
        db.execute('''
            INSERT INTO users (username, password_hash, first_name, last_name, email, role, active)
            VALUES (?,?,?,?,?,?,1)
        ''', (
            username,
            generate_password_hash(password),
            request.form.get('first_name', '').strip(),
            request.form.get('last_name', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('role', 'librarian'),
        ))
        db.commit()
        flash('User created successfully!', 'success')
        return redirect(url_for('admin_users'))
    return render_template('admin/user_form.html', user=None)


@app.route('/admin/users/<int:user_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required('admin')
def admin_user_edit(user_id):
    db = get_db()
    user = db.execute('SELECT * FROM users WHERE id=?', (user_id,)).fetchone()
    if not user:
        flash('User not found.', 'error')
        return redirect(url_for('admin_users'))

    if request.method == 'POST':
        db.execute('''
            UPDATE users SET first_name=?, last_name=?, email=?, role=?, active=?
            WHERE id=?
        ''', (
            request.form.get('first_name', '').strip(),
            request.form.get('last_name', '').strip(),
            request.form.get('email', '').strip(),
            request.form.get('role', 'librarian'),
            1 if request.form.get('active') else 0,
            user_id,
        ))
        new_pw = request.form.get('password', '').strip()
        if new_pw:
            db.execute(
                'UPDATE users SET password_hash=? WHERE id=?',
                (generate_password_hash(new_pw), user_id)
            )
        db.commit()
        flash('User updated successfully!', 'success')
        return redirect(url_for('admin_users'))

    return render_template('admin/user_form.html', user=user)


@app.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_user_delete(user_id):
    if user_id == session.get('user_id'):
        flash('You cannot deactivate your own account.', 'error')
        return redirect(url_for('admin_users'))
    db = get_db()
    db.execute('UPDATE users SET active=0 WHERE id=?', (user_id,))
    db.commit()
    flash('User deactivated.', 'success')
    return redirect(url_for('admin_users'))


@app.route('/admin/manage')
@login_required
@role_required('admin')
def admin_manage():
    db = get_db()
    return render_template(
        'admin/manage.html',
        destinations=db.execute('SELECT * FROM destinations ORDER BY name').fetchall(),
        departments=db.execute('''
            SELECT d.*, dst.name AS destination_name
            FROM departments d LEFT JOIN destinations dst ON d.destination_id=dst.id
            ORDER BY d.name
        ''').fetchall(),
        programs=db.execute('''
            SELECT p.*, d.name AS department_name
            FROM programs p LEFT JOIN departments d ON p.department_id=d.id
            ORDER BY p.name
        ''').fetchall(),
        vendors=db.execute('SELECT * FROM vendors ORDER BY name').fetchall(),
        material_types=db.execute('SELECT * FROM material_types ORDER BY name').fetchall(),
        fiscal_years=db.execute(
            'SELECT * FROM fiscal_years ORDER BY start_date DESC'
        ).fetchall(),
    )


# Reference-data CRUD helpers
def _ref_add(table, redirect_to, **fields):
    db = get_db()
    cols = ', '.join(fields.keys())
    placeholders = ', '.join('?' for _ in fields)
    try:
        db.execute(f'INSERT INTO {table} ({cols}) VALUES ({placeholders})', list(fields.values()))
        db.commit()
        flash(f'Added successfully.', 'success')
    except sqlite3.IntegrityError:
        flash('That entry already exists.', 'error')
    return redirect(url_for(redirect_to))


@app.route('/admin/destinations/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_destination_add():
    name = request.form.get('name', '').strip()
    if name:
        return _ref_add('destinations', 'admin_manage', name=name)
    return redirect(url_for('admin_manage'))


@app.route('/admin/destinations/<int:did>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_destination_delete(did):
    db = get_db()
    db.execute('DELETE FROM destinations WHERE id=?', (did,))
    db.commit()
    flash('Destination deleted.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/departments/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_department_add():
    name = request.form.get('name', '').strip()
    dst = request.form.get('destination_id') or None
    if name:
        db = get_db()
        db.execute('INSERT INTO departments (name, destination_id) VALUES (?,?)', (name, dst))
        db.commit()
        flash('Department added.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/departments/<int:did>/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_department_edit(did):
    db = get_db()
    name = request.form.get('name', '').strip()
    dst = request.form.get('destination_id') or None
    if name:
        db.execute('UPDATE departments SET name=?, destination_id=? WHERE id=?', (name, dst, did))
        db.commit()
        flash('Department updated.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/departments/<int:did>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_department_delete(did):
    db = get_db()
    db.execute('DELETE FROM departments WHERE id=?', (did,))
    db.commit()
    flash('Department deleted.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/programs/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_program_add():
    name = request.form.get('name', '').strip()
    dept = request.form.get('department_id') or None
    if name:
        db = get_db()
        db.execute('INSERT INTO programs (name, department_id) VALUES (?,?)', (name, dept))
        db.commit()
        flash('Program added.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/programs/<int:pid>/edit', methods=['POST'])
@login_required
@role_required('admin')
def admin_program_edit(pid):
    db = get_db()
    name = request.form.get('name', '').strip()
    dept = request.form.get('department_id') or None
    if name:
        db.execute('UPDATE programs SET name=?, department_id=? WHERE id=?', (name, dept, pid))
        db.commit()
        flash('Program updated.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/programs/<int:pid>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_program_delete(pid):
    db = get_db()
    db.execute('DELETE FROM programs WHERE id=?', (pid,))
    db.commit()
    flash('Program deleted.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/vendors/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_vendor_add():
    name = request.form.get('name', '').strip()
    if name:
        return _ref_add('vendors', 'admin_manage', name=name, active=1)
    return redirect(url_for('admin_manage'))


@app.route('/admin/vendors/<int:vid>/toggle', methods=['POST'])
@login_required
@role_required('admin')
def admin_vendor_toggle(vid):
    db = get_db()
    db.execute('UPDATE vendors SET active = 1 - active WHERE id=?', (vid,))
    db.commit()
    flash('Vendor status toggled.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/vendors/<int:vid>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_vendor_delete(vid):
    db = get_db()
    db.execute('DELETE FROM vendors WHERE id=?', (vid,))
    db.commit()
    flash('Vendor deleted.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/material-types/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_material_type_add():
    name = request.form.get('name', '').strip()
    if name:
        return _ref_add('material_types', 'admin_manage', name=name)
    return redirect(url_for('admin_manage'))


@app.route('/admin/material-types/<int:mid>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_material_type_delete(mid):
    db = get_db()
    db.execute('DELETE FROM material_types WHERE id=?', (mid,))
    db.commit()
    flash('Material type deleted.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/fiscal-years/add', methods=['POST'])
@login_required
@role_required('admin')
def admin_fiscal_year_add():
    label = request.form.get('label', '').strip()
    start = request.form.get('start_date', '')
    end = request.form.get('end_date', '')
    if label and start and end:
        db = get_db()
        db.execute(
            'INSERT INTO fiscal_years (label, start_date, end_date) VALUES (?,?,?)',
            (label, start, end)
        )
        db.commit()
        flash('Fiscal year added.', 'success')
    return redirect(url_for('admin_manage'))


@app.route('/admin/fiscal-years/<int:fid>/delete', methods=['POST'])
@login_required
@role_required('admin')
def admin_fiscal_year_delete(fid):
    db = get_db()
    db.execute('DELETE FROM fiscal_years WHERE id=?', (fid,))
    db.commit()
    flash('Fiscal year deleted.', 'success')
    return redirect(url_for('admin_manage'))


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
