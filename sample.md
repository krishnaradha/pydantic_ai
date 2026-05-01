Good architecture overall — solid foundation. I can spot 6 gaps worth addressing before implementing, ranging from correctness issues to things that will bite during implementation:

1. SSE streaming + multi-replica = broken without a fix
The roadmap lists streaming (SSE) but with least_conn load balancing, a stream opened to replica 1 can't continue if Nginx picks replica 2 for the next request. Two ways to solve it — pick one now so it shapes the implementation:

Sticky sessions (ip_hash on Nginx) — simple, but ties a user to one replica
Redis pub/sub — any replica publishes stream chunks, any replica can serve them — more resilient but more complex
2. Cache goes stale when docs change
When the cron job re-embeds a modified or deleted document in ChromaDB, Redis still holds cached answers that referenced that document. Those answers are now wrong. The cron job needs to also invalidate Redis entries for the affected document — either by tagging cache entries with source document metadata, or a simpler full-cache flush on any doc change.

3. No shared volume for /upload-docs
The FastAPI /upload-docs endpoint (in the roadmap) needs to write files somewhere the cron job container can read. Right now there's no shared volume between agent containers and the cron job. Needs a named volume (e.g. docs_data) mounted in both.

4. Network isolation is missing
Everything is currently on one implied Docker network — meaning ChromaDB and Redis are technically reachable from the frontend container. Worth splitting into two networks explicitly:

frontend-net: browser ↔ frontend Nginx ↔ reverse proxy
backend-net: reverse proxy ↔ agents ↔ Redis ↔ ChromaDB ↔ cron job
5. No Nginx health checks or Redis fallback
If an agent replica crashes, Nginx keeps routing requests to it until it times out. Nginx supports active health checks (health_check directive) — should be in the config.

Similarly, if Redis goes down, the current design has no fallback. Agents should degrade gracefully — bypass the cache and hit the full pipeline rather than returning a 500.

6. No rate limiting
Every cache miss triggers an OpenAI embedding call + full agent pipeline. A burst of requests (or a bad actor) could spike API costs fast. Nginx can rate-limit /api/* per IP with a single limit_req_zone directive — cheap to add now, painful to retrofit later.