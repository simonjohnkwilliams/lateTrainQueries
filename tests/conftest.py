"""Shared pytest setup.

TestFileGenerator.py does `from LateObject import LateObject` and `from TrainLine
import JsonArgs`, so both the project root and the TrainLine/ folder need to be
on sys.path for the tests to import the source modules directly.
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
TRAINLINE_DIR = os.path.join(PROJECT_ROOT, "TrainLine")

for path in (PROJECT_ROOT, TRAINLINE_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)
