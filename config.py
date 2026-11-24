"""Read settings from environment/.env locally or Streamlit Secrets in Cloud."""
from __future__ import annotations

import os


def get_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        import streamlit as st
        secret = st.secrets.get(name)
        if secret is not None:
            return str(secret)
    except Exception:
        # Streamlit Secrets is optional when running locally without secrets.toml.
        pass
    return default
