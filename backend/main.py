"""Entry point for the Flask backend.

Local dev:      python main.py           (http://localhost:5000)
Production:     gunicorn -w 2 -b 0.0.0.0:5000 "main:app"
"""
from website import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
