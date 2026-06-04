# Crawler Agent Backend

## Run

```bash
cd crawler_agent_backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py
```

Open API docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

## Notes

- Existing `crawler_agent/` code is used via `app/legacy_bridge` and is not modified.
- Dedup behavior:
  - Site quick hash skip
  - Raw html hash duplicate check
  - Normalized content hash duplicate check
