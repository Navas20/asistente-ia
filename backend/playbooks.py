import logging

log = logging.getLogger("artenisa.playbooks")

PLAYBOOKS = {
    "recon_web": {
        "name": "Reconocimiento Web",
        "description": "Recolecta información pública de un dominio: DNS, subdominios, puertos, tecnologías y directorios",
        "target_type": "domain",
        "depth_estimate": "medio",
        "steps": [
            {"id": "dns", "label": "Enumeration DNS", "tool": "dns_enum"},
            {"id": "subdomains", "label": "Descubrimiento de Subdominios", "tool": "subdomain_scan"},
            {"id": "ports", "label": "Escaneo de Puertos", "tool": "scan_ports"},
            {"id": "tech", "label": "Detección de Tecnologías", "tool": "detect_tech"},
            {"id": "dirs", "label": "Fuerza Bruta de Directorios", "tool": "dir_bruteforce"},
        ],
    },
    "web_audit": {
        "name": "Auditoría Web",
        "description": "Analiza un sitio web en busca de vulnerabilidades: tecnologías, SSL, SQLi, XSS, LFI y directorios",
        "target_type": "url",
        "depth_estimate": "lento",
        "steps": [
            {"id": "tech", "label": "Detección de Tecnologías", "tool": "detect_tech"},
            {"id": "headers", "label": "Análisis de Cabeceras", "tool": "check_headers"},
            {"id": "ssl", "label": "Verificación SSL/TLS", "tool": "ssl_check"},
            {"id": "sqli", "label": "Inyección SQL", "tool": "check_sqli"},
            {"id": "xss", "label": "Cross-Site Scripting", "tool": "check_xss"},
            {"id": "lfi", "label": "Local File Inclusion", "tool": "check_lfi"},
            {"id": "dirs", "label": "Fuerza Bruta de Directorios", "tool": "dir_bruteforce"},
        ],
    },
    "osint_domain": {
        "name": "OSINT de Dominio",
        "description": "Obtiene información OSINT de un dominio: DNS, subdominios, certificados y geolocalización",
        "target_type": "domain",
        "depth_estimate": "rapido",
        "steps": [
            {"id": "dns", "label": "Enumeration DNS", "tool": "dns_enum"},
            {"id": "subdomains", "label": "Descubrimiento de Subdominios", "tool": "subdomain_scan"},
            {"id": "certs", "label": "Transparencia de Certificados", "tool": "cert_transparency"},
            {"id": "geo", "label": "Geolocalización IP", "tool": "ip_geo"},
        ],
    },
    "password_audit": {
        "name": "Auditoría de Credenciales",
        "description": "Identifica y crackea hashes de contraseñas usando diccionarios integrados",
        "target_type": "any",
        "depth_estimate": "rapido",
        "steps": [
            {"id": "hash_id", "label": "Identificación de Hash", "tool": "hash_id"},
            {"id": "hash_crack", "label": "Cracking de Hash", "tool": "hash_crack"},
        ],
    },
    "full_scan": {
        "name": "Escaneo Completo",
        "description": "Escaneo exhaustivo: DNS, subdominios, puertos, tecnologías, directorios, SQLi, XSS, SSL y certificados",
        "target_type": "domain",
        "depth_estimate": "lento",
        "steps": [
            {"id": "dns", "label": "Enumeration DNS", "tool": "dns_enum"},
            {"id": "subdomains", "label": "Descubrimiento de Subdominios", "tool": "subdomain_scan"},
            {"id": "ports", "label": "Escaneo de Puertos", "tool": "scan_ports"},
            {"id": "tech", "label": "Detección de Tecnologías", "tool": "detect_tech"},
            {"id": "dirs", "label": "Fuerza Bruta de Directorios", "tool": "dir_bruteforce"},
            {"id": "sqli", "label": "Inyección SQL", "tool": "check_sqli"},
            {"id": "xss", "label": "Cross-Site Scripting", "tool": "check_xss"},
            {"id": "ssl", "label": "Verificación SSL/TLS", "tool": "ssl_check"},
            {"id": "certs", "label": "Transparencia de Certificados", "tool": "cert_transparency"},
            {"id": "report", "label": "Generación de Reporte", "tool": "generate_report"},
        ],
    },
}


def list_playbooks() -> dict:
    """Return name, description, target_type, depth_estimate for all playbooks."""
    return {
        name: {
            "name": pb["name"],
            "description": pb["description"],
            "target_type": pb["target_type"],
            "depth_estimate": pb["depth_estimate"],
        }
        for name, pb in PLAYBOOKS.items()
    }


def run_playbook(
    name,
    target,
    depth="rapido",
    hacking_module=None,
    target_engine=None,
    memory_engine=None,
    conv_id=None,
    progress_callback=None,
) -> dict:
    pb = PLAYBOOKS.get(name)
    if not pb:
        return {"error": f"Playbook '{name}' no encontrado"}

    if hacking_module is None:
        try:
            import hacking as hacking_module
        except ImportError:
            from backend import hacking as hacking_module

    total = len(pb["steps"]) or 1
    results = []

    for i, step in enumerate(pb["steps"]):
        pct = int((i / total) * 100)
        if progress_callback:
            progress_callback(step["label"], pct)

        step_result = {
            "step_id": step["id"],
            "label": step["label"],
            "tool": step["tool"],
            "success": False,
            "data": None,
            "note": None,
        }

        if step["id"] == "headers":
            tech_fn = getattr(hacking_module, "detect_tech", None)
            if tech_fn:
                try:
                    tech_data = tech_fn(target)
                    step_result["data"] = {"headers": tech_data.get("headers", {})}
                    step_result["success"] = True
                except Exception as e:
                    step_result["note"] = str(e)
            else:
                step_result["note"] = "detect_tech no disponible"
            results.append(step_result)
            if memory_engine and conv_id:
                memory_engine.merge_operational(conv_id, {f"step_{step['id']}": step_result})
            continue

        if step["id"] == "report":
            step_result["data"] = {
                "placeholder": True,
                "mensaje": "report generation available via /reporte",
            }
            step_result["success"] = True
            step_result["note"] = "report generation available via /reporte"
            results.append(step_result)
            if memory_engine and conv_id:
                memory_engine.merge_operational(conv_id, {f"step_{step['id']}": step_result})
            continue

        tool_fn = getattr(hacking_module, step["tool"], None)
        if not tool_fn:
            step_result["note"] = f"Función '{step['tool']}' no disponible"
            results.append(step_result)
            if memory_engine and conv_id:
                memory_engine.merge_operational(conv_id, {f"step_{step['id']}": step_result})
            continue

        try:
            data = tool_fn(target)
            step_result["data"] = data
            step_result["success"] = True
        except TypeError as e:
            step_result["note"] = f"Error de parámetros: {e}"
        except Exception as e:
            step_result["note"] = str(e)

        results.append(step_result)
        if memory_engine and conv_id:
            memory_engine.merge_operational(conv_id, {f"step_{step['id']}": step_result})

    if progress_callback:
        progress_callback("Completado", 100)

    summary = _build_summary(pb, results)

    if memory_engine and target:
        memory_engine.store_historical(
            target=target,
            operation=f"playbook:{name}",
            summary=summary,
            findings_count=sum(1 for r in results if r.get("success")),
        )

    return {
        "playbook": name,
        "target": target,
        "depth": depth,
        "steps_completed": len(results),
        "results": results,
        "summary": summary,
    }


def _build_summary(pb, results) -> str:
    total = len(results)
    ok = sum(1 for r in results if r.get("success"))
    lines = [
        f"Playbook: {pb['name']} ({pb.get('target_type', 'N/A')})",
        f"Pasos completados: {ok}/{total}",
    ]
    for r in results:
        icon = "OK" if r.get("success") else "SKIP"
        note = f" - {r['note']}" if r.get("note") else ""
        lines.append(f"  [{icon}] {r['label']}{note}")
    return "\n".join(lines)
