"""Read settings from environment/.env locally or Streamlit Secrets in Cloud."""
from __future__ import annotations

import os


def get_setting(name: str, default: str = "") -> str:
    """依序從環境變數、Streamlit Secrets 讀取設定，找不到時回傳預設值。"""
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
