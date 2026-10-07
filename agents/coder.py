import json
import os
import shutil
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "openai/gpt-oss-20b"
BASE_DIR = Path("generated_projects")
MAX_ROUNDS = 30

REQUIRED_FILES = [
    "backend/requirements.txt",
    "backend/main.py",
    "backend/tests/test_main.py",
    "backend/Dockerfile",
    "frontend/pubspec.yaml",
    "frontend/lib/main.dart",
    "frontend/Dockerfile",
    "docker-compose.yml",
    "README.md",
    ".gitignore",
]


def get_project_dir(project_id: str) -> Path:
    project_dir = (BASE_DIR / project_id).resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def safe_path(project_dir: Path, file_path: str) -> Path:
    path = (project_dir / file_path).resolve()

    try:
        path.relative_to(project_dir)
    except ValueError:
        raise ValueError("Unsafe file path.")

    return path


def get_existing_files(project_id: str) -> list[str]:
    project_dir = get_project_dir(project_id)

    return sorted(
        str(path.relative_to(project_dir)).replace("\\", "/")
        for path in project_dir.rglob("*")
        if path.is_file()
    )


def get_missing_files(project_id: str) -> list[str]:
    existing = set(get_existing_files(project_id))

    return [
        required_file
        for required_file in REQUIRED_FILES
        if required_file not in existing
    ]


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Create or replace a file in the generated project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative project file path.",
                    },
                    "content": {
                        "type": "string",
                        "description": "Complete file contents.",
                    },
                },
                "required": ["file_path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a file from the generated project.",
            "parameters": {
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Relative project file path.",
                    },
                },
                "required": ["file_path"],
            },
        },
    },
]


def normalize_tool_name(tool_name: str) -> str:
    tool_name = str(tool_name or "").strip()

    if tool_name.startswith("write_file"):
        return "write_file"

    if tool_name.startswith("read_file"):
        return "read_file"

    return tool_name


def execute_tool(
    project_id: str,
    tool_name: str,
    arguments: dict,
) -> dict:
    project_dir = get_project_dir(project_id)
    tool_name = normalize_tool_name(tool_name)

    try:
        if tool_name == "write_file":
            file_path = arguments.get("file_path")
            content = arguments.get("content")

            if not file_path:
                return {
                    "status": "error",
                    "message": "write_file requires file_path.",
                }

            if content is None:
                return {
                    "status": "error",
                    "message": "write_file requires content.",
                }

            path = safe_path(project_dir, file_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")

            return {
                "status": "success",
                "message": f"File written: {file_path}",
            }

        if tool_name == "read_file":
            file_path = arguments.get("file_path")

            if not file_path:
                return {
                    "status": "error",
                    "message": "read_file requires file_path.",
                }

            path = safe_path(project_dir, file_path)

            if not path.is_file():
                return {
                    "status": "error",
                    "message": f"File does not exist: {file_path}",
                }

            return {
                "status": "success",
                "file_path": file_path,
                "content": path.read_text(
                    encoding="utf-8",
                    errors="replace",
                ),
            }

        return {
            "status": "error",
            "message": f"Unknown tool: {tool_name}",
        }

    except Exception as error:
        return {
            "status": "error",
            "message": str(error),
        }


def coder_agent(
    project_id: str,
    user_request: str,
    project_context: str,
    plan: str,
    research: str,
    developer_output: str,
    test_result=None,
    review=None,
    runner_result=None,
    revision_count: int = 1,
) -> dict:
    project_dir = get_project_dir(project_id)

    if revision_count == 1:
        for item in project_dir.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

    revision = revision_count > 1

    system_prompt = """
You are the Coder Agent.

Build the project by calling write_file tools.

Do not only explain code.
Do not return code in chat.
Use write_file repeatedly until every required file exists.

Required files:

1. backend/requirements.txt
2. backend/main.py
3. backend/tests/test_main.py
4. backend/Dockerfile
5. frontend/pubspec.yaml
6. frontend/lib/main.dart
7. frontend/Dockerfile
8. docker-compose.yml
9. README.md
10. .gitignore

Rules:

- Backend must use FastAPI and Uvicorn.
- backend/main.py must expose GET / and GET /health.
- Root endpoint must work without external APIs, PostgreSQL, Redis, or AWS.
- requirements.txt must include fastapi, uvicorn, pytest, pytest-asyncio, and httpx.
- Tests must use modern HTTPX ASGITransport.
- Tests must not call external APIs.
- Create a minimal valid Flutter app.
- Create Docker files and docker-compose.yml.
- Create README.md and .gitignore.
- Never write files outside the generated project.
""".strip()

    if revision:
        system_prompt += """

This is a revision.

Read the relevant files only when necessary.
Fix the reported failure by using write_file.
Do not rebuild working files unnecessarily.
""".strip()

    user_prompt = f"""
User request:
{user_request}

Technology constraints:
{project_context}

Plan:
{plan}

Research:
{research}

Developer output:
{developer_output}

Existing files:
{get_existing_files(project_id)}

Missing required files:
{get_missing_files(project_id)}

Previous test result:
{test_result}

Previous review:
{review}

Previous runner result:
{runner_result}
""".strip()

    messages = [
        {
            "role": "system",
            "content": system_prompt,
        },
        {
            "role": "user",
            "content": user_prompt,
        },
    ]

    write_count = 0

    for round_number in range(1, MAX_ROUNDS + 1):
        missing_files = get_missing_files(project_id)

        if not missing_files and write_count > 0:
            break

        print(f"[Coder] Round {round_number}/{MAX_ROUNDS}")

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="required",
                temperature=0,
            )
        except Exception as error:
            return {
                "status": "FAILED",
                "message": f"Coder API error: {error}",
                "files": get_existing_files(project_id),
                "missing_files": get_missing_files(project_id),
            }

        message = response.choices[0].message

        if not message.tool_calls:
            messages.append(
                {
                    "role": "assistant",
                    "content": message.content or "",
                }
            )
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Use write_file now. "
                        f"These files are still missing: {missing_files}"
                    ),
                }
            )
            continue

        messages.append(
            {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                    for call in message.tool_calls
                ],
            }
        )

        for tool_call in message.tool_calls:
            original_tool_name = tool_call.function.name
            tool_name = normalize_tool_name(original_tool_name)

            try:
                arguments = json.loads(
                    tool_call.function.arguments
                )
            except json.JSONDecodeError:
                arguments = {}

            result = execute_tool(
                project_id=project_id,
                tool_name=tool_name,
                arguments=arguments,
            )

            if tool_name == "write_file" and result["status"] == "success":
                write_count += 1

            print(
                f"[Coder] {tool_name}: "
                f"{result.get('message', result['status'])}"
            )

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": json.dumps(result),
                }
            )

    missing_files = get_missing_files(project_id)

    return {
        "status": "COMPLETED" if not missing_files else "INCOMPLETE",
        "message": "Coder finished project generation.",
        "files": get_existing_files(project_id),
        "missing_files": missing_files,
        "revision_count": revision_count,
    }