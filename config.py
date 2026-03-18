import os
import sys

# 兼容低版本 Python 的 TOML 解析
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        print("缺少 TOML 解析库。请运行: pip install tomli")
        sys.exit(1)

# --- 目录常量 ---
INPUT_DIR = "input"
OUTPUT_DIR = "output"
OUTPUT_TEXT_DIR = "output_text"
PAGES_DIR_NAME = "pages"
LANDSCAPE_DIR_NAME = "landscape"
CONFIG_FILE = "config.toml"
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}

def load_config():
    """读取并返回 TOML 配置字典"""
    if not os.path.exists(CONFIG_FILE):
        print(f"找不到 {CONFIG_FILE}，请确保它在根目录。")
        sys.exit(1)
    with open(CONFIG_FILE, "rb") as f:
        return tomllib.load(f)