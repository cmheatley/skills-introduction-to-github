"""Initialize (or reset) the SQLite database with schema and seed data."""
import sqlite3
import os
from werkzeug.security import generate_password_hash

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'instance', 'library.db')

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT    NOT NULL UNIQUE,
    password_hash TEXT    NOT NULL,
    first_name    TEXT    NOT NULL DEFAULT '',
    last_name     TEXT    NOT NULL DEFAULT '',
    email         TEXT,
    role          TEXT    NOT NULL DEFAULT 'librarian',
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS destinations (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS departments (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    name           TEXT    NOT NULL,
    destination_id INTEGER REFERENCES destinations(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS programs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT    NOT NULL,
    department_id INTEGER REFERENCES departments(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS vendors (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name   TEXT    NOT NULL UNIQUE,
    active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS material_types (
    id   INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS fiscal_years (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    label      TEXT NOT NULL,
    start_date DATE NOT NULL,
    end_date   DATE NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    status                 TEXT    NOT NULL DEFAULT 'NEW',
    requisition_number     TEXT,
    request_date           DATE    NOT NULL,
    librarian_id           INTEGER REFERENCES users(id) ON DELETE SET NULL,
    acquisition_tech_id    INTEGER REFERENCES users(id) ON DELETE SET NULL,
    cataloging_personnel_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    destination_id         INTEGER REFERENCES destinations(id) ON DELETE SET NULL,
    department_id          INTEGER REFERENCES departments(id) ON DELETE SET NULL,
    program_id             INTEGER REFERENCES programs(id) ON DELETE SET NULL,
    fiscal_year_id         INTEGER REFERENCES fiscal_years(id) ON DELETE SET NULL,
    order_total            REAL    NOT NULL DEFAULT 0,
    date_fulfilled         DATE,
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS order_items (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    title            TEXT    NOT NULL,
    material_type_id INTEGER REFERENCES material_types(id) ON DELETE SET NULL,
    quantity         INTEGER NOT NULL DEFAULT 1,
    vendor_id        INTEGER REFERENCES vendors(id) ON DELETE SET NULL,
    source_url       TEXT,
    requestor_notes  TEXT,
    po_num           TEXT,
    item_amount      REAL    NOT NULL DEFAULT 0,
    date_ordered     DATE,
    date_received    DATE,
    date_catalogued  DATE,
    tech_notes       TEXT,
    item_status      TEXT    NOT NULL DEFAULT 'Not Yet Ordered',
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS faculty_requests (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id       INTEGER UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    faculty_name   TEXT,
    faculty_email  TEXT,
    faculty_phone  TEXT,
    notify_faculty INTEGER NOT NULL DEFAULT 0,
    preview_item   INTEGER NOT NULL DEFAULT 0,
    hold_item      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS course_reserves (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id         INTEGER UNIQUE NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    is_course_reserve INTEGER NOT NULL DEFAULT 0,
    course_name      TEXT,
    course_number    TEXT
);

CREATE TABLE IF NOT EXISTS department_budgets (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id INTEGER NOT NULL REFERENCES fiscal_years(id) ON DELETE CASCADE,
    department_id  INTEGER NOT NULL REFERENCES departments(id) ON DELETE CASCADE,
    amount_allocated REAL NOT NULL DEFAULT 0,
    effective_date DATE,
    UNIQUE(fiscal_year_id, department_id)
);

CREATE TABLE IF NOT EXISTS vendor_budgets (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    fiscal_year_id   INTEGER NOT NULL REFERENCES fiscal_years(id) ON DELETE CASCADE,
    vendor_id        INTEGER NOT NULL REFERENCES vendors(id) ON DELETE CASCADE,
    amount_allocated REAL NOT NULL DEFAULT 0,
    effective_date   DATE,
    UNIQUE(fiscal_year_id, vendor_id)
);
"""

SEED_DESTINATIONS = ['Lamar University']

# Departments map to academic departments at Lamar University
SEED_DEPARTMENTS = [
    # College of Arts and Sciences
    'Biology',
    'Chemistry and Biochemistry',
    'Computer Science',
    'Criminal Justice',
    'Earth and Space Sciences',
    'English and Modern Languages',
    'History',
    'Mathematics',
    'JoAnne Gay Dishman School of Nursing',
    'Physics',
    'Political Science',
    'Psychology',
    'Sociology and Social Work',
    # College of Business
    'Accounting, Finance and Economics',
    'Construction Management',
    'General Business',
    'Information Systems',
    'Management and Marketing',
    # College of Education and Human Development
    'Counseling',
    'Curriculum and Instruction',
    'Deaf Studies and Deaf Education',
    'Educational Leadership',
    # College of Engineering
    'Chemical and Biomolecular Engineering',
    'Civil and Environmental Engineering',
    'Electrical and Computer Engineering',
    'Industrial and Systems Engineering',
    'Mechanical Engineering',
    # College of Fine Arts and Communication
    'Art and Design',
    'Communication and Media',
    'Music',
    'Speech and Hearing Sciences',
    'Theatre and Dance',
    # Library collections
    'GovDocs',
    'Juvenile Collection',
    'Replacements',
    'Special Collections',
]

SEED_PROGRAMS = {
    # College of Arts and Sciences
    'Biology': ['Biology', 'Botany', 'Marine Biology', 'Zoology'],
    'Chemistry and Biochemistry': ['Biochemistry', 'Chemistry'],
    'Computer Science': ['Computer Science', 'Cybersecurity'],
    'Criminal Justice': ['Criminal Justice', 'Forensic Science'],
    'Earth and Space Sciences': ['Earth Science', 'Environmental Science', 'Space Science'],
    'English and Modern Languages': ['English', 'French', 'Spanish', 'Technical Writing'],
    'History': ['History'],
    'Mathematics': ['Mathematics', 'Statistics'],
    'JoAnne Gay Dishman School of Nursing': ['Nursing', 'Nursing – RN to BSN'],
    'Physics': ['Physics'],
    'Political Science': ['Political Science', 'Pre-Law'],
    'Psychology': ['Applied Behavioral Analysis', 'Psychology'],
    'Sociology and Social Work': ['Anthropology', 'Social Work', 'Sociology'],
    # College of Business
    'Accounting, Finance and Economics': ['Accounting', 'Economics', 'Finance'],
    'Construction Management': ['Construction Management'],
    'General Business': ['General Business', 'MBA'],
    'Information Systems': ['Cybersecurity Management', 'Information Systems'],
    'Management and Marketing': ['Management', 'Marketing', 'Supply Chain Management'],
    # College of Education and Human Development
    'Counseling': ['Mental Health Counseling', 'School Counseling'],
    'Curriculum and Instruction': [
        'Early Childhood Education', 'Elementary Education',
        'Secondary Education', 'Special Education',
    ],
    'Deaf Studies and Deaf Education': ['Deaf Education', 'Deaf Studies'],
    'Educational Leadership': ['Principal Certification', 'Superintendent Certification'],
    # College of Engineering
    'Chemical and Biomolecular Engineering': [
        'Biomolecular Engineering', 'Chemical Engineering',
    ],
    'Civil and Environmental Engineering': [
        'Civil Engineering', 'Environmental Engineering',
    ],
    'Electrical and Computer Engineering': [
        'Computer Engineering', 'Electrical Engineering',
    ],
    'Industrial and Systems Engineering': [
        'Industrial Engineering', 'Systems Engineering',
    ],
    'Mechanical Engineering': ['Mechanical Engineering'],
    # College of Fine Arts and Communication
    'Art and Design': ['Art History', 'Graphic Design', 'Studio Art'],
    'Communication and Media': [
        'Broadcasting', 'Communication', 'Journalism', 'Public Relations',
    ],
    'Music': ['Music Education', 'Music Performance'],
    'Speech and Hearing Sciences': ['Audiology', 'Speech-Language Pathology'],
    'Theatre and Dance': ['Dance', 'Technical Theatre', 'Theatre'],
    # Library collections
    'GovDocs': ['Government Documents'],
    'Juvenile Collection': ['Juvenile Collection'],
    'Replacements': ['Replacements'],
    'Special Collections': ['Special Collections'],
}

SEED_VENDORS = [
    'Amazon', 'Baker & Taylor', 'Brodart', 'EBSCO', 'Ingram',
    'ProQuest', 'Midwest Tape', 'YBP Library Services',
]

SEED_MATERIAL_TYPES = [
    'Print - Hardcover', 'Print - Softcover', 'E-Book', 'E-Journal',
    'DVD/Blu-ray', 'Streaming Media', 'Audio CD', 'Microfilm',
    'Map', 'Government Document', 'Other',
]

SEED_FISCAL_YEARS = [
    ('2023-2024', '2023-07-01', '2024-06-30'),
    ('2024-2025', '2024-07-01', '2025-06-30'),
    ('2025-2026', '2025-07-01', '2026-06-30'),
]

SEED_USERS = [
    ('admin',     'admin123',     'Admin',    'User',      'admin@lamar.edu',        'admin'),
    ('librarian1','librarian1',   'Katie',    'Yelinek',   'kyelinek@lamar.edu',     'librarian'),
    ('acqtech1',  'acqtech1',     'Courtney', 'Heatley',   'cheatley@lamar.edu',     'acquisition_tech'),
    ('catpers1',  'catpers1',     'Stacey',   'Hampe',     'shampe@lamar.edu',       'cataloging_personnel'),
    ('testlib',   'testlib',      'TEST',     'Librarian', 'testlib@lamar.edu',      'librarian'),
    ('testtech',  'testtech',     'TEST',     'Technician','testtech@lamar.edu',     'acquisition_tech'),
]


def init_db(force=False):
    os.makedirs(os.path.dirname(DATABASE), exist_ok=True)
    if os.path.exists(DATABASE) and not force:
        return

    conn = sqlite3.connect(DATABASE)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)

    # Destinations
    for d in SEED_DESTINATIONS:
        conn.execute('INSERT OR IGNORE INTO destinations (name) VALUES (?)', (d,))
    conn.commit()

    dest_ids = {row[0]: row[1] for row in conn.execute('SELECT name, id FROM destinations')}

    # Departments – all under single Lamar University destination
    lu_id = dest_ids.get('Lamar University')
    for dept in SEED_DEPARTMENTS:
        conn.execute(
            'INSERT OR IGNORE INTO departments (name, destination_id) VALUES (?,?)',
            (dept, lu_id)
        )
    conn.commit()

    dept_ids = {row[0]: row[1] for row in conn.execute('SELECT name, id FROM departments')}

    # Programs
    for dept_name, programs in SEED_PROGRAMS.items():
        dept_id = dept_ids.get(dept_name)
        if dept_id:
            for prog in programs:
                conn.execute(
                    'INSERT OR IGNORE INTO programs (name, department_id) VALUES (?,?)',
                    (prog, dept_id)
                )
    conn.commit()

    # Vendors
    for v in SEED_VENDORS:
        conn.execute('INSERT OR IGNORE INTO vendors (name, active) VALUES (?,1)', (v,))
    conn.commit()

    # Material types
    for mt in SEED_MATERIAL_TYPES:
        conn.execute('INSERT OR IGNORE INTO material_types (name) VALUES (?)', (mt,))
    conn.commit()

    # Fiscal years
    for label, start, end in SEED_FISCAL_YEARS:
        conn.execute(
            'INSERT OR IGNORE INTO fiscal_years (label, start_date, end_date) VALUES (?,?,?)',
            (label, start, end)
        )
    conn.commit()

    # Users
    for username, password, first, last, email, role in SEED_USERS:
        conn.execute(
            'INSERT OR IGNORE INTO users (username, password_hash, first_name, last_name, email, role, active) VALUES (?,?,?,?,?,?,1)',
            (username, generate_password_hash(password), first, last, email, role)
        )
    conn.commit()
    conn.close()
    print(f"Database initialized at {DATABASE}")


if __name__ == '__main__':
    init_db(force=True)
    print("Done.")
