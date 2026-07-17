"""
Coder node for Robert — Phase 2
Writes code, runs it, checks output, iterates until working, then commits.
"""

import os
import re
import tempfile
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage
from state import RobertState
from config import ROBERT_EXEC_MODEL as ROBERT_MODEL, OPENROUTER_API_KEY, OPENROUTER_BASE_URL
# Coder uses Haiku — writing/running code is execution, not strategy
from tools.exec_tool import run_command
from policy_gate import gate

WORKSPACE = "/root/.openclaw/workspace"
MAX_ITERATIONS = 4

CODER_PROMPT = """You are Robert, a coding agent for Buildtronix AI Corp.

Your job:
1. Write code to complete the task
2. The code will be executed and you'll see the output
3. If it fails, fix it and try again (up to 4 attempts)
4. When it works, commit it to git

Rules:
- Write complete, runnable Python or shell scripts
- Include all imports
- Handle errors gracefully
- Print clear output so you can verify it worked
- Keep code focused and minimal

When writing code, use this format EXACTLY:
```python
# your code here
```

Or for shell:
```bash
# your commands here
```

IMPORTANT - FILE CREATION TASKS:
If the task requires creating or writing a file to a specific path:
1. Your code MUST write the file content to the target path using open(path, 'w').write(content)
2. Your code MUST verify the file exists: assert os.path.exists(path), f"File not written: {path}"
3. Your code MUST print the file path and first 3 lines as verification
4. Only declare TASK_COMPLETE after the file exists on disk
5. NEVER declare TASK_COMPLETE if only showing file content in the response — the file must actually exist on disk

When the task is DONE and working, end with: TASK_COMPLETE
If you cannot complete it after max attempts, end with: TASK_FAILED - <reason>

---

OUTPUT STRUCTURE (mandatory — applies to your final completion message, not the code itself):

After your code runs successfully, before TASK_COMPLETE, produce:

## Task Output
[Summary of what the code does / the artifact produced]

## Completion Report
Action taken: [State explicitly what you did]
Evidence 1: [First directly observed outcome — execution output, file written, command result]
Evidence 2: [Second independent verification, distinct from Evidence 1]

Evidence classification:
- L1: Direct observations (execution output, file exists checks, grep results)
- L2: Derived inferences from L1
- L3: Assumptions not yet verified
- L4: Unknowns

Never present L3 or L4 as confirmed facts.
TASK_COMPLETE is only valid after ## Completion Report with all three fields present.
"""

def extract_code(text: str) -> tuple[str, str]:
    """Extract code block and language from LLM response."""
    # Try python block
    py_match = re.search(r'```python\n(.*?)```', text, re.DOTALL)
    if py_match:
        return py_match.group(1).strip(), "python"
    
    # Try bash block
    bash_match = re.search(r'```bash\n(.*?)```', text, re.DOTALL)
    if bash_match:
        return bash_match.group(1).strip(), "bash"
    
    # Try generic code block
    generic_match = re.search(r'```\n(.*?)```', text, re.DOTALL)
    if generic_match:
        return generic_match.group(1).strip(), "python"
    
    return "", ""

def run_code(code: str, lang: str) -> dict:
    """Write code to temp file and execute it."""
    if not code:
        return {"stdout": "", "stderr": "No code to run", "returncode": -1}
    
    suffix = ".py" if lang == "python" else ".sh"
    
    with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
        f.write(code)
        tmp_path = f.name
    
    try:
        if lang == "python":
            cmd = f"python3 {tmp_path}"
        else:
            cmd = f"bash {tmp_path}"
        
        result = run_command(cmd, timeout=60)
        return result
    finally:
        os.unlink(tmp_path)

def commit_to_git(filepath: str, message: str, originating_decision_id: str = None) -> dict:
    """Commit a file to git — GATED. Permanent state change requires gate approval."""
    from policy_gate import gate
    # commit_artifact: irreversible=False triggers escalation to RED at Gate 2
    # decision_id links this commit to its originating execution gate decision
    gate(
        "commit_artifact",
        target=filepath,
        data_sensitivity="internal",
        reversible=False,  # git commits are permanent state changes
        execution_payload={
            "filepath": filepath,
            "message": message,
            "originating_decision_id": originating_decision_id,
        }
    )
    result = run_command(f"cd {WORKSPACE} && git add {filepath} && git commit -m '{message}'")
    return result

def _generate_tests(task: str, design_doc: str, client) -> tuple[str, str]:
    """Generate pytest test cases before implementation."""
    import re as _re
    from pathlib import Path
    slug = _re.sub(r'[^a-z0-9]+', '_', task[:40].lower()).strip('_')
    test_file = f"/var/lib/robert/workspace/tests/test_{slug}.py"

    test_prompt = f"""You are Robert — senior engineer. Write pytest test cases for this task BEFORE implementation.

Task: {task}

Design context:
{design_doc[:1000] if design_doc else 'None'}

Write 3-5 meaningful pytest test cases. Include:
- Happy path test
- Edge case test
- Error condition test

Output only the Python test code in a ```python block. No explanation."""

    response = client.invoke([
        SystemMessage(content="You are a senior engineer writing tests first."),
        HumanMessage(content=test_prompt),
    ])
    code, _ = extract_code(response.content)
    if code:
        Path("/var/lib/robert/workspace/tests").mkdir(exist_ok=True)
        with open(test_file, 'w') as f:
            f.write(code)
        print(f"[CODER] Test file written: {test_file}")
    return test_file, code


def _run_tests(test_file: str) -> dict:
    """Run pytest on the test file."""
    import subprocess
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", test_file, "-v", "--tb=short", "--timeout=30"],
            capture_output=True, text=True, timeout=60
        )
        passed = result.stdout.count(" PASSED")
        failed = result.stdout.count(" FAILED")
        return {
            "passed": passed,
            "failed": failed,
            "output": result.stdout[-2000:] + result.stderr[-500:],
            "returncode": result.returncode,
        }
    except Exception as e:
        return {"passed": 0, "failed": 0, "output": str(e), "returncode": -1}


def validate_rr(state: dict) -> None:
    """RR-0040 Part A: Hard block deployment operations without an active RR ID.

    Detection priority:
    1. state['task_type'] == 'deployment' (authoritative — set by BOB per protocol)
    2. Keyword match on task string (fallback only — when task_type absent)
    """
    task_type = state.get("task_type", "")
    is_deployment = task_type == "deployment"

    if not is_deployment and not task_type:
        task = state.get("task", "").lower()
        deployment_keywords = [
            "deploy", "restart", "systemctl", "install",
            "update system", "apply patch", "migrate", "pip install"
        ]
        is_deployment = any(kw in task for kw in deployment_keywords)

    if is_deployment and not state.get("rr_id"):
        raise Exception(
            "BLOCKED: RR required before deployment. "
            "Set state['rr_id'] to the active RR number to proceed."
        )

    if is_deployment and state.get("rr_id"):
        print(f"[RR_VALIDATED] rr_id={state['rr_id']} task_type={state.get('task_type')}")


def coder(state: RobertState) -> RobertState:
    """
    Phase 2 coding node — test-first discipline.
    Generates tests, writes code, executes, iterates on failures, commits on success.
    """
    validate_rr(state)  # RR-0040: hard block if deployment task without RR ID
    try:
        client = ChatOpenAI(
            model=ROBERT_MODEL,
            openai_api_key=OPENROUTER_API_KEY,
            openai_api_base=OPENROUTER_BASE_URL,
            max_tokens=8192,  # RR-0031: prevent mid-generation truncation on Haiku-4-5
        )

        task = state["current_task"]
        context = state.get("memory_context", "")
        design_doc = state.get("design_doc", "")

        # Test-first: generate tests before coding
        if state.get("task_type") in ["code", "design", "architecture", "system"]:
            test_file, test_code = _generate_tests(task, design_doc, client)
            state["test_file"] = test_file
            state["tests_generated"] = bool(test_code)

        # Include design doc in coder context if available
        design_context = f"\n\nDesign Document:\n{design_doc[:2000]}" if design_doc else ""

        conversation = [
            SystemMessage(content=CODER_PROMPT),
            HumanMessage(content=f"Task: {task}\n\nContext: {context}{design_context}\n\nWrite the code to complete this task.")
        ]
        
        iterations = 0
        last_code = ""
        last_lang = ""
        execution_log = []
        
        while iterations < MAX_ITERATIONS:
            iterations += 1
            
            # Get LLM response
            response = client.invoke(conversation)
            llm_text = response.content
            
            # Check for completion signals
            if "TASK_COMPLETE" in llm_text:
                state["result"] = f"✅ Task completed in {iterations} iteration(s).\n\n{llm_text}\n\nExecution log:\n" + "\n".join(execution_log)
                state["messages"].append({"role": "coder", "content": state["result"]})
                
                # Try to commit if we have code
                # Run tests if they were generated
                if state.get("test_file"):
                    test_results = _run_tests(state["test_file"])
                    state["test_results"] = test_results
                    state["result"] += f"\n\n🧪 Tests: {test_results['passed']} passed, {test_results['failed']} failed"
                    if test_results["failed"] > 0:
                        state["result"] += f"\nTest output:\n{test_results['output'][-500:]}"

                if last_code:
                    commit_msg = f"Robert: {task[:60]}"
                    # Gate the commit — permanent artifact persistence
                    # Link to the originating decision via state task_id
                    from policy_gate import gate as _commit_gate
                    try:
                        _commit_gate(
                            "commit_artifact",
                            target=f"{WORKSPACE} (all staged files)",
                            data_sensitivity="internal",
                            reversible=False,
                            execution_payload={
                                "commit_message": commit_msg,
                                "task": task[:200],
                                "originating_task_id": state.get("task_id", "unknown"),
                                "code_preview": last_code[:300],
                            }
                        )
                        commit_result = run_command(f"cd {WORKSPACE} && git add -A && git commit -m \"{commit_msg}\"")
                        if commit_result["returncode"] == 0:
                            state["result"] += f"\n\n✅ Committed to git."
                    except PermissionError as e:
                        state["result"] += f"\n\n⚠️ Commit blocked by policy gate: {str(e)[:100]}"
                    
                return state
            
            if "TASK_FAILED" in llm_text:
                state["result"] = f"❌ Task failed: {llm_text}"
                state["requires_escalation"] = True
                return state
            
            # Extract and run code
            code, lang = extract_code(llm_text)
            
            if not code:
                # No code block — treat as analysis/planning response
                conversation.append(response)
                conversation.append(HumanMessage(content="No code block found. Please write the actual code in a ```python or ```bash block."))
                continue
            
            last_code = code
            last_lang = lang
            
            # Policy gate: classify before executing any code
            gate("run_script", target=f"{lang}:{task[:60]}", reversible=True,
                 execution_payload={"lang": lang, "code_preview": code[:500], "task": task[:200]})

            # Execute the code
            exec_result = run_code(code, lang)
            
            log_entry = f"Iteration {iterations}:\nCode:\n{code[:500]}\nOutput: {exec_result['stdout'][:300]}\nErrors: {exec_result['stderr'][:300]}\nExit: {exec_result['returncode']}"
            execution_log.append(log_entry)
            
            # Add result to conversation for next iteration
            conversation.append(response)
            
            if exec_result["returncode"] == 0:
                feedback = f"✅ Code ran successfully!\nOutput:\n{exec_result['stdout'][:1000]}\n\nIf this completes the task, say TASK_COMPLETE. Otherwise continue."
            else:
                feedback = f"❌ Code failed (exit {exec_result['returncode']}).\nStdout: {exec_result['stdout'][:500]}\nStderr: {exec_result['stderr'][:500]}\n\nFix the error and try again."
            
            conversation.append(HumanMessage(content=feedback))
        
        # Max iterations hit
        state["result"] = f"⚠️ Max iterations ({MAX_ITERATIONS}) reached.\n\nLast execution log:\n" + "\n".join(execution_log[-2:])
        state["requires_escalation"] = True
        return state

    except Exception as e:
        state["error"] = f"Coder error: {str(e)}"
        state["requires_escalation"] = True
        return state
