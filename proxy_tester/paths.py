import os
import sys


def app_base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def resource_base_dir():
    return getattr(sys, "_MEIPASS", BASE_DIR)


BASE_DIR = app_base_dir()
RESOURCE_DIR = resource_base_dir()
BIN_DIR = os.path.join(RESOURCE_DIR, "bin")
CONFIG_DIR = os.path.join(BASE_DIR, "configs")
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
LOG_DIR = os.path.join(BASE_DIR, "logs")
XRAY_BINARY = "xray.exe" if os.name == "nt" else "xray"
XRAY_EXE = os.path.join(BIN_DIR, "xray", XRAY_BINARY)
