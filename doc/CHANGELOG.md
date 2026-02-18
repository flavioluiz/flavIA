# Changelog — Historico de Conquistas

Este arquivo documenta as funcionalidades implementadas no flavIA, organizadas por area de desenvolvimento.

## Resumo

- **28/54 tarefas concluidas** (52%)
- **4 areas 100% completas**
- **21 tarefas completas** nas 7 areas ainda ativas

---

## Areas Completas

### Area 1: Multimodal File Processing (6/6 tarefas)

Expansao do sistema de processamento de conteudo para suportar multiplos formatos alem de PDF/texto.

**Funcionalidades entregues:**

- **1.1 Audio/Video Transcription** — Transcricao de audio/video via Mistral voxtral-mini-latest com timestamps por segmento e gerenciador de midia no `/catalog`
- **1.2 Image Description** — Descricoes de imagens via modelos multimodais com capacidade de visao
- **1.3 Word/Office Documents** — Conversao de documentos Office (.docx, .xlsx, .pptx) via python-docx, openpyxl, python-pptx
- **1.4 OCR + LaTeX Equations** — Pipeline de OCR para PDFs escaneados com avaliacao de qualidade integrada ao `/catalog`
- **1.5 Visual Frame Extraction** — Extracao de frames de videos com descricoes via LLM vision
- **1.6 YouTube/Web Converters** — Extracao de transcricoes do YouTube e conteudo de paginas web com gerenciamento completo via `/catalog`

[Detalhes completos](roadmap/completed/area-1-multimodal-file-processing.md)

---

### Area 5: File Modification Tools (2/2 tarefas)

Sistema completo de ferramentas de escrita com confirmacao do usuario, previews e backups automaticos.

**Funcionalidades entregues:**

- **5.1 Write/Edit File Tools** — 7 ferramentas de escrita (`write_file`, `edit_file`, `insert_text`, `append_file`, `delete_file`, `create_directory`, `remove_directory`) com verificacao de permissoes, confirmacao do usuario e backups automaticos
- **5.2 Write Operation Preview + Dry-Run Mode** — Previews de diff no fluxo de confirmacao e modo `--dry-run` para execucao sem modificacoes

[Detalhes completos](roadmap/completed/area-5-file-modification-tools.md)

---

### Area 8: Context Window Management (5/5 tarefas)

Sistema de monitoramento e gerenciamento do contexto do modelo para evitar estouros de limite de tokens.

**Funcionalidades entregues:**

- **8.1 Token Usage Tracking** — Captura de `response.usage`, display de utilizacao no CLI/Telegram com cores por nivel
- **8.2 Compaction with Confirmation** — Auto-sumarizacao quando contexto atinge threshold com aprovacao do usuario
- **8.3 Manual /compact Command** — Comando para sumarizacao on-demand da conversa
- **8.4 Tool Result Size Protection** — Protecao contra resultados de ferramentas que excedem contexto (guard de 4 camadas)
- **8.5 Context Compaction Tool** — Ferramenta `compact_context` acessivel pelo agente com instrucoes customizaveis

[Detalhes completos](roadmap/completed/area-8-context-window-management.md)

---

### Area 11: Semantic Retrieval & RAG Pipeline (8/8 tarefas)

Pipeline RAG completo com busca hibrida (vetorial + FTS) sobre documentos convertidos.

**Funcionalidades entregues:**

- **11.1 Chunk Pipeline** — Fragmentacao de documentos convertidos em chunks de 300-800 tokens com suporte a video (transcript + frames)
- **11.2 Embedding Index (sqlite-vec)** — Embeddings via nomic-embed-text-v1.5, armazenamento em sqlite-vec
- **11.3 FTS Index (SQLite FTS5)** — Busca por termos exatos via BM25
- **11.4 Hybrid Retrieval Engine** — Fusao de resultados via Reciprocal Rank Fusion (RRF) com router de catalogo
- **11.5 Video Temporal Expansion** — Expansao de janela temporal para chunks de video
- **11.6 search_chunks Tool** — Ferramenta de busca semantica com citacoes anotadas
- **11.7 Index CLI Commands** — Comandos `/index build`, `/index update`, `/index stats`
- **11.8 Agent Guidance Update** — Orientacao no prompt para routing `search_chunks` vs `query_catalog`

**Hardening adicional:** 17 issues corrigidas pos-implementacao incluindo consistencia de `doc_id`, scoping de `@mentions`, diagnosticos com `/rag-debug`, e cobertura de citacoes.

[Detalhes completos](roadmap/completed/area-11-semantic-retrieval.md) | [Plano de hardening](roadmap/completed/rag-generic-hardening-plan.md)

---

## Tarefas Completadas em Areas Ativas

### Area 4: CLI Improvements (6/9 tarefas)

- **4.1 Consolidate Info Commands** — Comandos `/models`, `/providers`, `/tools` e `/config` unificados
- **4.2 Runtime Agent Switching** — Comando `/agent` para listar e trocar agentes mid-session
- **4.3 Runtime Model Switching** — Comando `/model` para trocar modelos sem restart
- **4.4 In-Session Provider Management** — Comandos `/provider-setup`, `/provider-manage`, `/provider-test`
- **4.7 Unified Help System** — Sistema `/help` estruturado com categorias e registro de comandos
- **4.8 Expand questionary Adoption** — Menus interativos com arrow-keys, autocomplete e fallback non-TTY

### Area 6: Academic Workflow Tools (1/2 tarefas)

- **6.1 LaTeX Compilation** — Ferramenta `compile_latex` para compilar .tex para PDF via pdflatex/latexmk

---

## Estatisticas por Dificuldade

| Dificuldade | Total | Concluidas |
|-------------|-------|------------|
| Easy        | 14    | 12         |
| Medium      | 31    | 15         |
| Hard        | 9     | 1          |
| **Total**   | **54**| **28**     |

---

**[Voltar para Roadmap](roadmap.md)**
