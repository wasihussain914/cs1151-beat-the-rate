"""Minimal local harness: flask --app server/dev_app run -p 8787"""
from flask import Flask
from cs1151_game import bp

app = Flask(__name__)
app.register_blueprint(bp)
