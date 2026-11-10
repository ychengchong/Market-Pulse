"""Cloud entry point: frozen public snapshot, no database or SEC calls."""
from pathlib import Path
import sys

# Streamlit runs from the repository root; this also supports launching from demo/.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import streamlit as st
from src.app import render_app
from src.demo import load_snapshot

try:
    snapshot = load_snapshot()
except (OSError, ValueError, KeyError, TypeError):
    st.error("The saved demo snapshot is missing or invalid. Regenerate it locally with python export_demo.py.")
    st.stop()

render_app(demo=snapshot)
