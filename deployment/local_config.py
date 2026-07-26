"""Loopback-only local debug configuration.

Real credentials and hardware endpoints must be supplied outside version control.
"""


class BasicConfig:
    ak = ""
    sk = ""
    disable_browser = True
    no_update_feedback = True
    log_level = "INFO"


class WSConfig:
    reconnect_interval = 5
    max_reconnect_attempts = 999
    ws_ping_interval = 5
    ws_ping_timeout = 8
