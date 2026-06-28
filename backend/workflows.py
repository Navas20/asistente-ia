import os
import subprocess
import re
import shutil
from datetime import datetime

TOOL_TIMEOUT = int(os.getenv("TOOL_TIMEOUT", "120"))

def tool_exists(name: str) -> bool:
    return shutil.which(name) is not None

def run(cmd: str, timeout: int = None) -> dict:
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout or TOOL_TIMEOUT
        )
        output = (result.stdout or result.stderr or "(sin salida)")[:5000]
        return {
            "command": cmd,
            "success": result.returncode == 0,
            "output": output,
            "returncode": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"command": cmd, "success": False, "output": "[Timeout]"}
    except Exception as e:
        return {"command": cmd, "success": False, "output": f"[Error: {e}]"}

def try_run(tool: str, args: str, fallback_msg: str = None) -> dict:
    """Ejecuta una herramienta solo si existe, sino devuelve mensaje."""
    if tool_exists(tool):
        return run(f"{tool} {args}")
    return {
        "command": f"{tool} {args}",
        "success": False,
        "output": fallback_msg or f"[{tool} no instalado]"
    }

WORKFLOWS = {
    "full_recon": {
        "name": "Reconocimiento Completo",
        "description": "Escanea un objetivo a fondo: WHOIS, puertos, DNS, directorios",
        "params": [{"name": "target", "label": "Objetivo (IP o dominio)", "type": "text"}],
        "ofensivo": "Recolectar toda la información posible del objetivo",
        "defensivo": "Cerrar puertos innecesarios, ocultar info WHOIS, WAF, monitoreo continuo"
    },
    "web_audit": {
        "name": "Auditoría Web",
        "description": "Analiza un sitio web: tecnologías, vulnerabilidades, fuerza bruta",
        "params": [{"name": "target", "label": "URL (ej: http://example.com)", "type": "text"}],
        "ofensivo": "Identificar tecnologías, vulnerabilidades web y directorios ocultos",
        "defensivo": "Headers de seguridad, WAF, sanitización de inputs, rate limiting"
    },
    "exploit_suggest": {
        "name": "Sugerencia de Exploits",
        "description": "Busca exploits conocidos para servicios detectados",
        "params": [{"name": "service", "label": "Servicio y versión (ej: Apache 2.4.49)", "type": "text"}],
        "ofensivo": "Encontrar exploits públicos para el servicio",
        "defensivo": "Parches actualizados, segmentación, IDS/IPS"
    },
    "network_scan": {
        "name": "Escaneo de Red",
        "description": "Descubre hosts activos, puertos abiertos y servicios en una red",
        "params": [{"name": "target", "label": "Red (ej: 192.168.1.0/24)", "type": "text"}],
        "ofensivo": "Mapear toda la red: hosts activos, servicios y sistema operativo",
        "defensivo": "Segmentación de red, firewalls, NAC, monitoreo de tráfico"
    },
    "password_audit": {
        "name": "Auditoría de Contraseñas",
        "description": "Analiza fortaleza de contraseñas y hashes",
        "params": [{"name": "hash", "label": "Hash a analizar (opcional)", "type": "text", "required": False}],
        "ofensivo": "Identificar contraseñas débiles mediante cracking de hashes",
        "defensivo": "Políticas seguras, 2FA, gestor de contraseñas, MFA"
    }
}

def ejecutar_workflow(nombre: str, params: dict) -> dict:
    wf = WORKFLOWS.get(nombre)
    if not wf:
        return {"error": f"Workflow '{nombre}' no encontrado"}

    target = params.get("target", params.get("service", params.get("hash", "")))
    if not target:
        return {"error": "Se requiere un objetivo para este workflow"}

    resultados = []

    if nombre == "full_recon":
        resultados = [
            try_run("whois", target, "whois no disponible"),
            try_run("nmap", f"-sV -sC -T4 {target}", "nmap no instalado"),
            try_run("nslookup", target, "nslookup no disponible"),
        ]
        if not re.match(r'^\d+\.\d+\.\d+\.\d+$', target):
            resultados.append(
                try_run("gobuster", f"dir -u http://{target} -w /usr/share/wordlists/dirb/common.txt -q -t 10",
                        "gobuster no instalado (sudo apt install gobuster)")
            )

    elif nombre == "web_audit":
        resultados = [
            run(f"curl -sI {target} 2>/dev/null | head -30 || echo 'curl no disponible'"),
            try_run("whatweb", target, "whatweb no instalado"),
            try_run("nikto", f"-h {target} -Tuning 123456 -q", "nikto no instalado"),
            try_run("gobuster", f"dir -u {target} -w /usr/share/wordlists/dirb/common.txt -q -t 10",
                    "gobuster no instalado"),
        ]

    elif nombre == "exploit_suggest":
        resultados = [
            try_run("searchsploit", target, "searchsploit no instalado (parte de exploitdb)"),
            run(f"curl -s 'https://cve.circl.lu/api/cvefor/{target}' 2>/dev/null | head -200 || echo 'API CVE no responde'"),
        ]

    elif nombre == "network_scan":
        resultados = [
            try_run("nmap", f"-sn {target}", "nmap no instalado"),
            try_run("nmap", f"-sV -T4 {target}", "nmap no instalado"),
        ]

    elif nombre == "password_audit":
        resultados = [
            run("echo '--- Auditoría de contraseñas ---'"),
            try_run("hashid", target, "hashid no instalado") if target else run("echo '(sin hash para analizar)'"),
            run("echo 'Defensa recomendada: gestor de contraseñas + 2FA + MFA'"),
        ]

    reporte = [
        f"=== Workflow: {wf['name']} ===",
        f"Objetivo: {target}",
        f"Tiempo: {datetime.utcnow().isoformat()}",
        "",
        f" OFENSIVO: {wf['ofensivo']}",
        "",
    ]
    for r in resultados:
        icon = "    " if r.get("success") else "    "
        reporte.append(f"{icon} $ {r['command']}")
        output = r.get("output", "").strip()
        if output:
            reporte.append(output[:1500])
        reporte.append("")

    reporte.append(f" DEFENSIVO: {wf['defensivo']}")
    reporte.append("")

    if nombre == "full_recon":
        reporte.append(" Proximos pasos: web_audit, exploit_suggest")
    elif nombre == "web_audit":
        reporte.append(" Proximo paso: exploit_suggest")
    elif nombre == "network_scan":
        reporte.append(" Proximo paso: full_recon en hosts encontrados")

    return {
        "workflow": nombre,
        "target": target,
        "pasos_ejecutados": len(resultados),
        "reporte": "\n".join(reporte),
        "defensa": wf["defensivo"]
    }

def listar_workflows() -> dict:
    return {
        name: {"name": w["name"], "description": w["description"], "params": w["params"]}
        for name, w in WORKFLOWS.items()
    }
