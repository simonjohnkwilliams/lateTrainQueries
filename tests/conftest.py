"""Shared pytest setup.

Puts the project root on sys.path so the ``trainline`` package imports cleanly
in the default (offline) test run. No network or credentials are required by
default (NFR2); live tests are opt-in and skip without HSP_CREDENTIALS_FILE.
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
