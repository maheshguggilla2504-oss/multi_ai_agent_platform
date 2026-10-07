from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph

from agents.coder import coder_agent
from agents.developer import developer_agent
from agents.planner import planner_agent
from agents.researcher import researcher_agent
from agents.reviewer import reviewer_agent
from agents.runner import runner_agent
from agents.tester import tester_agent

MAX_CODER_ATTEMPTS = 3


class WorkflowState(TypedDict, total=False):
    project_id: str
    user_request: str
    project_context: str
    plan: Any
    research: Any
    developer_output: Any
    coder_output: Any
    test_result: Any
    review: Any
    runner_result: Any
    application_url: str
    revision_count: int
    workflow_status: str


def planner_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("PLANNER")
    print("=" * 60)

    return {
        "plan": planner_agent(
            user_request=state.get("user_request", ""),
            project_context=state.get("project_context", ""),
        )
    }


def researcher_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("RESEARCHER")
    print("=" * 60)

    return {
        "research": researcher_agent(
            user_request=state.get("user_request", ""),
            project_context=state.get("project_context", ""),
            plan=state.get("plan", ""),
        )
    }


def developer_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("DEVELOPER")
    print("=" * 60)

    return {
        "developer_output": developer_agent(
            user_request=state.get("user_request", ""),
            project_context=state.get("project_context", ""),
            plan=state.get("plan", ""),
            research=state.get("research", ""),
        )
    }


def coder_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("CODER")
    print("=" * 60)

    attempt = state.get("revision_count", 0) + 1
    print(f"Coder attempt: {attempt}/{MAX_CODER_ATTEMPTS}")

    result = coder_agent(
        project_id=state["project_id"],
        user_request=state.get("user_request", ""),
        project_context=state.get("project_context", ""),
        plan=state.get("plan", ""),
        research=state.get("research", ""),
        developer_output=state.get("developer_output", ""),
        test_result=state.get("test_result", {}),
        review=state.get("review", {}),
        runner_result=state.get("runner_result", {}),
        revision_count=attempt,
    )

    return {
        "coder_output": result,
        "revision_count": attempt,
    }


def tester_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("TESTER")
    print("=" * 60)

    return {
        "test_result": tester_agent(
            project_id=state["project_id"],
            coder_output=state.get("coder_output", {}),
        )
    }


def reviewer_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("REVIEWER")
    print("=" * 60)

    return {
        "review": reviewer_agent(
            user_request=state.get("user_request", ""),
            project_context=state.get("project_context", ""),
            plan=state.get("plan", ""),
            research=state.get("research", ""),
            developer_output=state.get("developer_output", ""),
            coder_output=state.get("coder_output", {}),
            test_result=state.get("test_result", {}),
            project_id=state.get("project_id"),
        )
    }


def review_router(state: WorkflowState):
    review = state.get("review", {})
    decision = str(
        review.get("decision", "") if isinstance(review, dict) else review
    ).upper()

    if decision == "APPROVED":
        return "runner"

    if decision == "NEEDS_REVISION":
        if state.get("revision_count", 0) < MAX_CODER_ATTEMPTS:
            return "coder"
        return "finish"

    return "finish"


def runner_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("RUNNER")
    print("=" * 60)

    result = runner_agent(
        project_id=state["project_id"],
    )

    application_url = ""
    if isinstance(result, dict):
        application_url = result.get("url", result.get("base_url", ""))

    return {
        "runner_result": result,
        "application_url": application_url,
    }


def runner_router(state: WorkflowState):
    result = state.get("runner_result", {})
    status = str(
        result.get("status", "") if isinstance(result, dict) else result
    ).upper()

    if status == "RUNNING":
        return "finish"

    if status in {"FAILED", "ERROR"}:
        if state.get("revision_count", 0) < MAX_CODER_ATTEMPTS:
            return "coder"

    return "finish"


def finish_node(state: WorkflowState):
    print("\n" + "=" * 60)
    print("WORKFLOW FINISHED")
    print("=" * 60)

    review = state.get("review", {})
    decision = str(
        review.get("decision", "") if isinstance(review, dict) else review
    ).upper()

    runner_result = state.get("runner_result", {})
    runner_status = str(
        runner_result.get("status", "")
        if isinstance(runner_result, dict)
        else runner_result
    ).upper()

    if decision == "APPROVED" and runner_status == "RUNNING":
        status = "COMPLETED"
    elif decision == "APPROVED":
        status = "APPROVED"
    elif decision == "NEEDS_REVISION":
        status = "FAILED"
    else:
        status = "FAILED"

    print(f"Workflow status: {status}")
    print(f"Coder attempts: {state.get('revision_count', 0)}")
    print(f"Application: {state.get('application_url', '')}")

    return {"workflow_status": status}


workflow = StateGraph(WorkflowState)

workflow.add_node("planner", planner_node)
workflow.add_node("researcher", researcher_node)
workflow.add_node("developer", developer_node)
workflow.add_node("coder", coder_node)
workflow.add_node("tester", tester_node)
workflow.add_node("reviewer", reviewer_node)
workflow.add_node("runner", runner_node)
workflow.add_node("finish", finish_node)

workflow.add_edge(START, "planner")
workflow.add_edge("planner", "researcher")
workflow.add_edge("researcher", "developer")
workflow.add_edge("developer", "coder")
workflow.add_edge("coder", "tester")
workflow.add_edge("tester", "reviewer")

workflow.add_conditional_edges(
    "reviewer",
    review_router,
    {
        "runner": "runner",
        "coder": "coder",
        "finish": "finish",
    },
)

workflow.add_conditional_edges(
    "runner",
    runner_router,
    {
        "coder": "coder",
        "finish": "finish",
    },
)

workflow.add_edge("finish", END)

app = workflow.compile()


if __name__ == "__main__":
    user_request = input("\nEnter your project request: ").strip()

    if not user_request:
        raise SystemExit("No project request provided.")

    initial_state: WorkflowState = {
        "project_id": "weather_demo_001",
        "user_request": user_request,
        "project_context": """
Frontend: Flutter
Backend: FastAPI
Database: PostgreSQL
Cache: Redis
Containerization: Docker
Cloud: AWS
""".strip(),
        "plan": "",
        "research": "",
        "developer_output": "",
        "coder_output": {},
        "test_result": {},
        "review": {},
        "runner_result": {},
        "application_url": "",
        "revision_count": 0,
        "workflow_status": "STARTING",
    }

    final_state = app.invoke(initial_state)

    print("\n" + "=" * 60)
    print("FINAL RESULT")
    print("=" * 60)
    print(f"Status: {final_state.get('workflow_status', 'UNKNOWN')}")
    print(f"Attempts: {final_state.get('revision_count', 0)}")
    print(f"Application: {final_state.get('application_url', '')}")