# Library Ordering & Budget Tracking System

A web-based collection development ordering and budget tracking system for Lamar University's Mary & John Gray Library.

## Features

- **Order Management** — Create, view, edit, and delete acquisition orders; add/edit/delete items per order
- **Status Tracking** — Orders flow through NEW → PENDING → COMPLETED
- **Budget Tracking** — Department and vendor budget allocation vs. spending by fiscal year
- **Role-Based Access** — Admin, Librarian, Acquisition Technician, Cataloging Personnel
- **User Management** — Admin panel to create/edit/deactivate users
- **System Settings** — Manage destinations, departments, programs, vendors, material types, fiscal years

## Quick Start

### Requirements

- Python 3.10+
- pip

### Install & Run

```bash
cd library_system
pip install -r requirements.txt
python run.py
```

Then open http://localhost:5000 in your browser.

### Default Login Credentials

| Username     | Password     | Role                   |
|-------------|-------------|------------------------|
| `admin`     | `admin123`  | Administrator          |
| `librarian1`| `librarian1`| Librarian              |
| `acqtech1`  | `acqtech1`  | Acquisition Technician |
| `catpers1`  | `catpers1`  | Cataloging Personnel   |
| `testlib`   | `testlib`   | Librarian (TEST)       |
| `testtech`  | `testtech`  | Acquisition Tech (TEST)|

**Change all passwords after first login.**

### Reset the Database

```bash
python init_db.py
```

(Deletes and re-creates the database with seed data.)

## Role Permissions

| Feature                    | Admin | Librarian | Acq. Tech | Cat. Personnel |
|---------------------------|-------|-----------|-----------|----------------|
| View orders                | ✓     | ✓         | ✓         | ✓              |
| Create orders              | ✓     | ✓         | ✓         | ✓              |
| Edit / Delete orders       | ✓     | ✓         | —         | —              |
| Edit budget allocations    | ✓     | ✓         | —         | —              |
| Manage users               | ✓     | —         | —         | —              |
| System settings            | ✓     | —         | —         | —              |

## Project Structure

```
library_system/
├── app.py           # Flask routes and application logic
├── init_db.py       # Database schema + seed data
├── run.py           # Entry point
├── requirements.txt
├── instance/
│   └── library.db   # SQLite database (created on first run)
├── templates/
│   ├── base.html
│   ├── login.html
│   ├── orders/
│   │   ├── summary.html
│   │   ├── detail.html
│   │   ├── form.html
│   │   ├── edit.html
│   │   └── item_form.html
│   ├── financials/
│   │   └── budget.html
│   └── admin/
│       ├── users.html
│       ├── user_form.html
│       └── manage.html
└── static/
    ├── css/style.css
    └── js/main.js
```
