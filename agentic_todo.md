# Multi-Agentic System — Future Improvements

## 1. Output Post-Processing Validation
- Validate agent final output before returning to the user
- Check for hallucination markers (e.g. "As an AI…", "I cannot…" leaking into tool responses)
- Schema-validate structured outputs (JSON, code blocks) using pydantic models
- Detect if the agent returned an empty or trivially short response
- Optionally re-run the agent with a corrective prompt if validation fails

## 2. Session Management
- Add a session concept distinct from user identity (one user → many sessions)
- Allow the caller to pass a `session_id` alongside `user_id`
- Scope conversation history to `(user_id, session_id)` in both `InMemoryHistoryStore` and `RedisHistoryStore`
- Expose session listing and deletion via the `HistoryStore` interface
- Useful for multi-tab or multi-device UX in a frontend

## 3. Streaming Responses
- Switch `assistant.run()` to `assistant.run_stream()` from pydantic-ai
- Yield partial text tokens to a callback or async generator
- Allow the frontend/CLI to display a live typing effect
- Handle streaming errors gracefully (flush partial output, record in `RunResult`)

## 4. Startup Health Check
- On `__main__.py` startup, before running any queries:
  - Verify OpenAI API key with a lightweight test call (e.g. embedding of a single word)
  - Verify Tavily API key with a minimal search
  - Ping the E2B sandbox service
  - Ping Redis (if `RedisHistoryStore` is configured)
- Print a Rich table showing pass/fail for each service
- Exit early with a clear message if any required service is unreachable

## 5. Session-Level Metrics Summary
- After all demo queries complete, print a final Rich summary panel showing:
  - Total queries run / blocked / errored / timed out
  - Aggregate token usage (input, output, cached)
  - Aggregate cost (USD)
  - Average response time (ms)
  - Per-tool invocation counts
- Optionally write the session summary to `data/traces/session_summary_YYYY-MM-DD.json`
