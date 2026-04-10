import subprocess
import time
import requests

proc = subprocess.Popen(["uvicorn", "main:app", "--port", "8011"])
time.sleep(3)

try:
    print("Testing clear-queue...")
    r = requests.post("http://127.0.0.1:8011/clear-queue?team_id=finance1")
    print(r.status_code, r.json())
finally:
    proc.terminate()
