from flask import render_template, request, redirect, url_for, session, jsonify
from app import app
from app.database import get_db_connection
import json
from datetime import date, datetime

# ── HOME ──
@app.route('/')
def home():
    if 'user_id' in session:
        return redirect(url_for('admin_dashboard' if session['role'] == 'admin' else 'user_dashboard'))
    return redirect(url_for('login'))

# ── AUTH ──
@app.route('/login', methods=['GET', 'POST'])
def login():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password)).fetchone()
        conn.close()
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['role'] = user['role']
            return redirect(url_for('admin_dashboard' if user['role'] == 'admin' else 'user_dashboard'))
        else:
            error = "Invalid username or password. Please try again."
    return render_template('login.html', error=error)

@app.route('/register', methods=['GET', 'POST'])
def register():
    error = None
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        try:
            conn = get_db_connection()
            conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, 'user'))
            conn.commit()
            conn.close()
            return redirect(url_for('login'))
        except:
            error = "Username already taken. Please choose another."
    return render_template('register.html', error=error)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ── USER ──
@app.route('/dashboard')
def user_dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    buses = [dict(row) for row in conn.execute("SELECT * FROM buses").fetchall()]
    conn.close()
    return render_template('user.html', buses=buses, user=session['username'])

@app.route('/my-bookings')
def my_bookings():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    bookings_list = conn.execute(
        '''SELECT bookings.id,
                  COALESCE(buses.name,  'Bus (removed)') AS name,
                  COALESCE(buses.route, '—')             AS route,
                  bookings.bus_id,
                  bookings.seat_numbers,
                  bookings.total_price,
                  bookings.date,
                  COALESCE(bookings.dep_time, buses.dep_time, '08:00') AS dep_time,
                  COALESCE(bookings.arr_time, buses.arr_time, '14:00') AS arr_time
           FROM bookings
           LEFT JOIN buses ON bookings.bus_id = buses.id
           WHERE bookings.user_id = ?
           ORDER BY bookings.id DESC''',
        (session['user_id'],)
    ).fetchall()

    # Fetch all pending/decided requests for this user so the UI can show badges
    requests_list = conn.execute(
        '''SELECT id, booking_id, request_type, status, admin_note,
                  rescheduled_date, created_at
           FROM requests
           WHERE user_id = ?
           ORDER BY id DESC''',
        (session['user_id'],)
    ).fetchall()
    conn.close()

    # Build a lookup: booking_id → latest request row (dict)
    request_map = {}
    for r in requests_list:
        bid = r['booking_id']
        if bid not in request_map:          # first row is already the latest (ORDER BY id DESC)
            request_map[bid] = dict(r)

    return render_template('my_bookings.html',
                           my_bookings=bookings_list,
                           request_map=request_map,
                           user=session['username'])

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    booking_count = conn.execute("SELECT COUNT(*) FROM bookings WHERE user_id=?", (session['user_id'],)).fetchone()[0]
    total_spent_row = conn.execute("SELECT SUM(total_price) FROM bookings WHERE user_id=?", (session['user_id'],)).fetchone()
    total_spent = total_spent_row[0] or 0
    swift_points = total_spent // 10
    conn.close()
    return render_template('profile.html', user=session['username'],
                           booking_count=booking_count,
                           total_spent=total_spent,
                           swift_points=swift_points)

@app.route('/cancel')
def cancel_ticket():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    bookings_for_cancel = conn.execute(
        '''SELECT bookings.id,
                  COALESCE(buses.name, 'Bus (removed)') AS name,
                  bookings.bus_id,
                  bookings.seat_numbers,
                  bookings.total_price,
                  bookings.date
           FROM bookings
           LEFT JOIN buses ON bookings.bus_id = buses.id
           WHERE bookings.user_id = ?
           ORDER BY bookings.id DESC''',
        (session['user_id'],)
    ).fetchall()

    # Fetch existing requests for cancel status badges
    cancel_requests = conn.execute(
        '''SELECT booking_id, status, admin_note, created_at
           FROM requests
           WHERE user_id = ? AND request_type = 'cancel'
           ORDER BY id DESC''',
        (session['user_id'],)
    ).fetchall()
    conn.close()

    today = date.today().isoformat()
    # Build lookup: booking_id → latest cancel request
    cancel_req_map = {}
    for r in cancel_requests:
        if r['booking_id'] not in cancel_req_map:
            cancel_req_map[r['booking_id']] = dict(r)

    return render_template('cancel.html', my_bookings=bookings_for_cancel,
                           cancel_req_map=cancel_req_map,
                           user=session['username'], today=today)

@app.route('/reschedule')
def reschedule_ticket():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    conn = get_db_connection()
    bookings_for_resched = conn.execute(
        '''SELECT bookings.id,
                  COALESCE(buses.name, 'Bus (removed)') AS name,
                  bookings.bus_id,
                  bookings.seat_numbers,
                  bookings.total_price,
                  bookings.date
           FROM bookings
           LEFT JOIN buses ON bookings.bus_id = buses.id
           WHERE bookings.user_id = ?
           ORDER BY bookings.id DESC''',
        (session['user_id'],)
    ).fetchall()

    # Fetch existing reschedule requests for status badges
    resched_requests = conn.execute(
        '''SELECT booking_id, status, admin_note, rescheduled_date, created_at
           FROM requests
           WHERE user_id = ? AND request_type = 'reschedule'
           ORDER BY id DESC''',
        (session['user_id'],)
    ).fetchall()
    conn.close()

    today = date.today().isoformat()
    resched_req_map = {}
    for r in resched_requests:
        if r['booking_id'] not in resched_req_map:
            resched_req_map[r['booking_id']] = dict(r)

    return render_template('reschedule.html', my_bookings=bookings_for_resched,
                           resched_req_map=resched_req_map,
                           user=session['username'], today=today)

# ══════════════════════════════════════════════════════════
#  REQUEST SYSTEM — User-facing APIs
# ══════════════════════════════════════════════════════════

@app.route('/request/create', methods=['POST'])
def create_request():
    """
    User submits a cancel or reschedule request.
    Does NOT modify the booking immediately — that only happens after admin approval.

    Request JSON:
        { "booking_id": 5, "request_type": "cancel" }
        { "booking_id": 5, "request_type": "reschedule", "rescheduled_date": "2025-09-15" }

    Response JSON:
        { "status": "success", "request_id": 12, "message": "..." }
        { "status": "error",   "message": "..." }
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})

    data = request.json or {}
    booking_id      = data.get('booking_id')
    request_type    = data.get('request_type')   # 'cancel' | 'reschedule'
    rescheduled_date = data.get('rescheduled_date')

    if not booking_id or request_type not in ('cancel', 'reschedule'):
        return jsonify({'status': 'error', 'message': 'Invalid request parameters'})

    if request_type == 'reschedule' and not rescheduled_date:
        return jsonify({'status': 'error', 'message': 'New date is required for reschedule'})

    conn = get_db_connection()

    # Verify the booking belongs to the logged-in user
    booking = conn.execute(
        '''SELECT bookings.*, 
                  COALESCE(buses.name,  'Bus (removed)') AS bus_name,
                  COALESCE(buses.route, '—')             AS bus_route
           FROM bookings
           LEFT JOIN buses ON bookings.bus_id = buses.id
           WHERE bookings.id = ? AND bookings.user_id = ?''',
        (booking_id, session['user_id'])
    ).fetchone()

    if not booking:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Booking not found'})

    # Block duplicate pending requests for the same booking
    existing = conn.execute(
        "SELECT id FROM requests WHERE booking_id = ? AND status = 'pending'",
        (booking_id,)
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'status': 'error',
                        'message': 'A pending request already exists for this booking. '
                                   'Please wait for admin review.'})

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        '''INSERT INTO requests
               (user_id, booking_id, request_type, bus_name, bus_route,
                original_date, rescheduled_date, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)''',
        (session['user_id'], booking_id, request_type,
         booking['bus_name'], booking['bus_route'],
         booking['date'], rescheduled_date, now)
    )
    new_id = cursor.lastrowid
    conn.commit()
    conn.close()

    return jsonify({'status': 'success', 'request_id': new_id,
                    'message': 'Request submitted. Awaiting admin approval.'})


@app.route('/my-requests/status')
def my_requests_status():
    """
    Returns all requests (and their current status) for the logged-in user.
    Used by the frontend to poll / refresh badges without a full page reload.

    Response JSON:
        [ { "id": 1, "booking_id": 5, "request_type": "cancel",
            "status": "pending", "admin_note": null, ... }, ... ]
    """
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})

    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT id, booking_id, request_type, bus_name, bus_route,
                  original_date, rescheduled_date, status, admin_note, created_at, updated_at
           FROM requests
           WHERE user_id = ?
           ORDER BY id DESC''',
        (session['user_id'],)
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


# ══════════════════════════════════════════════════════════
#  REQUEST SYSTEM — Admin-facing APIs
# ══════════════════════════════════════════════════════════

@app.route('/admin/requests/all')
def admin_get_requests():
    """
    Returns all requests (pending + decided) for the admin dashboard.

    Response JSON:
        [ { "id": 1, "username": "alice", "booking_id": 5,
            "request_type": "cancel", "bus_name": "NueGo", "bus_route": "...",
            "original_date": "2025-08-10", "rescheduled_date": null,
            "seat_numbers": "[2,3]", "total_price": 560,
            "status": "pending", "admin_note": null,
            "created_at": "2025-07-30 10:22:11" }, ... ]
    """
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'})

    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT requests.id,
                  users.username,
                  requests.booking_id,
                  requests.request_type,
                  requests.bus_name,
                  requests.bus_route,
                  requests.original_date,
                  requests.rescheduled_date,
                  bookings.seat_numbers,
                  bookings.total_price,
                  requests.status,
                  requests.admin_note,
                  requests.created_at,
                  requests.updated_at
           FROM requests
           LEFT JOIN users    ON requests.user_id    = users.id
           LEFT JOIN bookings ON requests.booking_id = bookings.id
           ORDER BY
               CASE requests.status WHEN 'pending' THEN 0 ELSE 1 END,
               requests.id DESC''',
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/admin/request/<int:req_id>/decide', methods=['POST'])
def decide_request(req_id):
    """
    Admin approves or rejects a request.
    On approval:
      - cancel   → booking row is deleted
      - reschedule → booking.date is updated to rescheduled_date

    Request JSON:
        { "decision": "approved", "admin_note": "Looks good." }
        { "decision": "rejected", "admin_note": "No seats available on new date." }

    Response JSON:
        { "status": "success", "decision": "approved", "request_id": 1 }
        { "status": "error",   "message": "..." }
    """
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'})

    data       = request.json or {}
    decision   = data.get('decision')     # 'approved' | 'rejected'
    admin_note = data.get('admin_note', '').strip()

    if decision not in ('approved', 'rejected'):
        return jsonify({'status': 'error', 'message': 'Decision must be approved or rejected'})

    conn = get_db_connection()
    req = conn.execute("SELECT * FROM requests WHERE id = ?", (req_id,)).fetchone()

    if not req:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Request not found'})

    if req['status'] != 'pending':
        conn.close()
        return jsonify({'status': 'error',
                        'message': f'Request already {req["status"]}. Cannot decide again.'})

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Update the request row
    conn.execute(
        "UPDATE requests SET status = ?, admin_note = ?, updated_at = ? WHERE id = ?",
        (decision, admin_note, now, req_id)
    )

    # Apply the effect only on approval
    if decision == 'approved':
        if req['request_type'] == 'cancel':
            conn.execute("DELETE FROM bookings WHERE id = ?", (req['booking_id'],))
        elif req['request_type'] == 'reschedule' and req['rescheduled_date']:
            conn.execute(
                "UPDATE bookings SET date = ? WHERE id = ?",
                (req['rescheduled_date'], req['booking_id'])
            )

    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'decision': decision, 'request_id': req_id})


# ══════════════════════════════════════════════════════════
#  LEGACY DIRECT ROUTES (kept for backward-compat / admin use)
# ══════════════════════════════════════════════════════════

@app.route('/reschedule_booking/<int:booking_id>', methods=['POST'])
def reschedule_booking(booking_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})
    new_date = request.json.get('new_date', '')
    if not new_date:
        return jsonify({'status': 'error', 'message': 'No date provided'})
    conn = get_db_connection()
    booking = conn.execute(
        "SELECT id FROM bookings WHERE id=? AND user_id=?",
        (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Booking not found'})
    conn.execute("UPDATE bookings SET date=? WHERE id=?", (new_date, booking_id))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'new_date': new_date})

# ── SEAT & BOOKING APIs ──
@app.route('/get_seats/<int:bus_id>')
def get_seats(bus_id):
    conn = get_db_connection()
    bus = conn.execute("SELECT seats FROM buses WHERE id=?", (bus_id,)).fetchone()
    if not bus:
        conn.close()
        return jsonify({'total': 0, 'booked': []})
    total_seats = bus['seats']
    data = conn.execute("SELECT seat_numbers FROM bookings WHERE bus_id=?", (bus_id,)).fetchall()
    booked_seats = []
    for row in data:
        parsed = json.loads(row['seat_numbers'])
        booked_seats.extend([int(s) for s in parsed])
    conn.close()
    return jsonify({'total': int(total_seats), 'booked': booked_seats})

@app.route('/book_ticket', methods=['POST'])
def book_ticket():
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})
    data = request.json
    bus_id   = data['busId']
    seats    = data['seats']
    price    = data['price']
    # ISSUE 1 FIX: frontend now sends the actual departure/arrival times
    # displayed on the bus card so getTripStatus() compares real clock values
    conn = get_db_connection()
    # ISSUE 1 FIX: always fetch dep/arr times from the bus table as
    # authoritative source — frontend hint used only as last fallback.
    bus = conn.execute("SELECT dep_time, arr_time FROM buses WHERE id=?", (bus_id,)).fetchone()
    dep_time = (bus['dep_time'] if bus and bus['dep_time'] else None) or data.get('depTime','08:00')
    arr_time = (bus['arr_time'] if bus and bus['arr_time'] else None) or data.get('arrTime','14:00')
    conn.execute(
        '''INSERT INTO bookings
               (user_id, bus_id, seat_numbers, total_price, date, dep_time, arr_time)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (session['user_id'], bus_id, json.dumps(seats), price,
         datetime.now().strftime("%Y-%m-%d"), dep_time, arr_time)
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'dep_time': dep_time, 'arr_time': arr_time})

@app.route('/cancel_booking/<int:booking_id>', methods=['POST'])
def cancel_booking(booking_id):
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})
    conn = get_db_connection()
    booking = conn.execute(
        "SELECT id FROM bookings WHERE id=? AND user_id=?",
        (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Booking not found'})
    conn.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()
    return jsonify({'status': 'success'})


# ══════════════════════════════════════════════════════════
#  FEEDBACK SYSTEM
# ══════════════════════════════════════════════════════════

@app.route('/feedback/submit', methods=['POST'])
def submit_feedback():
    """User submits a rating + message for a completed trip."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})
    data       = request.json or {}
    booking_id = data.get('booking_id')
    rating     = data.get('rating')      # integer 1-5
    message    = data.get('message', '').strip()
    if not booking_id or not rating:
        return jsonify({'status': 'error', 'message': 'booking_id and rating are required'})
    conn = get_db_connection()
    # Verify booking belongs to user
    booking = conn.execute(
        '''SELECT bookings.id, COALESCE(buses.name,'Bus (removed)') AS bus_name,
                  COALESCE(buses.route,'—') AS bus_route
           FROM bookings LEFT JOIN buses ON bookings.bus_id=buses.id
           WHERE bookings.id=? AND bookings.user_id=?''',
        (booking_id, session['user_id'])
    ).fetchone()
    if not booking:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Booking not found'})
    # Prevent duplicate feedback for same booking
    existing = conn.execute(
        "SELECT id FROM feedback WHERE booking_id=? AND user_id=?",
        (booking_id, session['user_id'])
    ).fetchone()
    if existing:
        conn.close()
        return jsonify({'status': 'error', 'message': 'Feedback already submitted for this booking'})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor = conn.execute(
        '''INSERT INTO feedback (user_id, booking_id, bus_name, bus_route, rating, message, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (session['user_id'], booking_id, booking['bus_name'], booking['bus_route'],
         int(rating), message, now)
    )
    fid = cursor.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'feedback_id': fid})


@app.route('/feedback/status/<int:booking_id>')
def feedback_status(booking_id):
    """Returns feedback status for one booking (user-facing poll)."""
    if 'user_id' not in session:
        return jsonify({'status': 'error', 'message': 'Not logged in'})
    conn = get_db_connection()
    row = conn.execute(
        "SELECT id, status, admin_note FROM feedback WHERE booking_id=? AND user_id=?",
        (booking_id, session['user_id'])
    ).fetchone()
    conn.close()
    if not row:
        return jsonify({'submitted': False})
    return jsonify({'submitted': True, 'feedback_id': row['id'],
                    'status': row['status'], 'admin_note': row['admin_note']})


@app.route('/admin/feedback/all')
def admin_get_feedback():
    """Admin: fetch all feedback with context."""
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
    conn = get_db_connection()
    rows = conn.execute(
        '''SELECT feedback.id, users.username, feedback.booking_id,
                  feedback.bus_name, feedback.bus_route,
                  feedback.rating, feedback.message,
                  feedback.status, feedback.admin_note,
                  feedback.created_at, feedback.updated_at
           FROM feedback
           LEFT JOIN users ON feedback.user_id = users.id
           ORDER BY CASE feedback.status WHEN 'submitted' THEN 0 ELSE 1 END,
                    feedback.id DESC'''
    ).fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route('/admin/feedback/<int:feedback_id>/action', methods=['POST'])
def admin_feedback_action(feedback_id):
    """Admin: set status and optional note on a feedback entry.
       status: 'reviewed' | 'resolved' | 'reported'
    """
    if session.get('role') != 'admin':
        return jsonify({'status': 'error', 'message': 'Unauthorized'})
    data       = request.json or {}
    new_status = data.get('status')
    note       = data.get('note', '').strip()
    if new_status not in ('reviewed', 'resolved', 'reported'):
        return jsonify({'status': 'error', 'message': 'Invalid status'})
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = get_db_connection()
    conn.execute(
        "UPDATE feedback SET status=?, admin_note=?, updated_at=? WHERE id=?",
        (new_status, note, now, feedback_id)
    )
    conn.commit()
    conn.close()
    return jsonify({'status': 'success', 'new_status': new_status})


# ── ADMIN ──
@app.route('/admin')
def admin_dashboard():
    if 'role' not in session or session['role'] != 'admin':
        return redirect(url_for('login'))
    conn = get_db_connection()
    buses = conn.execute("SELECT * FROM buses").fetchall()
    all_bookings = conn.execute(
        '''SELECT bookings.id, users.username, buses.name, bookings.seat_numbers, bookings.total_price
           FROM bookings JOIN users ON bookings.user_id = users.id
           JOIN buses ON bookings.bus_id = buses.id'''
    ).fetchall()
    # Fetch pending requests + new feedback counts for sidebar badges
    pending_count    = conn.execute(
        "SELECT COUNT(*) FROM requests WHERE status='pending'"
    ).fetchone()[0]
    new_feedback_count = conn.execute(
        "SELECT COUNT(*) FROM feedback WHERE status='submitted'"
    ).fetchone()[0]
    conn.close()
    return render_template('admin.html', buses=buses, bookings=all_bookings,
                           pending_count=pending_count,
                           new_feedback_count=new_feedback_count,
                           user=session['username'])

@app.route('/admin/add_bus', methods=['POST'])
def add_bus():
    if session.get('role') == 'admin':
        name  = request.form['name']
        route = request.form['route']
        price = request.form['price']
        seats = request.form['seats']
        conn  = get_db_connection()
        conn.execute("INSERT INTO buses (name, route, price, seats) VALUES (?, ?, ?, ?)",
                     (name, route, price, seats))
        conn.commit()
        conn.close()
    return redirect(url_for('admin_dashboard'))

@app.route('/admin/delete_bus/<int:id>')
def delete_bus(id):
    if session.get('role') == 'admin':
        conn = get_db_connection()
        conn.execute("DELETE FROM buses    WHERE id=?",     (id,))
        conn.execute("DELETE FROM bookings WHERE bus_id=?", (id,))
        conn.commit()
        conn.close()
    return redirect(url_for('admin_dashboard'))