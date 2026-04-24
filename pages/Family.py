# Family.py（已整合：持股分布 台股 / 美股）

import streamlit as st
import pandas as pd
import plotly.express as px
import numpy as np

def to_num(s):
    return pd.to_numeric(s, errors="coerce").fillna(0)

def _filter_trade_like_rows(df):
    return df.copy()

def make_holding_distribution_pie_by_market(df, market):
    df = _filter_trade_like_rows(df)

    if "分類" not in df.columns:
        return None

    df["分類"] = df["分類"].astype(str).str.strip()

    if market == "台股":
        df = df[df["分類"].isin(["台股", "台股 ETF"])]
    elif market == "美股":
        df = df[df["分類"] == "美股"]
    else:
        return None

    if df.empty or "參考現值" not in df.columns:
        return None

    df["參考現值"] = to_num(df["參考現值"])
    df = df[df["參考現值"] > 0]

    if df.empty:
        return None

    name_col = "股票名稱" if "股票名稱" in df.columns else "股票"
    df["標的"] = df[name_col].astype(str)

    agg = df.groupby("標的")["參考現值"].sum().reset_index()

    fig = px.pie(
        agg,
        names="標的",
        values="參考現值",
        title=f"持股分布（{market}）"
    )
    fig.update_traces(textposition="inside", textinfo="percent+label")
    fig.update_layout(height=500)

    return fig
