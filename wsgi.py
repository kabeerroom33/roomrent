"""
WSGI entry point for Render.
This wrapper exists because the Flask app lives in the rent-app subfolder.
"""
import os
import sys

ROOT = os.path.dirname(__file__)
APP_DIR = os.path.join(ROOT, 'rent-app')
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from app import create_app

application = create_app()

if __name__ == '__main__':
    application.run(host='0.0.0.0', port=int(os.environ.get('PORT', 8080)))
