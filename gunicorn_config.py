import os

bind = f"0.0.0.0:{int(os.environ.get('PORT', 10000))}"
workers = 1
threads = 4
worker_class = "gthread"
worker_connections = 1000
timeout = 120
keepalive = 5
