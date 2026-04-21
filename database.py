import sqlite3
from app import app

def get_db_connection():
    conn = sqlite3.connect(app.config['DB_NAME'])
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    c = conn.cursor()

    # ── Core tables ──
    c.execute('''CREATE TABLE IF NOT EXISTS users
                 (id INTEGER PRIMARY KEY, username TEXT UNIQUE,
                  password TEXT, role TEXT)''')

    # ISSUE 1 FIX: Add dep_time + arr_time to buses so each bus has
    # realistic schedule times used for trip-lifecycle comparison.
    c.execute('''CREATE TABLE IF NOT EXISTS buses
                 (id INTEGER PRIMARY KEY, name TEXT, route TEXT,
                  price INTEGER, seats INTEGER,
                  dep_time TEXT DEFAULT '08:00',
                  arr_time TEXT DEFAULT '14:00')''')

    # ISSUE 1 FIX: Add dep_time + arr_time to bookings so the exact
    # schedule is stored at booking time (survives bus edits later).
    c.execute('''CREATE TABLE IF NOT EXISTS bookings
                 (id INTEGER PRIMARY KEY, user_id INTEGER, bus_id INTEGER,
                  seat_numbers TEXT, total_price INTEGER, date TEXT,
                  dep_time TEXT DEFAULT '08:00',
                  arr_time TEXT DEFAULT '14:00',
                  FOREIGN KEY(user_id) REFERENCES users(id),
                  FOREIGN KEY(bus_id)  REFERENCES buses(id))''')

    c.execute('''CREATE TABLE IF NOT EXISTS requests
                 (id            INTEGER PRIMARY KEY,
                  user_id       INTEGER NOT NULL,
                  booking_id    INTEGER NOT NULL,
                  request_type  TEXT    NOT NULL,
                  bus_name      TEXT,
                  bus_route     TEXT,
                  original_date TEXT,
                  rescheduled_date TEXT,
                  status        TEXT    NOT NULL DEFAULT 'pending',
                  admin_note    TEXT,
                  created_at    TEXT,
                  updated_at    TEXT,
                  FOREIGN KEY(user_id)    REFERENCES users(id),
                  FOREIGN KEY(booking_id) REFERENCES bookings(id))''')

    # ISSUE 3 FIX: Feedback table — stores user rating + message per booking
    c.execute('''CREATE TABLE IF NOT EXISTS feedback
                 (id         INTEGER PRIMARY KEY,
                  user_id    INTEGER NOT NULL,
                  booking_id INTEGER NOT NULL,
                  bus_name   TEXT,
                  bus_route  TEXT,
                  rating     INTEGER NOT NULL,           -- 1-5
                  message    TEXT,
                  status     TEXT NOT NULL DEFAULT 'submitted',
                                                         -- submitted|reviewed|resolved|reported
                  admin_note TEXT,
                  created_at TEXT,
                  updated_at TEXT,
                  FOREIGN KEY(user_id)    REFERENCES users(id),
                  FOREIGN KEY(booking_id) REFERENCES bookings(id))''')

    # ── MIGRATION: add new columns to existing tables safely ──
    for col, dflt in [('dep_time', "'08:00'"), ('arr_time', "'14:00'")]:
        try:
            c.execute(f"ALTER TABLE buses     ADD COLUMN {col} TEXT DEFAULT {dflt}")
        except Exception:
            pass
        try:
            c.execute(f"ALTER TABLE bookings  ADD COLUMN {col} TEXT DEFAULT {dflt}")
        except Exception:
            pass

    # ── Seed admin ──
    c.execute("SELECT * FROM users WHERE role='admin'")
    if not c.fetchone():
        c.execute("INSERT INTO users (username, password, role) VALUES (?,?,?)",
                  ('admin', 'admin123', 'admin'))

    # ISSUE 1 FIX: Seed buses with realistic dep_time / arr_time.
    # Using times spread across the day so demos show all three states.
    c.execute("SELECT COUNT(*) FROM buses")
    if c.fetchone()[0] == 0:
        default_buses = [
            ('NueGo Electric AC',    'Chennai - Coimbatore',      280, 40, '06:00', '10:30'),
            ('TNSTC Volvo AC',       'Chennai - Madurai',         350, 44, '07:30', '13:00'),
            ('SRS Travels',          'Chennai - Bengaluru',       420, 40, '09:00', '15:30'),
            ('Orange Tours AC',      'Coimbatore - Chennai',      290, 44, '10:30', '15:00'),
            ('KPN Travels',          'Madurai - Chennai',         310, 40, '14:00', '19:30'),
            ('Parveen Travels',      'Chennai - Tirunelveli',     380, 36, '16:00', '22:00'),
            ('VRL Travels AC',       'Chennai - Hyderabad',       550, 40, '18:00', '04:00'),
            ('Kallada Travels',      'Coimbatore - Bengaluru',    400, 40, '20:30', '02:30'),
            ('SETC Super Deluxe',    'Chennai - Salem',           220, 54, '22:00', '03:30'),
            ('IntrCity SmartBus',    'Chennai - Tiruchirappalli', 260, 42, '23:30', '04:30'),
        ]
        c.executemany(
            "INSERT INTO buses (name,route,price,seats,dep_time,arr_time) VALUES (?,?,?,?,?,?)",
            default_buses
        )

    conn.commit()
    conn.close()