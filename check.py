import os
from openai import OpenAI
from dotenv import load_dotenv
load_dotenv(r"D:\study-buddy\.env")

client = OpenAI(base_url="https://developer.amd.com.cn/radeon/api/v1",
                api_key=os.environ["RADEON_API_KEY"])
print([m.id for m in client.models.list().data])
r = client.chat.completions.create(
    model="MiMo-V2.6-Flash", reasoning_effort="none",
    messages=[{"role": "user", "content": "Say hello in one sentence."}])
print(r.choices[0].message.content)