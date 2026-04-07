import threading

_log_lock = threading.Lock()


def log(msg, level="INFO", sku=""):
    icons = {"INFO": "i ", "OK": "OK", "WARN": "! ", "ERR": "X ", "DL": "->"}
    prefix = f"[{sku}] " if sku else ""
    with _log_lock:
        print(f"  [{icons.get(level, '  ')}] {prefix}{msg}")


def banner(text):
    bar = "=" * 60
    print(f"\n{bar}\n  {text}\n{bar}\n")
