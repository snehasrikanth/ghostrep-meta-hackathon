import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Tests must never write to the developer's data/ghostrep.db.
_TEST_DATA = Path(tempfile.mkdtemp(prefix="ghostrep-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DATA / 'test.db'}"
os.environ["DATA_DIR"] = str(_TEST_DATA)
os.environ["AI_PROVIDER"] = "local"
os.environ["WORKOUT_PROVIDER"] = "local"
os.environ["COACHING_PROVIDER"] = "local"
os.environ["SEGMENTATION_PROVIDER"] = "none"
os.environ["ENABLE_META_API"] = "false"
os.environ["META_RETRY_SLEEP"] = "false"

import socket

_original_getaddrinfo = socket.getaddrinfo
_original_create_connection = socket.create_connection


def _meta_host(value) -> bool:
    host = value[0] if isinstance(value, tuple) else value
    return isinstance(host, str) and (host == "api.meta.ai" or host.endswith(".meta.ai"))


def _block_meta_dns(host, *args, **kwargs):
    if _meta_host(host):
        raise RuntimeError(f"blocked Meta network call to {host}")
    return _original_getaddrinfo(host, *args, **kwargs)


def _block_meta_connection(address, *args, **kwargs):
    if _meta_host(address):
        raise RuntimeError(f"blocked Meta network call to {address[0]}")
    return _original_create_connection(address, *args, **kwargs)


socket.getaddrinfo = _block_meta_dns
socket.create_connection = _block_meta_connection
