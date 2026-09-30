"""App-wide configuration constants."""
import os

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'rent.db')
ROOM_NAME = os.environ.get('ROOM_NAME', 'Room 33')
