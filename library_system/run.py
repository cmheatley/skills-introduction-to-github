#!/usr/bin/env python3
"""Entry point: python run.py"""
from app import app
from init_db import init_db

if __name__ == '__main__':
    init_db()
    app.run(debug=False, host='0.0.0.0', port=5000)
