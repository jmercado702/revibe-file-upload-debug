from app import app
from routes import *  # Import all routes

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
