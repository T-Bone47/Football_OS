import json

log_path = r"C:\Users\olive\.gemini\antigravity-ide\brain\4e3ce894-a5df-49ac-9a5a-d5fe7a1fc5a8\.system_generated\logs\transcript_full.jsonl"
out_path = r"C:\Users\olive\.gemini\antigravity-ide\brain\81a3bffc-5028-444c-9e30-caff656f67a3\phase_8_master_prompt.txt"

with open(log_path, "r", encoding="utf-8") as f:
    line = f.readline()
    data = json.loads(line)
    content = data.get("content", "")

with open(out_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Saved prompt. Length:", len(content))
