from flask import Flask
import json
import os

# Initialize Flask
app = Flask(__name__)

# Load configuration from JSON
base_dir = os.path.dirname(os.path.dirname(__file__))
config_path = os.path.join(base_dir, 'config.json')

with open(config_path) as config_file:
    config = json.load(config_file)

app.secret_key = config['SECRET_KEY']
app.config['DB_NAME'] = config['DATABASE_NAME']

# Import routes at the bottom to avoid circular imports
from app import routes