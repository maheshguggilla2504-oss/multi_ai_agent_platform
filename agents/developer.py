import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "openai/gpt-oss-20b"


def developer_agent(
    user_request: str,
    project_context: str,
    plan: str,
    research: str,
) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": """
You are a Developer Agent.

Return concise implementation bullet points covering architecture,
backend, frontend, APIs, data, tests, Docker, and deployment.

Follow technology constraints exactly.
Do not write code.
Do not invent requirements.
""".strip(),
            },
            {
                "role": "user",
                "content": f"""
Project requirement:
{user_request}

Technology constraints:
{project_context}

Plan:
{plan}

Research:
{research}
""".strip(),
            },
        ],
    )

    return response.choices[0].message.content.strip()