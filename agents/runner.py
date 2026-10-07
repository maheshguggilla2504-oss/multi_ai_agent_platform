import os
import socket
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path


BASE_DIR = Path("generated_projects")
TEST_ENV_DIR = Path("project_test_envs")


# ============================================================
# HELPERS
# ============================================================

def get_project_dir(project_id: str) -> Path:
    return BASE_DIR / project_id


def get_python_executable(project_id: str) -> Path:

    env_dir = (
        TEST_ENV_DIR
        / project_id
        / ".venv"
    )

    if os.name == "nt":
        return env_dir / "Scripts" / "python.exe"

    return env_dir / "bin" / "python"


def find_free_port():

    with socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    ) as sock:

        sock.bind(
            (
                "127.0.0.1",
                0,
            )
        )

        return sock.getsockname()[1]


def check_url(url: str):

    try:

        with urllib.request.urlopen(
            url,
            timeout=3,
        ) as response:

            body = response.read().decode(
                "utf-8",
                errors="replace",
            )

            return {
                "success": True,
                "status_code": response.status,
                "body": body[:1000],
            }

    except Exception as e:

        return {
            "success": False,
            "error": str(e),
        }


# ============================================================
# RUNNER AGENT
# ============================================================

def runner_agent(
    project_id: str,
):

    print("\n" + "=" * 60)
    print("[Runner] Starting generated application")
    print("=" * 60)

    project_dir = get_project_dir(
        project_id
    )

    backend_dir = (
        project_dir / "backend"
    )

    python_exe = get_python_executable(
        project_id
    )

    # --------------------------------------------------------
    # VALIDATE PROJECT
    # --------------------------------------------------------

    if not project_dir.exists():

        return {
            "status": "FAILED",
            "error": (
                "Generated project does not exist."
            ),
        }

    if not backend_dir.exists():

        return {
            "status": "FAILED",
            "error": (
                "Backend directory does not exist."
            ),
        }

    if not (
        backend_dir / "main.py"
    ).exists():

        return {
            "status": "FAILED",
            "error": (
                "backend/main.py does not exist."
            ),
        }

    if not python_exe.exists():

        return {
            "status": "FAILED",
            "error": (
                "Test environment Python was not found."
            ),
        }

    # --------------------------------------------------------
    # FIND PORT
    # --------------------------------------------------------

    port = find_free_port()

    print(
        f"[Runner] Selected port: {port}"
    )

    # --------------------------------------------------------
    # START FASTAPI
    # --------------------------------------------------------

    command = [
        str(python_exe),
        "-m",
        "uvicorn",
        "main:app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
    ]

    print(
        "[Runner] Starting FastAPI..."
    )

    try:

        if os.name == "nt":

            process = subprocess.Popen(
                command,
                cwd=str(backend_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
            )

        else:

            process = subprocess.Popen(
                command,
                cwd=str(backend_dir),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )

    except Exception as e:

        return {
            "status": "FAILED",
            "error": (
                f"Could not start application: {e}"
            ),
        }

    # --------------------------------------------------------
    # WAIT FOR APPLICATION
    # --------------------------------------------------------

    base_url = (
        f"http://127.0.0.1:{port}"
    )

    urls = [
        f"{base_url}/health",
        f"{base_url}/",
    ]

    successful_url = None
    last_error = None

    print(
        "[Runner] Waiting for application..."
    )

    try:

        for _ in range(20):

            # Process already stopped?
            if process.poll() is not None:

                last_error = (
                    "FastAPI process stopped unexpectedly."
                )

                break

            for url in urls:

                result = check_url(url)

                if result["success"]:

                    successful_url = url
                    break

                last_error = result.get(
                    "error"
                )

            if successful_url:
                break

            time.sleep(1)

    except Exception as e:

        last_error = str(e)

    # --------------------------------------------------------
    # RESULT
    # --------------------------------------------------------

    if successful_url:

        print(
            "\n[Runner] Application is running!"
        )

        print(
            f"[Runner] URL: {successful_url}"
        )

        print(
            f"[Runner] PID: {process.pid}"
        )

        print(
            "[Runner] The process will remain running."
        )

        return {
            "status": "RUNNING",
            "url": successful_url,
            "base_url": base_url,
            "port": port,
            "pid": process.pid,
            "message": (
                "Generated FastAPI application "
                "started successfully."
            ),
        }

    # --------------------------------------------------------
    # STARTUP FAILED
    # --------------------------------------------------------

    if process.poll() is None:

        try:
            process.terminate()
            process.wait(timeout=5)

        except Exception:

            try:
                process.kill()
            except Exception:
                pass

    print(
        "[Runner] Application failed to start."
    )

    return {
        "status": "FAILED",
        "error": (
            last_error
            or "Application did not respond."
        ),
    }