# Robert v1 — LangGraph COO Agent

**Robert** is an AI-powered Chief Operating Officer (COO) agent for Buildtronix. It's built on LangGraph and handles complex operational tasks with multi-step planning, execution, and review.

## What is Robert?

Robert is a LangGraph-based agent that:
- **Plans** complex tasks into actionable steps
- **Executes** plans with access to tools (exec, memory, database, email)
- **Reviews** results and validates outcomes
- **Routes** to finance specialists for financial tasks
- **Escalates** when human judgment is needed

## Architecture

```
START
  ↓
PLANNER (breaks down task, detects if finance-related)
  ↓
  ├→ FINANCE (if is_finance_task=True)
  ├→ EXECUTOR (otherwise)
  ↓
REVIEWER (validates result, checks for escalation)
  ↓
  ├→ END (if requires_escalation or max iterations)
  └→ PLANNER (retry loop)
```

## Installation

```bash
pip install -r requirements.txt
```

**Requirements:**
- Python 3.10+
- Anthropic API key (Claude Haiku)
- Optional: Supabase credentials, SendGrid API key, Telegram bot token

## Configuration

Create a `.env` file in the robert/ directory:

```
# All credentials must be environment variables — never hardcode
ANTHROPIC_API_KEY=[set from env]
SUPABASE_URL=[set from env]
SUPABASE_SERVICE_KEY= os.environ.get("SUPABASE_SERVICE_KEY", "")
SENDGRID_API_KEY= os.environ.get("SENDGRID_API_KEY", "")
TELEGRAM_BOT_TOKEN=[set from env]
TELEGRAM_CHAT_ID=[set from env]
WORKSPACE_PATH=/root/.openclaw/workspace
ROBERT_MODEL=anthropic/claude-haiku-4-5
```

## Usage

### Command Line

```bash
python main.py "Your task here"
```

### Interactive

```bash
python main.py
# Prompts for task input
```

### Example Tasks

```bash
# Financial analysis
python main.py "Analyze the P&L for Q1 2025"

# Operational planning
python main.py "Create a project timeline for the MechCo expansion"

# Data operations
python main.py "Query all active projects and summarize status"
```

## State Schema

```python
RobertState = {
    "current_task": str,           # The task being processed
    "memory_context": str,         # Loaded from workspace
    "pending_approvals": [str],    # Items awaiting approval
    "active_workflows": [str],     # Current workflows
    "messages": [dict],            # Execution history
    "iteration_count": int,        # Loop counter
    "requires_escalation": bool,   # Needs human review
    "is_finance_task": bool,       # Finance routing flag
    "result": str,                 # Final output
    "error": str                   # Error message if any
}
```

## Nodes

### Planner
Breaks down the task into steps and detects if it's finance-related.

### Executor
Executes the plan using available tools (exec, memory, database).

### Finance (Bill)
Specialized handler for financial operations (P&L, budgets, revenue, expenses).

### Reviewer
Validates results and determines if escalation is needed.

## Tools Available

- **Memory**: read_memory, write_memory, append_memory
- **Execution**: run_command (shell)
- **Database**: query_table, insert_row (Supabase)
- **Messaging**: send_telegram, send_email

## Development

### Adding a New Tool

1. Create `tools/new_tool.py` with your function(s)
2. Import in `tools/__init__.py`
3. Reference in node code (e.g., executor.py)

### Adding a New Node

1. Create `nodes/new_node.py` with your node function
2. Import in `nodes/__init__.py`
3. Add to graph in `graph.py`
4. Define routing logic if needed

## Limitations

- Max 3 iterations by default (configurable)
- Claude Haiku model (cost-optimized)
- Supabase as database backend
- Telegram for notifications

## License

Internal tool for Buildtronix.
