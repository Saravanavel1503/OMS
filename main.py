# -*- coding: utf-8 -*-
"""
Created on Fri Sep  5 11:25:58 2025

@author: SPE8COB
"""

# main.py
import threading, time, webbrowser
from app import app

def run_server():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False, threaded=True)

if __name__ == "__main__":
    t = threading.Thread(target=run_server, daemon=True)
    t.start()
    time.sleep(0.8)
    webbrowser.open("http://127.0.0.1:5000/")
    t.join()
