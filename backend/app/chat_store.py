import json
import os
from threading import Lock

_lock = Lock()
_store_path = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'data', 'chat_history.json'))
_messages = []

def _ensure_loaded():
    global _messages
    if _messages:
        return
    try:
        if os.path.exists(_store_path):
            with open(_store_path, 'r', encoding='utf-8') as f:
                _messages = json.load(f)
        else:
            _messages = []
    except Exception:
        _messages = []

def _persist():
    try:
        os.makedirs(os.path.dirname(_store_path), exist_ok=True)
        with open(_store_path, 'w', encoding='utf-8') as f:
            json.dump(_messages, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def get_messages():
    with _lock:
        _ensure_loaded()
        return list(_messages)

def add_message(msg: dict):
    with _lock:
        _ensure_loaded()
        _messages.append(msg)
        _persist()
        return list(_messages)

def clear_messages():
    with _lock:
        _ensure_loaded()
        _messages.clear()
        _persist()
        return []
