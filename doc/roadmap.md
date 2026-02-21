# Roadmap — Planejamento Futuro

Este documento foca no planejamento futuro do flavIA. Para o historico de funcionalidades ja implementadas, consulte o [CHANGELOG](CHANGELOG.md).

---

## Visao

flavIA e um assistente de pesquisa academica baseado em LLM, projetado para transformar a interacao com documentos, literatura cientifica e fluxos de trabalho academico. A visao e evoluir de um assistente read-only para um sistema completo de produtividade academica com:

**Capacidades atuais** (implementadas):
- Processamento multimodal de documentos (PDF, Office, audio, video, imagens, web)
- Sistema RAG com busca hibrida semantica + lexica
- Ferramentas de escrita de arquivos com seguranca e previews
- Gerenciamento de contexto com compactacao automatica
- CLI interativa com switching de agentes/modelos em runtime

**Direcao futura**:
- **Plataforma multi-bot**: Framework unificado para Telegram, WhatsApp e API web
- **Pesquisa academica integrada**: Busca em bases de dados, download de artigos, gerenciamento de referencias
- **Automacao de fluxos**: Execucao de scripts, integracao com email/calendario
- **Sistema de agentes avancado**: Perfis estruturados, agentes globais, meta-agentes

---

## Proximas Prioridades

### Quick Wins (menor esforco, valor imediato)

| Tarefa | Area | Dificuldade | Descricao |
|--------|------|-------------|-----------|
| **9.3** DOI Metadata Resolution | Pesquisa | Easy | Resolver DOIs via CrossRef/DataCite, gerar BibTeX automatico |
| **10.2** Send File Tool | Telegram | Easy | Ferramenta para enviar arquivos pelo Telegram |
| **4.5** Standard Default Agent | CLI | Medium | Agente built-in sempre disponivel como fallback |

### Recomendados para Proxima Sprint

| Tarefa | Area | Dificuldade | Valor |
|--------|------|-------------|-------|
| **10.1** Structured Agent Responses | Telegram | Medium | Habilita acoes alem de texto (envio de arquivos) |
| **10.3** Telegram File Delivery Handler | Telegram | Medium | Entrega de arquivos no chat |
| **3.1** YAML Bot Configuration | Messaging | Medium | Base para multi-bot e per-conversation agents |
| **9.1** Web Search Engine | Pesquisa | Medium | Busca na web multi-provider |

---

## Backlog por Area Ativa

### [Area 2: Agent System Improvements](roadmap/active/area-2-agent-system-improvements.md)

Redesenho do sistema de configuracao de agentes para definicoes mais ricas e manuteniveis.

| ID | Tarefa | Dificuldade | Dependencias |
|----|--------|-------------|--------------|
| 2.1 | Structured Agent Profiles | Medium | — |
| 2.2 | CLI Agent Management | Medium | 2.1, 4.2 |
| 2.3 | Meta-Agent Generation | Hard | 2.1, 2.2 |

---

### [Area 3: Messaging Platform Framework](roadmap/active/area-3-messaging-platform-framework.md)

Transformar a integracao Telegram em um framework multi-plataforma.

| ID | Tarefa | Dificuldade | Dependencias |
|----|--------|-------------|--------------|
| 3.1 | YAML Bot Configuration | Medium | — |
| 3.2 | Per-Conversation Agents | Medium | 3.1 |
| 3.3 | Multi-Bot Support | Medium | 3.1, 3.2 |
| 3.4 | Abstract Messaging Interface | Hard | 3.1, 3.2 |
| 3.5 | WhatsApp Integration | Hard | 3.4 |
| 3.6 | Web API Interface | Medium | 3.4 |

---

### [Area 4: CLI Improvements](roadmap/active/area-4-cli-improvements.md)

Consolidacao de comandos e recursos avancados de CLI.

| ID | Tarefa | Dificuldade | Dependencias |
|----|--------|-------------|--------------|
| 4.5 | Standard Default Agent | Medium | — |
| 4.6 | Global Agent Definitions | Medium | 2.1, 4.2 |
| 4.9 | Configurable LLM API Timeout | Medium | — |
| 4.10 | Batch OCR Processing in Catalog | Easy | — |

---

### [Area 6: Academic Workflow Tools](roadmap/active/area-6-academic-workflow-tools.md)

Ferramentas para producao de output academico.

| ID | Tarefa | Dificuldade | Dependencias |
|----|--------|-------------|--------------|
| 6.2 | Sandboxed Script Execution | Hard | 5.1 (done) |

---

### [Area 7: External Service Integration](roadmap/active/area-7-external-service-integration.md)

Integracao com email e calendario.

| ID | Tarefa | Dificuldade | Dependencias |
|----|--------|-------------|--------------|
| 7.1 | Email Integration (IMAP/SMTP) | Hard | — |
| 7.2 | Google Calendar | Hard | — |

---

### [Area 9: Web & Academic Research Tools](roadmap/active/area-9-web-academic-research-tools.md)

Suite completa de ferramentas para pesquisa web e academica.

| ID | Tarefa | Dificuldade | Dependencias | Status |
|----|--------|-------------|--------------|--------|
| 9.1 | Web Search Engine | Medium | — | ✅ DONE |
| 9.2 | Academic Database Search | Medium | — | ✅ DONE |
| 9.3 | DOI Metadata Resolution | Easy | — |
| 9.4 | Scopus Integration | Medium | — |
| 9.5 | Article Download & Integration | Hard | 9.2, 9.3, 1.5 (done) |
| 9.6 | CAPES/Academic Network Access | Hard | 9.5, 9.4 |
| 9.7 | BibTeX Reference Management | Medium | 9.3, 5.1 (done) |
| 9.8 | Research Session Management | Medium | 9.2, 9.5 |

---

### [Area 10: Telegram File Delivery](roadmap/active/area-10-telegram-file-delivery.md)

Envio de arquivos diretamente pelo chat do Telegram.

| ID | Tarefa | Dificuldade | Dependencias |
|----|--------|-------------|--------------|
| 10.1 | Structured Agent Responses | Medium | — |
| 10.2 | Send File Tool | Easy | 10.1 |
| 10.3 | Telegram File Delivery Handler | Medium | 10.1, 10.2 |

---

## Grafo de Dependencias (Tarefas Pendentes)

```
Area 2 -- Agent System:
  2.1 (Structured Profiles) ──┬── 2.2 (CLI Agent Commands)
                              └── 2.3 (Meta-Agent)

Area 3 -- Messaging Platforms:
  3.1 (YAML Bot Config) ──┬── 3.2 (Per-Conv Agent)
                          ├── 3.3 (Multi-Bot)
                          └── 3.4 (Abstract Interface) ──┬── 3.5 (WhatsApp)
                                                         └── 3.6 (Web API)

Area 4 -- CLI:
  4.5 (Standard Default Agent) ── (independente)
  4.6 (Global Agents) ── depende de 2.1, 4.2 (done)
  4.9 (Configurable Timeout) ── (independente)
  4.10 (Batch OCR in Catalog) ── (independente)

Area 6 -- Academic Workflow:
  6.2 (Script Execution) ── depende de 5.1 (done)

Area 7 -- External Services:
  7.1 (Email) ── (independente)
  7.2 (Calendar) ── (independente)

Area 9 -- Web & Academic Research:
  9.1 (Web Search) ✅ DONE
  9.2 (Academic Search) ✅ DONE
  9.3 (DOI Resolution) ─────────────────────────────────┐
                          ├── 9.5 (Article Download) ───┴── 9.6 (CAPES Access)
  9.4 (Scopus) ───────────┤                             │
                          └── 9.7 (BibTeX Management) ──┘
  9.8 (Research Sessions) ── depende de 9.2, 9.5

Area 10 -- Telegram File Delivery:
  10.1 (Structured Responses) ──┬── 10.2 (Send File Tool)
                                └── 10.3 (File Delivery Handler)
  10.2 ────────────────────────── 10.3
```

---

## Estatisticas

| Metrica | Valor |
|---------|-------|
| Tarefas pendentes | 25 |
| Areas ativas | 7 |
| Easy | 3 pendentes |
| Medium | 14 pendentes |
| Hard | 8 pendentes |

---

## Historico

Para o registro completo de funcionalidades ja implementadas, incluindo:
- 4 areas 100% completas
- 28 tarefas concluidas
- Detalhes de implementacao

Consulte o **[CHANGELOG](CHANGELOG.md)**.
