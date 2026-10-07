import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECTS_DIR = Path("generated_projects")
TEST_ENVS_DIR = Path("project_test_envs")

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
    return (PROJECTS_DIR / project_id).resolve()


def get_python(project_id: str) -> Path:
    venv = (TEST_ENVS_DIR / project_id / ".venv").resolve()

    if os.name == "nt":
        return venv / "Scripts" / "python.exe"

    return venv / "bin" / "python"


def run(command, cwd=None, timeout=180, env=None) -> dict:
    try:
        result = subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        return {
            "returncode": result.returncode,
            "output": ((result.stdout or "") + (result.stderr or "")).strip(),
        }

    except subprocess.TimeoutExpired:
        return {"returncode": -1, "output": "Command timed out."}
    except Exception as error:
        return {"returncode": -1, "output": str(error)}


def find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def create_environment(project_id: str) -> dict:
    python = get_python(project_id)

    if python.exists():
        return {"status": "PASSED", "python": python}

    python.parent.parent.mkdir(parents=True, exist_ok=True)

    result = run(
        [sys.executable, "-m", "venv", str(python.parent.parent)],
        timeout=120,
    )

    if result["returncode"] != 0 or not python.exists():
        return {"status": "FAILED", "error": result["output"]}

    return {"status": "PASSED", "python": python}


def install_dependencies(project_dir: Path, python: Path) -> dict:
    requirements = project_dir / "backend" / "requirements.txt"

    result = run(
        [str(python), "-m", "pip", "install", "-r", str(requirements)],
        cwd=project_dir,
        timeout=300,
    )

    if result["returncode"] != 0:
        return {"status": "FAILED", "error": result["output"]}

    result = run(
        [
            str(python),
            "-m",
            "pip",
            "install",
            "pytest",
            "pytest-asyncio",
            "httpx",
        ],
        cwd=project_dir,
        timeout=180,
    )

    if result["returncode"] != 0:
        return {"status": "FAILED", "error": result["output"]}

    return {"status": "PASSED"}


def fix_httpx_tests(project_dir: Path) -> None:
    tests_dir = project_dir / "backend" / "tests"

    for test_file in tests_dir.rglob("*.py"):
        content = test_file.read_text(encoding="utf-8")

        if "AsyncClient(app=app" not in content:
            continue

        if "from httpx import AsyncClient" in content:
            content = content.replace(
                "from httpx import AsyncClient",
                "from httpx import ASGITransport, AsyncClient",
            )

        content = re.sub(
            r"AsyncClient\(\s*app\s*=\s*app\s*,\s*base_url\s*=\s*([^)]+)\)",
            r"AsyncClient(transport=ASGITransport(app=app), base_url=\1)",
            content,
        )

        test_file.write_text(content, encoding="utf-8")
        print(f"[Tester] Updated incompatible httpx test: {test_file}")


def run_runtime_check(project_dir: Path, python: Path) -> dict:
    backend_dir = project_dir / "backend"
    port = find_free_port()

    process = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(backend_dir),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    url = f"http://127.0.0.1:{port}/health"
    error = "Application did not respond."

    try:
        for _ in range(15):
            if process.poll() is not None:
                error = "FastAPI process stopped unexpectedly."
                break

            try:
                import urllib.request

                with urllib.request.urlopen(url, timeout=2) as response:
                    if response.status < 500:
                        return {"status": "PASSED", "url": url}
            except Exception as request_error:
                error = str(request_error)

            time.sleep(1)

        return {"status": "FAILED", "error": error}

    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


def tester_agent(project_id: str, coder_output=None) -> dict:
    project_dir = get_project_dir(project_id)

    if not project_dir.is_dir():
        return {"overall": "FAILED", "errors": ["Generated project does not exist."]}

    missing = [
        path for path in REQUIRED_FILES
        if not (project_dir / path).is_file()
    ]

    if missing:
        return {
            "overall": "FAILED",
            "errors": [f"Missing files: {', '.join(missing)}"],
            "missing": missing,
        }

    environment = create_environment(project_id)
    if environment["status"] != "PASSED":
        return {
            "overall": "FAILED",
            "errors": [environment.get("error", "Could not create test environment.")],
        }

    python = environment["python"]
    dependencies = install_dependencies(project_dir, python)

    if dependencies["status"] != "PASSED":
        return {
            "overall": "FAILED",
            "errors": [dependencies.get("error", "Dependency installation failed.")],
        }

    backend_dir = project_dir / "backend"
    python_files = list(backend_dir.rglob("*.py"))

    syntax = run(
        [str(python), "-m", "py_compile", *[str(file) for file in python_files]],
        cwd=project_dir,
    )

    if syntax["returncode"] != 0:
        return {"overall": "FAILED", "errors": [syntax["output"]]}

    fix_httpx_tests(project_dir)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        [str(project_dir), str(backend_dir)]
    )

    pytest = run(
        [str(python), "-m", "pytest", "backend/tests", "-q"],
        cwd=project_dir,
        env=env,
        timeout=120,
    )

    if pytest["returncode"] != 0:
        return {"overall": "FAILED", "errors": ["Pytest failed.", pytest["output"]]}

    runtime = run_runtime_check(project_dir, python)

    if runtime["status"] != "PASSED":
        return {
            "overall": "FAILED",
            "errors": [runtime.get("error", "Runtime check failed.")],
        }

    docker_files = [
        "backend/Dockerfile",
        "frontend/Dockerfile",
        "docker-compose.yml",
    ]

    missing_docker = [
        path for path in docker_files
        if not (project_dir / path).is_file()
    ]

    if missing_docker:
        return {
            "overall": "FAILED",
            "errors": [f"Missing Docker files: {', '.join(missing_docker)}"],
        }

    return {
        "overall": "PASSED",
        "structure": {"status": "PASSED"},
        "dependencies": {"status": "PASSED"},
        "syntax": {"status": "PASSED"},
        "pytest": {"status": "PASSED", "output": pytest["output"]},
        "runtime": runtime,
        "docker": {"status": "PASSED"},
    }