import json
json_content = """{
  "plano_id": "123",
  "componentes": [
    {"a": 1},
    {"b": 2}"""
if json_content.strip().endswith("}"):
    print(json.loads(json_content + '], "confidence_score": 0.5}'))
