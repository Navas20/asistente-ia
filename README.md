# Artenisa — AI Operations Copilot

[![CI/CD](https://img.shields.io/badge/CI%2FCD-GitHub%20Actions-blue)](https://github.com/Navas20/asistente-ia/actions)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-teal)](https://fastapi.tiangolo.com)
[![Docker](https://img.shields.io/badge/Docker-3%20services-2496ED)](https://docker.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue)](https://postgresql.org)

Asistente de operaciones con IA que integra un backend FastAPI, un bot de Telegram multi-comando y herramientas de ciberseguridad — todo containerizado con Docker y CI/CD automatizado.

## Arquitectura

```
┌─────────────────┐     ┌──────────────┐     ┌──────────────┐
│   Telegram Bot  │────▶│   Backend     │────▶│  PostgreSQL  │
│   (Docker)      │     │   FastAPI     │     │  (Docker)    │
└─────────────────┘     └──────┬───────┘     └──────────────┘
                               │
                        ┌──────▼───────┐
                        │  Kali Tools  │
                        │  (Docker)    │
                        └──────────────┘
```

## Tech Stack

| Servicio | Tecnología | Detalles |
|---|---|---|
| Backend | FastAPI (Python 3.10+) | 13 endpoints REST |
| Bot | Telegram Bot API | 9 botones + wizards |
| DB | PostgreSQL | Vercel Postgres |
| Infra | Docker + docker-compose | Health checks, NET_ADMIN |
| CI/CD | GitHub Actions | SARIF security reports |
| SO | Kali Linux tools | 5 playbooks de ciberseguridad |

## Características

- **Plugin system extensible** — Arquitectura modular para agregar comandos sin modificar el core
- **Memoria de 3 capas** — Contexto de conversación, preferencias y estado de operaciones
- **24+ comandos** con ayuda contextual y validación de parámetros
- **Wizards guiados** paso a paso para tareas complejas
- **5 playbooks de ciberseguridad** con automatización de herramientas Kali
- **Health checks + volúmenes persistentes** en todos los contenedores

## CI/CD

GitHub Actions con:
- Build multi-stage Docker
- Test suite automatizada (pytest)
- SARIF security scanning
- Deploy automático

## Instalación

```bash
cp .env.example .env
docker-compose up -d
```

3 servicios se levantan con health checks y volúmenes configurados.
