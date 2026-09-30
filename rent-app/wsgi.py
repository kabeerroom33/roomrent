"""
WSGI entry point for Render / Gunicorn.
Usage: gunicorn wsgi:application
"""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app
application = create_app()

if __name__ == '__main__':
    application.run()
