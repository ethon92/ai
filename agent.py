"""Conversational LangGraph agent for read-only branch data queries."""
from __future__ import annotations

import json
import os
from typing import Annotated, TypedDict

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

import db
from config import get_setting

SYSTEM = """你是教育機構的分校資料助理，使用繁體中文與使用者自然對談。
依照使用者問題，呼叫下列唯讀資料工具取得 SQLite 中的分校資料，再清楚回答。可處理分校基本資料、學生名冊、報名明細、課程、月度招生統計，以及跨分校招生比較。
若分校名稱不明確，先用 search_branches 搜尋並詢問使用者選擇；不可猜測分校。可利用對話歷史解析「那間分校」「上個月」等追問。
日期請使用 YYYY-MM-DD。報名明細依要求使用日期及課程篩選，並簡潔說明資料筆數與限制。
不得執行 SQL、建立/修改/刪除資料、建立任務或核准流程。名冊工具不回傳電話，不要索取或推測個人聯絡資訊。
若查無資料，明確說明查詢條件並建議可用的篩選方式。回答數值時以工具結果為準，不編造。"""


def _json(value) -> str:
    return json.dumps(value, ensure_ascii=False, default=str)


@tool
def search_branches(keyword: str = "", location: str = "") -> str:
    """依分校名稱、主管姓名或地區搜尋分校。keyword 可使用名稱片段。"""
    return _json(db.search_branches(keyword, location))


@tool
def get_branch_profile(branch_id: int) -> str:
    """查詢分校基本資料、學生人數及累計報名筆數。先用 search_branches 取得 branch_id。"""
    return _json(db.branch_detail(branch_id))


@tool
def get_branch_students(branch_id: int, limit: int = 50) -> str:
    """查詢分校學生名冊，只含學生編號與姓名，不含電話。最多回傳 100 筆。"""
    rows = db.branch_students(branch_id)[:max(1, min(limit, 100))]
    return _json({"count_returned": len(rows), "students": rows})


@tool
def get_branch_enrollments(branch_id: int, start_date: str = "", end_date: str = "",
                           course_name: str = "", limit: int = 50) -> str:
    """查詢分校報名明細，可依日期區間與課程名稱篩選；不回傳學生個資。日期格式 YYYY-MM-DD。"""
    rows = db.branch_enrollments(branch_id, start_date or None, end_date or None,
                                 course_name, max(1, min(limit, 100)))
    # Do not send student names to the model; enrollment facts are sufficient for analysis.
    public_rows = [{k: row[k] for k in ("enrollment_id", "enrollment_date", "course_name", "branch_name")} for row in rows]
    return _json({"count_returned": len(public_rows), "limit": max(1, min(limit, 100)), "enrollments": public_rows})


@tool
def get_branch_monthly_summary(branch_id: int, months: int = 6) -> str:
    """查詢分校最近數月的報名筆數與學生數。"""
    return _json(db.branch_monthly_summary(branch_id, max(1, min(months, 12))))


@tool
def compare_branch_enrollment() -> str:
    """比較所有分校最新資料月份與前一月份的招生人數及變化率。"""
    return _json(db.enrollment_comparison())


TOOLS = [search_branches, get_branch_profile, get_branch_students,
         get_branch_enrollments, get_branch_monthly_summary, compare_branch_enrollment]


class State(TypedDict):
    messages: Annotated[list, add_messages]


def _make_model():
    provider = get_setting("AI_PROVIDER", "ollama").lower()
    if provider == "openrouter":
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            model=get_setting("OPENROUTER_MODEL", "openrouter/free"),
            api_key=get_setting("OPENROUTER_API_KEY"),
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
        )
    elif provider == "ollama":
        from langchain_ollama import ChatOllama
        model = ChatOllama(model=get_setting("OLLAMA_MODEL", "qwen2.5:7b"),
                           base_url=get_setting("OLLAMA_BASE_URL", "http://localhost:11434"), temperature=0)
    elif provider == "demo":
        return None
    else:
        raise ValueError("AI_PROVIDER 請設定為 demo、ollama 或 openrouter。")
    return model.bind_tools(TOOLS)


def run_agent(question: str, history: list[dict] | None = None) -> dict:
    model = _make_model()
    if model is None:
        return _run_demo(question)

    def assistant(state: State):
        return {"messages": [model.invoke([SystemMessage(content=SYSTEM), *state["messages"]])]}

    def route(state: State):
        return "tools" if getattr(state["messages"][-1], "tool_calls", None) else END

    from langgraph.prebuilt import ToolNode
    graph = StateGraph(State)
    graph.add_node("assistant", assistant)
    graph.add_node("tools", ToolNode(TOOLS))
    graph.add_edge(START, "assistant")
    graph.add_conditional_edges("assistant", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "assistant")

    messages = []
    for item in (history or [])[-12:]:
        content = item.get("content", "")
        if not content:
            continue
        if item.get("role") == "user":
            messages.append(HumanMessage(content=content))
        elif item.get("role") == "assistant":
            messages.append(AIMessage(content=content))
    messages.append(HumanMessage(content=question))
    result = graph.compile().invoke({"messages": messages}, {"recursion_limit": 16})
    answer = result["messages"][-1].content
    called = [call["name"] for message in result["messages"] for call in getattr(message, "tool_calls", [])]
    return {"answer": answer, "tools": called, "mode": get_setting("AI_PROVIDER", "demo")}


def _run_demo(question: str) -> dict:
    """Offline fallback. Full natural-language interpretation requires an LLM provider."""
    rows = db.enrollment_comparison()
    falling = [r for r in rows if r["previous_students"] and r["change_pct"] <= -20]
    if any(word in question for word in ("比較", "全部", "所有", "下降", "招生")):
        answer = "各分校最近月份招生比較：\n" + "\n".join(
            f"- {r['branch_name']}：{r['previous_students']} → {r['current_students']} 人（{r['change_pct']:+.1f}%）"
            for r in rows[:10])
        if len(rows) > 10:
            answer += f"\n（共 {len(rows)} 間分校；示範模式顯示前 10 間。）"
        tools = ["compare_branch_enrollment"]
    else:
        matches = [b for b in db.branch_rows() if b["branch_name"] in question]
        if matches:
            branch = matches[0]
            profile = db.branch_detail(branch["branch_id"])
            answer = (f"{profile['branch_name']}（{profile['location']}）\n"
                      f"主管：{profile['manager']}；狀態：{profile['status']}\n"
                      f"學生：{profile['student_count']} 人；累計報名：{profile['enrollment_count']} 筆。")
            tools = ["get_branch_profile"]
        elif falling:
            answer = "示範模式只能處理簡單關鍵字查詢。若要用自然語言連續查詢分校明細，請在 .env 設定 AI_PROVIDER=ollama 或 openrouter。\n\n"
            answer += "目前招生下降達 20% 的分校：\n" + "\n".join(
                f"- {r['branch_name']}：{r['change_pct']}%" for r in falling[:5])
            tools = ["compare_branch_enrollment"]
        else:
            answer = "目前使用離線示範模式。請設定 Ollama 或雲端模型，啟用完整自然語言對談與分校查詢。"
            tools = []
    return {"answer": answer, "tools": tools, "mode": "demo"}
