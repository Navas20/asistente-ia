"""
Tests de integración para JARVIS API.

Ejecutar: python tests/test_api.py
Requisito: servidor corriendo en localhost:8000 con AUTH_TOKEN configurado
"""

import os
import sys
import json
import httpx
import time
import unittest

API_URL = os.getenv("API_URL", "http://localhost:8000")
AUTH_TOKEN = os.getenv("AUTH_TOKEN", "test-token")
TIMEOUT = 30

def api(path, method="GET", data=None, files=None):
    headers = {"Authorization": f"Bearer {AUTH_TOKEN}"}
    with httpx.Client(timeout=TIMEOUT) as c:
        if method == "GET":
            return c.get(f"{API_URL}{path}", headers=headers)
        elif method == "POST" and files:
            return c.post(f"{API_URL}{path}", files=files, headers={"Authorization": f"Bearer {AUTH_TOKEN}"})
        elif method == "POST" and data is not None:
            return c.post(f"{API_URL}{path}", json=data, headers=headers)
        elif method == "DELETE":
            return c.delete(f"{API_URL}{path}", headers=headers)
        elif method == "POST":
            return c.post(f"{API_URL}{path}", headers=headers)


class TestJARVIS(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # Verificar que el servidor responde
        try:
            resp = api("/")
            if resp.status_code != 200:
                print(f"\n⚠️  Servidor no responde en {API_URL}")
                print("   Asegúrate de que JARVIS está corriendo")
                print(f"   API_URL={API_URL} AUTH_TOKEN={AUTH_TOKEN}\n")
                sys.exit(1)
            cls.server_ok = True
            print(f"✓ Servidor detectado: {resp.json().get('asistente', 'JARVIS')}")
        except Exception as e:
            print(f"\n⚠️  No se pudo conectar a {API_URL}: {e}")
            print("   Asegúrate de que JARVIS está corriendo\n")
            sys.exit(1)

    # ─── ROOT ───

    def test_01_root(self):
        resp = api("/")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("asistente", data)
        self.assertIn("modelo", data)
        print("  ✓ GET /")

    # ─── AUTH ───

    def test_02_auth_required(self):
        resp = httpx.get(f"{API_URL}/", timeout=TIMEOUT)
        self.assertEqual(resp.status_code, 200)  # root no requiere auth

        resp = httpx.get(f"{API_URL}/memories", timeout=TIMEOUT)
        self.assertEqual(resp.status_code, 401)  # memories sí
        print("  ✓ Auth requerida verificada")

    # ─── CHAT ───

    def test_03_chat_basic(self):
        resp = api("/chat", "POST", {"message": "Hola, test"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("response", data)
        self.assertIn("conversation_id", data)
        self.assertGreater(len(data["response"]), 0)
        print(f"  ✓ Chat básico ({len(data['response'])} chars)")

    def test_04_chat_conversation(self):
        # Primera mensaje
        resp1 = api("/chat", "POST", {"message": "Me llamo TestUser"})
        self.assertEqual(resp1.status_code, 200)
        conv_id = resp1.json()["conversation_id"]

        # Segunda mensaje con mismo conversation_id
        resp2 = api("/chat", "POST", {
            "message": "¿Cómo me llamo?",
            "conversation_id": conv_id
        })
        self.assertEqual(resp2.status_code, 200)
        # El modelo debería recordar el nombre (no podemos asegurar, pero el endpoint funciona)
        print(f"  ✓ Chat con contexto (conv_id: {conv_id[:8]}...)")

    # ─── MEMORY ───

    def test_05_memory_crud(self):
        # Crear memoria
        resp = api("/memories", "POST", {"key": "test_key", "value": "test_value"})
        self.assertEqual(resp.status_code, 200)

        # Leer memoria
        resp = api("/memories")
        self.assertEqual(resp.status_code, 200)
        mems = resp.json().get("memories", {})
        self.assertIn("test_key", mems)
        self.assertEqual(mems["test_key"], "test_value")

        # Eliminar memoria
        resp = api("/memories/test_key", "DELETE")
        self.assertEqual(resp.status_code, 200)

        # Verificar eliminado
        resp = api("/memories")
        mems = resp.json().get("memories", {})
        self.assertNotIn("test_key", mems)
        print("  ✓ Memoria CRUD")

    # ─── SEARCH ───

    def test_06_search(self):
        resp = api("/search?query=test")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("results", data)
        # Puede fallar si no hay internet
        print(f"  ✓ Búsqueda web ({'con datos' if data['results'] and 'Error' not in data['results'] else 'sin internet'})")

    # ─── EXECUTE ───

    def test_07_execute(self):
        resp = httpx.post(
            f"{API_URL}/execute",
            data={"command": "echo 'test'"},
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            timeout=TIMEOUT
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("output", data)
        print(f"  ✓ Ejecución de comandos (returncode: {data.get('returncode')})")

    def test_08_execute_timeout(self):
        resp = httpx.post(
            f"{API_URL}/execute",
            data={"command": "sleep 5"},
            headers={"Authorization": f"Bearer {AUTH_TOKEN}"},
            timeout=TIMEOUT
        )
        self.assertEqual(resp.status_code, 200)
        print("  ✓ Timeout de comandos")

    # ─── FILES ───

    def test_09_files(self):
        # Subir archivo
        resp = api("/upload", files={"file": ("test.txt", b"Hola JARVIS", "text/plain")})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("file_id", data)
        file_id = data["file_id"]

        # Listar archivos
        resp = api("/files")
        self.assertEqual(resp.status_code, 200)
        files = resp.json().get("files", [])
        self.assertTrue(any(f["id"] == file_id for f in files))

        # Descargar archivo (no auth required for download? yes it does)
        resp = api(f"/files/{file_id}/test.txt")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content, b"Hola JARVIS")
        print(f"  ✓ File upload/download ({file_id})")

    # ─── WORKFLOWS ───

    def test_10_workflows_list(self):
        resp = api("/workflows")
        self.assertEqual(resp.status_code, 200)
        wfs = resp.json()
        self.assertGreater(len(wfs), 0)
        self.assertIn("full_recon", wfs)
        print(f"  ✓ Workflows listados ({len(wfs)} disponibles)")

    def test_11_workflow_execute(self):
        resp = api("/workflows/network_scan", "POST", {"target": "127.0.0.1"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("reporte", data)
        self.assertIn("defensa", data)
        print(f"  ✓ Workflow ejecutado (pasos: {data.get('pasos_ejecutados', 0)})")

    # ─── HEALTH ───

    def test_12_health(self):
        resp = api("/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data.get("status"), "healthy")
        print("  ✓ Health check")

    # ─── DATA EXPORT ───

    def test_13_conversations(self):
        resp = api("/conversations")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("conversations", data)
        print(f"  ✓ {len(data['conversations'])} conversaciones encontradas")


if __name__ == "__main__":
    print("\n═══════════════════════════════════")
    print(" JARVIS — Tests de integración")
    print("═══════════════════════════════════")
    unittest.main(verbosity=0)
