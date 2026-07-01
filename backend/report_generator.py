import json
import logging
import re
from datetime import datetime
from pathlib import Path

log = logging.getLogger("artenisa.report")

REPORTS_DIR = Path(__file__).parent / "data" / "reports"

MIME_MAP = {"md": "text/markdown", "html": "text/html", "json": "application/json"}

MAX_CONTENT_LENGTH = 50_000


def _sanitize(target: str) -> str:
    return re.sub(r"[^\w.\-]", "_", target)


def _ts() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def generate_report(target: str, data: dict, fmt: str = "md") -> dict:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ext = fmt
    filename = f"report_{_sanitize(target)}_{_ts()}.{ext}"
    path = REPORTS_DIR / filename

    generators = {"md": generate_markdown, "html": generate_html, "json": generate_json}
    gen = generators.get(fmt)
    if gen is None:
        raise ValueError(f"Formato no soportado: {fmt}. Usa: md, html, json")
    content = gen(target, data)

    path.write_text(content, encoding="utf-8")
    size = path.stat().st_size

    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH]

    return {
        "format": fmt,
        "filename": filename,
        "path": str(path),
        "size": size,
        "mime": MIME_MAP.get(fmt, "text/plain"),
        "content": content,
    }


def generate_markdown(target: str, data: dict) -> str:
    lines = [f"# Informe de Auditoría — {target}", ""]
    metadata = data.get("metadata", {})
    if metadata:
        lines.append(f"**Fecha:** {metadata.get('date', 'N/A')}")
        lines.append(f"**Duración:** {metadata.get('duration', 'N/A')}")
        lines.append(f"**Playbook:** {metadata.get('playbook', data.get('playbook', 'N/A'))}")
        lines.append("")

    for step in data.get("results", []):
        label = step.get("label", "Paso")
        lines.append(f"## {label}")
        result = step.get("result", {})
        if isinstance(result, dict):
            for k, v in result.items():
                friendly = k.replace("_", " ").capitalize()
                lines.append(f"- **{friendly}:** {v}")
        elif isinstance(result, list):
            for item in result:
                lines.append(f"- {item}")
        else:
            lines.append(f"{result}")
        lines.append("")

    findings = data.get("findings")
    if findings:
        lines.append("## Hallazgos")
        if isinstance(findings, list):
            for f in findings:
                lines.append(f"- {f}")
        else:
            lines.append(f"{findings}")
        lines.append("")

    return "\n".join(lines)


def generate_html(target: str, data: dict) -> str:
    md = generate_markdown(target, data)

    body = []
    in_list = False
    for line in md.split("\n"):
        if line.startswith("# "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h1>{line[2:]}</h1>")
        elif line.startswith("## "):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("**") and line.endswith("**"):
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<p>{line}</p>")
        elif line.startswith("- **"):
            if in_list:
                body.append("</ul>")
                in_list = False
            m = re.match(r"- \*\*(.+?):\*\* (.+)", line)
            if m:
                body.append(f"<p><strong>{m.group(1)}:</strong> {m.group(2)}</p>")
            else:
                body.append(f"<p>{line[2:]}</p>")
        elif line.startswith("- "):
            if not in_list:
                body.append("<ul>")
                in_list = True
            body.append(f"<li>{line[2:]}</li>")
        elif line == "":
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append("")
        else:
            if in_list:
                body.append("</ul>")
                in_list = False
            body.append(f"<p>{line}</p>")
    if in_list:
        body.append("</ul>")

    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Informe de Auditoría — {target}</title>
<style>
  body {{ font-family: system-ui, -apple-system, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; line-height: 1.6; color: #1a1a1a; }}
  h1 {{ border-bottom: 2px solid #2563eb; padding-bottom: 0.5rem; color: #1e3a8a; }}
  h2 {{ color: #1e40af; margin-top: 2rem; }}
  p {{ margin: 0.5rem 0; }}
  li {{ margin: 0.25rem 0 0.25rem 1.5rem; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
  th, td {{ border: 1px solid #d1d5db; padding: 0.5rem; text-align: left; }}
  th {{ background: #eff6ff; font-weight: 600; }}
  code {{ background: #f3f4f6; padding: 0.15rem 0.3rem; border-radius: 3px; font-size: 0.9em; }}
</style>
</head>
<body>
{''.join(body)}
</body>
</html>"""

    return html


def generate_json(target: str, data: dict) -> str:
    report = {
        "report": {
            "target": target,
            "generated_at": datetime.now().isoformat(),
            "data": data,
        }
    }
    return json.dumps(report, indent=2, ensure_ascii=False)
