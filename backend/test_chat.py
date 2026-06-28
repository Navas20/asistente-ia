import httpx
r = httpx.post("http://localhost:8000/chat",
    headers={"Authorization": "Bearer test-token"},
    json={"message": "Hola, elegi tu propio nombre y decime quien sos", "conversation_id": "test-001"},
    timeout=120)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"RESPUESTA: {data['response']}")
else:
    print(f"ERROR: {r.text}")
