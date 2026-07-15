
from litellm import completion

response = completion(
    # model="github_copilot/gpt-4o",
    # model="github_copilot/gpt-4.1",
    model="github_copilot/gpt-5.1",
    messages=[
        {"role": "system", "content": "You are a helpful coding assistant"},
        {"role": "user", "content": "Write a Python function to calculate fibonacci numbers"}
    ]
)
print(response)


