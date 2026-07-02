# Configuration Reference

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | (required) | OpenAI API key for gpt-5-nano |
| `MEMORA_DATA_DIR` | `~/.memora` | Root data directory |
| `MEMORA_LOG_LEVEL` | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `MEMORA_AUTO_APPROVE_THRESHOLD` | `0.85` | Confidence threshold for auto-approving proposals |
| `MEMORA_EMBEDDING_MODEL` | `all-mpnet-base-v2` | Sentence-transformers model name |

## Config File

Located at `~/.memora/config.yaml` (auto-created on first run).

```yaml
version: 1
log_level: INFO
auto_approve_threshold: 0.85

# Per-network decay rates (higher = faster decay)
decay_lambda:
  academic: 0.05
  professional: 0.03
  financial: 0.02
  health: 0.05
  personal_growth: 0.04
  social: 0.07
  ventures: 0.03

# Days without contact before relationship decays
relationship_decay_thresholds:
  close: 7
  regular: 14
  acquaintance: 30

# Spaced repetition (SM-2 algorithm)
sm2_default_easiness: 2.5

# Bridge discovery similarity threshold
bridge_similarity_threshold: 0.75

# Embedding model
embedding_model: all-mpnet-base-v2

# Connector configurations
connectors: {}
connector_sync_interval_minutes: 60
```

## Data Directory Structure

```
~/.memora/
  graph/          DuckDB database (memora.duckdb)
  vectors/        Weaviate embedded data
  models/         Cached sentence-transformers model
  backups/        Graph backups
  logs/           Structured JSON logs (memora.log, rotated at 10MB)
  config.yaml     User configuration
```

## LLM Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `llm_max_retries` | `3` | Max retry attempts for OpenAI calls |
| `llm_retry_base_delay` | `1.0` | Base delay (seconds) for exponential backoff |
| `llm_retry_max_delay` | `30.0` | Max delay (seconds) between retries |

## CRAG (Corrective RAG) Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `crag_relevance_threshold` | `0.5` | Minimum relevance score for RAG results |
| `crag_min_results` | `3` | Minimum results before triggering correction |
| `crag_term_coverage_threshold` | `0.3` | Term coverage threshold for correction |
