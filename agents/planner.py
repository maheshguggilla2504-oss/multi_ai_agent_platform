import os

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1",
)

MODEL = "openai/gpt-oss-20b"


def planner_agent(user_request: str, project_context: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0,
        messages=[
            {
                "role": "system",
                "content": """
You are a Planner Agent.

Return only a numbered list of 5 to 8 concise development tasks.
Follow the stated technology constraints exactly.
Do not write code or explanations.
""".strip(),
            },
            {
                "role": "user",
                "content": f"""
Project requirement:
{user_request}

Technology constraints:
{project_context}
""".strip(),
            },
        ],
    )

    return response.choices[0].message.content.strip()