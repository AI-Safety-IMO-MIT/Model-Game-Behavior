# AI Model Game Behavior

## Quick Start
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirement.txt
```
Put your API keys in .env
```bash
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-proj-...
```


## Run Tests
```bash
pytest % run only free tests.
pytest -m "live" % run tests that cost money.
pytest -m "" % run all tests. Cost tokens.
```

## Misc
- [Idea list](https://docs.google.com/document/d/1T7n6WZ_1W7CG9IisZZOa8fEgd6eNLnnIdzyER3fmkDI/edit?tab=t.0)
