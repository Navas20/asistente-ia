# Task 7: Report Generator

## File
Create: `backend/report_generator.py`

## Functions

### `generate_report(target: str, data: dict, fmt: str = "md") -> dict`
Main entry point. Generates a report file in `data/reports/`. Returns:
```python
{"format": fmt, "filename": str, "path": str, "size": int, "mime": str, "content": str}
```

### `generate_markdown(target, data) -> str`
Markdown report with sections:
- Title: `# Informe de Auditoría — {target}`
- Metadata: Fecha, Duración, Playbook
- For each step in `data["results"]`: `## {label}`, then key-value list
- Findings section if `data["findings"]` present

### `generate_html(target, data) -> str`
HTML with inline CSS (system font, max-width 800px, styled tables). Sections same as markdown but as HTML elements.

### `generate_json(target, data) -> str`
JSON with `{"report": {"target": ..., "generated_at": ..., "data": {...}}}`

### Implementation notes
- Use `data/reports/` directory relative to backend/
- Create dir if not exists
- Filename: `report_{target_sanitized}_{YYYYMMDD_HHMMSS}.{ext}`
- Sanitize target: alphanumeric + `-_.` only
- `content` field truncated to 50000 chars for large reports
- Use only stdlib + json + datetime + pathlib

## Global Constraints
- Windows compatible
- Python 3.10+
- Spanish text
- Importable without side effects
