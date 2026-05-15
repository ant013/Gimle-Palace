# Gimlé Palace

> **Gimlé** — в скандинавской мифологии последнее убежище достойных после Рагнарёка.
> Метафорически — защищённое место где хранится ценное знание,
> доступное только тем, кто умеет к нему обратиться.

Portable self-hostable стек, который даёт AI coding agents (Claude Code, Codex, Cursor,
OpenCode, Gemini, Paperclip employees) **pre-chewed контекстное знание** о любом кодовом
репозитории. Один раз глубоко анализирует проект силами команды специализированных
reviewer-агентов, хранит результат в bi-temporal knowledge graph, выставляет его через
MCP — и агенты перестают жечь контекст на разведку, начинают работать.

## Stack

Neo4j Community 5.x · Graphiti · Python (FastAPI + asyncio) · Docker Compose ·
Model Context Protocol · (опционально) Paperclip AI как control plane

## Deployment

Одна команда на чистом сервере. Три профиля (`review` / `analyze` / `full`) под разный
масштаб. Client ставится за одну `curl ... | sh`.

Операторский ранбук для host-side `project analyze`:
[`docs/runbooks/project-analyze-operator-path.md`](docs/runbooks/project-analyze-operator-path.md)

См. [`docs/superpowers/specs/2026-04-15-gimle-palace-design.md`](docs/superpowers/specs/2026-04-15-gimle-palace-design.md) — полная архитектура.

## Status

🏗 **Design phase complete · implementation starting.**

Spec: 2800+ строк, 9 phases, ~12-14 weeks MVP.
First live ingest (Phase 7): `unstoppable-wallet-ios`.
Implementation разбита на отдельные plans через [superpowers](https://github.com/obra/superpowers) skill'ы.

## Contributing

Design phase — пока не принимаем external contributions. Следить за прогрессом можно через
issues / commits. После Phase 4-5 откроется window для обсуждения.
