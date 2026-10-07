def reviewer_agent(
    user_request="",
    project_context="",
    plan="",
    research="",
    developer_output="",
    coder_output="",
    test_result=None,
    project_id=None,
) -> dict:
    tester_status = "UNKNOWN"
    errors = []

    if isinstance(test_result, dict):
        tester_status = str(
            test_result.get(
                "overall",
                test_result.get("status", "UNKNOWN"),
            )
        ).upper()
        errors = test_result.get("errors", [])

    elif isinstance(test_result, str):
        tester_status = test_result.upper()

    if tester_status != "PASSED":
        return {
            "decision": "NEEDS_REVISION",
            "status": "NEEDS_REVISION",
            "explanation": "Tester reported a failure.",
            "problems": errors or ["Tester reported FAILED."],
        }

    return {
        "decision": "APPROVED",
        "status": "APPROVED",
        "explanation": (
            "Automated validation passed. "
            "Project approved for startup."
        ),
        "problems": [],
    }