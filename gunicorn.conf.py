import os

port = int(os.environ.get('PORT', 10000))
bind = f"0.0.0.0:{port}"
workers = 1
threads = 4
timeout = 120
keepalive = 2
