import os


RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"


def enabled():
    return os.environ.get("NO_COLOR", "").strip() == ""


def paint(text, *styles):
    if not enabled() or not styles:
        return str(text)
    return "".join(styles) + str(text) + RESET


def title(text):
    return paint(text, BOLD, CYAN)


def success(text):
    return paint(text, GREEN)


def warning(text):
    return paint(text, YELLOW)


def error(text):
    return paint(text, RED)


def info(text):
    return paint(text, CYAN)


def muted(text):
    return paint(text, DIM)

