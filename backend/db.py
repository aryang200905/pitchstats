"""Shared MySQL connection config for the PitchStats backend.

The local MySQL 8.0 server listens on the Unix socket /tmp/mysql.sock
(TCP on 3306 is disabled on this machine), so we connect via the socket.
"""
import mysql.connector

DB_CONFIG = {
    "unix_socket": "/tmp/mysql.sock",
    "user": "root",
    "password": "pitchstats",
    "database": "pitchstats",
}


def get_connection(with_db=True):
    cfg = dict(DB_CONFIG)
    if not with_db:
        cfg.pop("database", None)
    return mysql.connector.connect(**cfg)
