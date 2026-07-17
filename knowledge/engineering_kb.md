# Robert Engineering Knowledge Base
_Last updated: 2026-04-21 | Robert v2_

---

## LLM Architecture

### Transformer Architecture
- **Attention mechanism:** Q/K/V projections, scaled dot-product attention, multi-head attention. O(n²) in sequence length.
- **MLP block:** Two linear layers with GELU activation (SwiGLU in modern models). ~2/3 of parameters.
- **LayerNorm:** Pre-norm (modern) vs post-norm. RMS norm in Llama/Mistral.
- **Residual connections:** Every block has skip connections. Critical for gradient flow in deep networks.
- **Positional encoding:** Sinusoidal (original), learned (GPT), RoPE (Llama, Mistral, Claude), ALiBi (longer context).

### Key Models (2024-2026)
| Model | Context | Notes |
|-------|---------|-------|
| GPT-4o | 128K | OpenAI flagship, vision capable |
| Claude 3.5/4.x Sonnet | 200K | Anthropic, best for reasoning/code |
| Claude Haiku 4.5 | 200K | Fast, cheap, good for execution tasks |
| Llama 3.3 70B | 128K | Best open-source, Meta |
| Mistral Large | 128K | European, strong on code |
| Gemini 1.5 Pro | 1M | Google, longest context |

### Inference Optimization
- **KV Cache:** Stores K/V tensors for previously seen tokens. Essential for generation speed.
- **Quantization:** GPTQ (post-training, 4-bit), AWQ (activation-aware), GGUF (llama.cpp format). 4-bit = ~4x size reduction, ~5-10% quality loss.
- **Batching:** Dynamic batching for throughput. vLLM uses PagedAttention for efficient KV cache management.
- **Speculative decoding:** Draft model generates candidates, main model verifies. 2-3x speedup.

### Fine-Tuning Approaches
- **LoRA:** Low-Rank Adaptation. Freeze base model, train small rank-decomposed matrices. r=8-64 typical.
- **QLoRA:** LoRA + 4-bit quantized base model. Train 70B on single A100.
- **Full fine-tune:** All weights updated. Expensive but highest quality. Use for domain adaptation.
- **RLHF:** Reward model trained on human preferences, then PPO. Used in ChatGPT/Claude.
- **DPO:** Direct Preference Optimization. Simpler than RLHF, no reward model needed. Often preferred now.
- **ORPO/SimPO:** Newer alignment methods, more stable training than DPO.

### RAG Patterns
- **Naive RAG:** Embed query → vector search → stuff top-k into context → generate.
- **Advanced RAG:** Query rewriting, reranking (Cohere/BGE), hybrid search (vector + BM25), HyDE.
- **Agentic RAG:** Agent decides when/what to retrieve. Multiple retrieval steps. Tool-use pattern.
- **Hybrid search:** Combine dense (vector) + sparse (BM25/TF-IDF). RRF for result fusion.

### Vector Databases
| DB | Notes |
|----|-------|
| Pinecone | Managed, serverless tier, good for production |
| Weaviate | Open source, multi-modal, good GraphQL API |
| Qdrant | Open source, Rust, high performance, good filtering |
| pgvector | PostgreSQL extension. Use when already on Postgres (Supabase). |
| Chroma | Local dev, simple API, not production-grade |

### Embedding Models
- `text-embedding-3-small` — 1536 dims, $0.02/1M tokens, good general purpose
- `text-embedding-3-large` — 3072 dims, better quality, 5x cost
- `nomic-embed-text` — Open source, strong performance, Apache 2.0
- `BGE-M3` — Multi-lingual, multi-granularity, strong on retrieval benchmarks

---

## AI Agent Architecture

### Frameworks
- **LangGraph:** Graph-based agent orchestration. Nodes = functions, edges = routing logic. State machine or DAG. Best for complex multi-step agents. Robert is built on LangGraph.
- **LangChain:** Tool chains, retrievers, agents. Heavy abstraction. Good for simple pipelines.
- **AutoGen:** Microsoft. Multi-agent conversations. Good for collaborative tasks.
- **CrewAI:** Role-based multi-agent teams. Higher-level abstraction over LangChain.

### State Machines vs DAGs
- **State machines:** Fixed states, transitions defined by conditions. Predictable, auditable. Good for: approval workflows, step-by-step processes.
- **DAGs:** Directed acyclic graphs. Flexible routing. Good for: parallel execution, conditional branching, complex pipelines. LangGraph supports cycles (not pure DAG).

### Tool Use Patterns
- **Function calling:** Structured output with tool name + JSON args. OpenAI/Anthropic both support.
- **ReAct:** Reason → Act → Observe loop. Agent thinks then acts.
- **Tool chaining:** Output of one tool feeds next. Must handle failures gracefully.
- **Parallel tool calls:** Multiple tools in one generation. Claude and GPT-4 support this.

### Memory Types
- **In-context:** Everything in the current context window. Fast, limited by context size.
- **External vector:** Embeddings in a vector DB. Semantic retrieval. Unlimited scale.
- **Procedural:** Skills/tools the agent can invoke. Robert's tools directory.
- **Episodic:** Past experiences/conversation history. Robert's memory_store.py.

### HMAC Security for Agent APIs
- Sign request payloads with HMAC-SHA256 using shared secret
- Include timestamp + nonce in envelope to prevent replay attacks
- 5-minute expiry window on signed messages
- Verify signature before processing any inter-agent message
- Robert uses this in bob_contract.py

---

## Software Engineering

### Python Best Practices
- **Type hints everywhere:** `def func(x: int, y: str) -> dict[str, Any]:`
- **Pydantic for validation:** Use BaseModel for all structured data crossing boundaries
- **Dataclasses:** For simple data containers without validation
- **async/await:** Use for I/O-bound operations (API calls, DB queries). Don't block event loop.
- **Context managers:** Always use `with` for files, connections, locks
- **Error handling:** Specific exceptions, not bare `except`. Log with context.
- **Logging:** Use `logging` module, not `print` in production code

### API Design
- **REST:** Resources = nouns, HTTP verbs = actions. GET/POST/PATCH/DELETE. Idempotent where possible.
- **Idempotency:** Same request = same result. Use idempotency keys for mutations (Stripe pattern).
- **Pagination:** Cursor-based for large datasets (not offset — breaks with mutations).
- **Versioning:** `/api/v1/` prefix or `Accept-Version` header.
- **Error format:** `{success: false, error: "message", code: "ERROR_CODE"}`

### PostgreSQL / Supabase
- **RLS (Row Level Security):** Enable on all tables. Policy per role. Supabase auth integrates automatically.
- **Indexes:** B-tree for equality/range, GiST for geometric/text search, GIN for arrays/JSONB.
- **Connection pooling:** Use Supabase pooler (pgBouncer) for serverless. Max 10 direct connections on free tier.
- **Triggers:** Use for `updated_at` columns. `CREATE TRIGGER ... BEFORE UPDATE`.
- **UUID primary keys:** `gen_random_uuid()`. Never expose sequential IDs.
- **Supabase DB URL:** `postgresql://postgres.[ref]:[password]@aws-1-us-east-1.pooler.supabase.com:5432/postgres`

### Next.js 15/16
- **App Router:** `app/` directory. `page.tsx` = route. `layout.tsx` = shared layout. `loading.tsx` = Suspense fallback.
- **Server Components:** Default. Fetch data directly, no useEffect. Can't use hooks/event handlers.
- **Client Components:** `"use client"` directive. Required for hooks, browser APIs, event handlers.
- **API Routes:** `app/api/[route]/route.ts`. Export `GET`, `POST`, `PATCH`, `DELETE` functions.
- **Dynamic params (v16):** `{ params }: { params: Promise<{ id: string }> }` — must `await params`.
- **Middleware:** `middleware.ts` at root. Runs before every request. Use for auth, redirects.

### Testing
- **pytest:** Python testing framework. Fixtures for setup/teardown. Parametrize for multiple inputs.
- **Test types:** Unit (isolated function), Integration (real DB/API), E2E (full user journey).
- **Test-first discipline:** Write test cases before implementation. Catches requirement ambiguities early.
- **Coverage target:** 80% for production code. 100% for critical paths (auth, payments, financial calcs).

---

## Construction Tech Domain

### ComputerEase
- Dominant accounting system for MEP contractors (mechanical, plumbing, HVAC, electrical)
- **CE Live API:** REST API in CE version 24.3+. Requires CE Live middleware installation.
- **Key modules:** Job costing, payroll, AP/AR, equipment, purchase orders
- **Job cost structure:** Job → Phase → Cost code → Labor/Material/Subcontract/Equipment/Overhead
- **Integration scope:** Real-time job cost sync, payroll imports, AP aging, AR invoicing
- Procore does NOT integrate with ComputerEase. This is Buildtronix's moat.

### Procore (Competition)
- Enterprise construction PM platform. IPO'd at $6.5B.
- **Strengths:** RFIs, submittals, drawings, change orders, inspections, large GC market
- **Weaknesses:** No service ops, no ComputerEase integration, expensive ($375-1200+/mo), overkill for sub-$50M contractors
- **API:** REST API, good documentation, webhook support. Robert knows the Procore API.

### Bluebeam Revu
- Industry-standard PDF markup tool for construction. Used by most GCs and engineers.
- **Studio Sessions:** Cloud collaboration. Multiple users mark up same drawing simultaneously.
- **Studio API:** REST API for programmatic access to sessions, markups, and layers.
- **Markup layers:** Each discipline (mechanical, electrical, structural) has its own layer.
- **Use in Buildtronix:** Import drawings via Studio API → create reference point anchors on drawing → anchor video frames to coordinates → write progress markups back to Bluebeam layer.
- **Georeferenced PDFs:** Construction drawings have real-world coordinates embedded. Use these for spatial anchoring.

### Field Vision (Buildtronix)
- Daily video walk by foreman → AI video analysis → delta calculation
- **QR anchor system:** Physical QR codes placed at fixed job points. Printed, taped to walls/columns.
- **Video anchoring:** Each video frame georeferenced to QR anchor → mapped to Bluebeam drawing coordinates
- **Delta calculation:** Compare today's video to yesterday's video → what changed = work done that shift
- **SAM2 (Meta):** Open-source video segmentation model for detecting installed vs not-installed elements
- **GPT-4o Vision:** Describes what's visible in each frame, identifies MEP systems
- **Production rate:** LF of pipe, number of hangers, % ductwork complete per zone per shift
- **Norm integration:** Production delta → cost code → compare to bid labor budget → M/L ratio check

### NAICS Codes (Construction)
| Code | Trade |
|------|-------|
| 236220 | Commercial Building Construction |
| 238210 | Electrical Contractors |
| 238220 | Plumbing, Heating, AC (HVAC/mechanical) |
| 238330 | Flooring |
| 237310 | Highway/Street/Bridge |
| 541330 | Engineering Services |

### CSI MasterFormat Divisions
- **Division 01:** General Requirements
- **Division 03:** Concrete
- **Division 05:** Metals / Structural Steel
- **Division 07:** Thermal & Moisture Protection
- **Division 08:** Openings (doors, windows)
- **Division 09:** Finishes (drywall, paint)
- **Division 15/22:** Plumbing
- **Division 15/23:** HVAC/Mechanical
- **Division 16/26:** Electrical

### Material/Labor Ratios by Trade
| Trade | Typical M/L Ratio | Alert Threshold |
|-------|------------------|-----------------|
| HVAC (ductwork) | 1.3-1.6:1 | >15% drift from bid |
| HVAC (equipment) | 3.0-5.0:1 | >15% drift |
| Plumbing (pipe) | 1.1-1.4:1 | >15% drift |
| Electrical (wire/conduit) | 0.8-1.2:1 | >15% drift |
| General Construction | 1.5-2.5:1 | >20% drift |

Norm monitors these ratios. Deviation = labor coding error, productivity problem, or material waste.

---

_This KB is Robert's reference. Update it when you learn something new._
