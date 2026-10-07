from openai import OpenAI
from dotenv import load_dotenv
import os
from agents.planner import planner

# Load .env file
load_dotenv()

# Create OpenRouter client
client = OpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url="https://openrouter.ai/api/v1"
)

# Send a prompt
response = client.chat.completions.create(
    model="openai/gpt-oss-20b:free",
    messages=[
        {
            "role": "user",
            "content": "Hello! Tell me who you are in one sentence."
        }
    ]
)


user_request = input("Enter your project idea: ")

result = planner(user_request)

print("\nPlanner Output:\n")
print(result)

# Print the response
print(response.choices[0].message.content)