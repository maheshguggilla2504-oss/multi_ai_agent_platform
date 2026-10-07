import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "openai/gpt-oss-20b"


def researcher_agent(
    user_request: str,
    project_context: str,
    plan: str,
) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": """
You are a Research Agent.

Return concise bullet points covering only the technical information
needed to build the requested project.

Follow the specified technologies exactly.
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
""".strip(),
            },
        ],
    )

    return response.choices[0].message.content.strip()