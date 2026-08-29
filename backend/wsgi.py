import os
from dotenv import load_dotenv

# 加载 .env 文件
load_dotenv()

from app import create_app

config_name = os.getenv("FLASK_ENV", "development")
app = create_app(config_name)

if __name__ == "__main__":
    host = os.getenv("FLASK_HOST", "0.0.0.0")
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = config_name == "development"
    app.run(host=host, port=port, debug=debug)
