import os
from main import app

def run():
    port = int(os.environ.get("PORT", 10000))
    print(f"Starting server on port {port}")
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    run()
