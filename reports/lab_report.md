# Day 08 Lab Report - LangGraph Agentic Orchestration

## 1. Student

- Name: 2A202601795-Phạm Thị Liên
- Repo/commit: local lab workspace
- Date: 2026-08-25

## 2. Architecture

The workflow is implemented as a LangGraph `StateGraph` for a support-ticket agent:

`START -> intake -> classify -> conditional route`

- `simple`: `answer -> finalize -> END`
- `tool`: `tool -> evaluate -> answer/fallback retry -> finalize -> END`
- `missing_info`: `clarify -> finalize -> END`
- `risky`: `risky_action -> approval -> tool/clarify -> evaluate -> answer -> finalize -> END`
- `error`: `retry -> tool -> evaluate`, bounded by `max_attempts`; exhausted retries go to `dead_letter -> finalize -> END`

`classify_node` uses structured LLM output to choose the route. `answer_node` uses the LLM to generate a grounded support response from the query, tool output, proposed action, and approval decision. Tool execution is mocked so retry, approval, and dead-letter behavior can be tested deterministically.

## 3. State Schema

| Field | Reducer | Why |
|---|---|---|
| `thread_id`, `scenario_id`, `query` | overwrite | Identify and normalize a single run. |
| `route`, `risk_level` | overwrite | Keep the current routing decision and risk level. |
| `attempt`, `max_attempts` | overwrite | Bound retry behavior and prevent infinite loops. |
| `evaluation_result` | overwrite | Drive the retry-or-answer conditional edge. |
| `pending_question`, `proposed_action`, `approval`, `final_answer` | overwrite | Store the latest clarification, risky action, approval decision, and final response. |
| `messages`, `tool_results`, `errors`, `events` | append | Preserve audit trail, tool outputs, retry errors, and grading/debug evidence. |

## 4. Metrics Summary

| Metric | Value |
|---|---:|
| Total scenarios | 7 |
| Success rate | 100.00% |
| Average nodes visited | 6.43 |
| Total retries | 3 |
| Total approval/interrupt events | 2 |
| Resume success | No |

## 5. Scenario Results

| Scenario | Expected route | Actual route | Success | Retries | Interrupts |
|---|---|---|---:|---:|---:|
| S01_simple | simple | simple | Yes | 0 | 0 |
| S02_tool | tool | tool | Yes | 0 | 0 |
| S03_missing | missing_info | missing_info | Yes | 0 | 0 |
| S04_risky | risky | risky | Yes | 0 | 1 |
| S05_error | error | error | Yes | 2 | 0 |
| S06_delete | risky | risky | Yes | 0 | 1 |
| S07_dead_letter | error | error | Yes | 1 | 0 |

## 6. Failure Analysis

1. Retry or tool failure: error-route scenarios intentionally produce transient tool failures. `evaluate_node` marks failed results as `needs_retry`, then `retry_or_fallback_node` increments `attempt`. `route_after_retry` sends the workflow back to `tool` only while `attempt < max_attempts`; otherwise the request is moved to `dead_letter`.

2. Risky action without approval: refund, delete, cancellation, and outbound email requests route through `risky_action` and `approval` before any tool execution. Rejected approvals go to `clarify`, so the graph does not perform side-effecting actions without review.

Current result summary: All sample scenarios completed successfully.

## 7. Persistence / Recovery Evidence

`build_checkpointer()` supports in-memory checkpoints for tests and SQLite checkpoints for durable runs. The SQLite implementation opens `outputs/checkpoints.sqlite`, enables WAL mode, and passes the connection to `SqliteSaver`. Each scenario is invoked with a stable `thread_id`, so state history can be inspected or resumed per scenario.

Local SQLite verification found `outputs/checkpoints.sqlite` with tables checkpoints, writes. At verification time it contained 53 checkpoint rows and 278 write rows.

## 8. Extension Work

- SQLite persistence support with WAL mode.
- Optional human-in-the-loop interrupt path controlled by `LANGGRAPH_INTERRUPT=true`.
- Dead-letter route for exhausted retries.
- Report generation from metrics data.

## 9. Improvement Plan

With one more day, I would add automated state-history evidence to the CLI report, include a rendered graph diagram, and add a small approval UI for real HITL review/resume demos.
