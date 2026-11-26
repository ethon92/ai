from __future__ import annotations
from datetime import date
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
load_dotenv()
from config import get_setting
import db

db.init_db()
st.set_page_config(page_title="AI 營運中心", page_icon="🤖", layout="wide", initial_sidebar_state="expanded")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;600;700;800&display=swap');
html,body,[class*="css"] {font-family:'DM Sans','Noto Sans TC',sans-serif}
.stApp{background:#f5f7fb}.block-container{padding-top:4rem;max-width:1440px}
[data-testid="stSidebar"]{background:#111b2e}.sidebar-title{font-size:20px;font-weight:800;color:#fff;padding:4px 8px 28px}
[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p{color:#c2cad8}
.eyebrow{color:#707e93;font-size:12px;font-weight:700;letter-spacing:.13em;text-transform:uppercase}
.page-title{font-size:30px;font-weight:800;color:#17243a;margin:2px 0 4px}.subtle{color:#748197;font-size:14px}
.card{background:#fff;border:1px solid #e8edf4;border-radius:14px;padding:19px 20px;box-shadow:0 3px 12px #17243a06}
.metric-label{font-size:13px;color:#748197}.metric-value{font-size:27px;color:#17243a;font-weight:800;margin-top:5px}.metric-note{font-size:12px;color:#748197;margin-top:5px}
.section{font-size:18px;font-weight:750;color:#17243a;margin:18px 0 12px}.chat-box{background:#fff;border:1px solid #e8edf4;border-radius:14px;padding:20px}
div[data-testid="stMetric"]{background:#fff;border:1px solid #e8edf4;padding:14px 18px;border-radius:14px}
div[data-testid="stMetricLabel"] p{color:#748197}div[data-testid="stMetricValue"]{color:#17243a}
button[kind="primary"]{background:#315ee8;border-color:#315ee8}
</style>""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown('<div class="sidebar-title">AI <span style="color:#7d9cff">營運中心</span></div>', unsafe_allow_html=True)
    page = st.radio("導覽", ["營運總覽", "分校資料助理", "招生總表", "分校查詢"], label_visibility="collapsed")
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)
    provider = get_setting("AI_PROVIDER", "ollama").upper()
    st.caption(f"● 系統運作中　·　AI：{provider}")
    st.caption("分校資料查詢 · Mini ERP")

branches = db.branch_rows()
comparison = db.enrollment_comparison()
today = date.today()

def header(title, subtitle):
    """在頁面上顯示統一格式的標題、副標題與營運標籤。"""
    st.markdown(f'<div class="eyebrow">EDUCATION OPERATIONS</div><div class="page-title">{title}</div><div class="subtle">{subtitle}</div>', unsafe_allow_html=True)

if page == "營運總覽":
    header("營運總覽", f"掌握分校招生表現　·　資料更新 {today.strftime('%Y/%m/%d')}")
    st.write("")
    total = sum(r["current_students"] for r in comparison)
    prev = sum(r["previous_students"] for r in comparison)
    rate = round((total-prev)/prev*100,1) if prev else 0
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("營運分校", f"{len(branches)} 間", "全台模擬據點")
    c2.metric("本月報名", f"{total:,} 筆", f"較前月 {rate:+.1f}%")
    c3.metric("前月報名", f"{prev:,} 筆", "月增減比較基準")
    drops = sum(1 for r in comparison if r["change_pct"] <= -20)
    c4.metric("招生預警", f"{drops} 間", "下降達 20% 的分校")
    left,right=st.columns([1.7,1])
    with left:
        st.markdown('<div class="section">各分校招生變化</div>',unsafe_allow_html=True)
        chart=pd.DataFrame(comparison).sort_values("change_pct")
        chart=chart.set_index("branch_name")[["change_pct"]].rename(columns={"change_pct":"較前月變化（%）"})
        st.bar_chart(chart, color="#5277ed", height=330)
    with right:
        st.markdown('<div class="section">需要留意</div>',unsafe_allow_html=True)
        for row in [r for r in comparison if r["change_pct"] <= -20][:5]:
            st.markdown(f"<div class='card' style='margin-bottom:9px;padding:14px 16px'><b>{row['branch_name']}</b><span style='float:right;color:#d94c55;font-weight:700'>{row['change_pct']}%</span><div class='subtle' style='margin-top:5px'>招生 {row['previous_students']} → {row['current_students']} 人</div></div>",unsafe_allow_html=True)
        if drops == 0: st.success("目前沒有達到預警門檻的分校。")
        st.markdown('<div class="card" style="margin-top:18px"><b>分校明細查詢</b><div class="subtle" style="margin-top:6px">可進一步查看分校資料、學生名冊、報名明細與月度招生統計。</div></div>',unsafe_allow_html=True)

elif page == "分校資料助理":
    header("分校資料助理", "直接用自然語言對談，查詢各分校資料與招生狀況。")
    st.markdown('<div class="section">開始一段營運分析</div>',unsafe_allow_html=True)
    if "chat_history" not in st.session_state:
        st.session_state.chat_history=[{"role":"assistant","content":"您好，我是分校資料助理。您可以直接用自然語言查詢分校基本資料、學生名冊、報名明細或月度招生統計。\n\n例如：「台北中正分校這個月有哪些課程報名？」或「新北有哪些分校？」"}]
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
    prompt=st.chat_input("例如：台北中正分校這個月有哪些課程報名？")
    if prompt:
        st.session_state.chat_history.append({"role":"user","content":prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("正在查詢分校資料…"):
                try:
                    from agent import run_agent
                    result=run_agent(prompt, history=st.session_state.chat_history[:-1])
                    st.markdown(result["answer"])
                    st.caption("執行工具："+"、".join(result["tools"])+f"　·　{result['mode']} 模式")
                    st.session_state.chat_history.append({"role":"assistant","content":result["answer"]})
                except Exception as exc:
                    st.error(f"Agent 執行失敗：{exc}")
    st.caption("對話會保留在目前工作階段；助理只能查詢資料，不會修改 SQLite。")

elif page == "招生總表":
    header("招生總表", "檢視 25 個模擬分校的招生數據。畫面不含學生個人資料。")
    df=pd.DataFrame(comparison).rename(columns={"branch_name":"分校","location":"地區","current_students":"本月報名","previous_students":"前月報名","change_pct":"變化率 %"})
    st.dataframe(df[["分校","地區","前月報名","本月報名","變化率 %"]],use_container_width=True,hide_index=True)
    st.download_button("下載 CSV",df.to_csv(index=False).encode("utf-8-sig"),"branch_enrollment.csv","text/csv")

else:
    header("分校查詢", "選擇分校後，查詢四類 SQLite 營運資料。")
    st.write("")
    branch_options={f"{b['branch_name']}（{b['location']}）":b["branch_id"] for b in branches}
    selected=st.selectbox("選擇分校", list(branch_options))
    branch_id=branch_options[selected]
    detail=db.branch_detail(branch_id)
    tabs=st.tabs(["① 分校基本資料", "② 學生名冊", "③ 報名明細", "④ 月度招生統計"])
    with tabs[0]:
        st.markdown(f"### {detail['branch_name']}")
        a,b=st.columns(2)
        a.metric("學生人數",f"{detail['student_count']} 人")
        b.metric("累計報名筆數",f"{detail['enrollment_count']} 筆")
        st.write(f"**地區：** {detail['location']}　　**分校主管：** {detail['manager']}　　**營運狀態：** {detail['status']}")
    with tabs[1]:
        students=pd.DataFrame(db.branch_students(branch_id))
        st.caption("以下欄位直接對應 students 資料表。")
        st.dataframe(students,use_container_width=True,hide_index=True)
    with tabs[2]:
        st.caption("以下欄位直接對應 enrollments 資料表。調整日期後按「查詢」才會更新結果。")
        query_key=f"enrollment_query_{branch_id}"
        with st.form(f"enrollment_filter_{branch_id}"):
            f1,f2=st.columns(2)
            start=f1.date_input("開始日期",value=date(date.today().year,date.today().month,1),key=f"enrollment_start_{branch_id}")
            end=f2.date_input("結束日期",value=date.today(),key=f"enrollment_end_{branch_id}")
            submitted=st.form_submit_button("查詢",type="primary")
        if submitted:
            if start>end:
                st.session_state.pop(query_key,None)
                st.warning("開始日期需早於或等於結束日期。")
            else:
                st.session_state[query_key]={
                    "start":start.isoformat(), "end":end.isoformat(),
                    "rows":db.branch_enrollments(branch_id,start.isoformat(),end.isoformat())
                }
        result=st.session_state.get(query_key)
        if result:
            rows=result["rows"]
            columns=["enrollment_id","student_id","course_id","branch_id","enrollment_date"]
            enroll_df=pd.DataFrame(rows,columns=columns)
            st.caption(f"查詢期間：{result['start']} 至 {result['end']}")
            st.metric("查詢期間報名",f"{len(rows)} 筆")
            st.dataframe(enroll_df,use_container_width=True,hide_index=True)
        else:
            st.info("請設定日期區間後按「查詢」。")
    with tabs[3]:
        st.caption("每月報名筆數直接依 enrollments.enrollment_date 分組，並可與上方明細逐筆核對。")
        summary=pd.DataFrame(db.branch_monthly_summary(branch_id,6)).rename(columns={"month":"月份","enrollment_count":"報名筆數","unique_students":"學生數"})
        if summary.empty:
            st.info("這間分校目前沒有招生紀錄。")
        else:
            st.dataframe(summary,use_container_width=True,hide_index=True)
            st.bar_chart(summary.sort_values("月份").set_index("月份")[["報名筆數"]],color="#5277ed")

