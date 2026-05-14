import json
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from hashlib import sha1
from math import sqrt
from os import getenv
from time import perf_counter
from typing import Any, Protocol
from urllib import parse as url_parse
from urllib import request as url_request

from llama_index.core.node_parser import SentenceSplitter
from llama_index.core.schema import NodeWithScore, TextNode
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.contracts.report import CitationStatus, SourceRef
from app.contracts.research_task import ResearchTaskType


class RetrievalFallbackStatus(StrEnum):
    NONE = "none"
    EMPTY = "empty"
    DEGRADED = "degraded"


class FilingDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str = Field(min_length=1, max_length=16)
    filing_type: str
    filing_date: str | None = None
    accession_number: str | None = None
    text: str = Field(min_length=1)


class FilingSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ticker: str
    filing_type: str
    filing_date: str | None = None
    accession_number: str | None = None
    section: str
    text: str


class PgVectorStoreConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    database_url: str = Field(min_length=1)
    table_name: str = Field(min_length=1)
    embedding_dimension: int = Field(gt=0)

    @field_validator("table_name")
    @classmethod
    def normalize_table_name(cls, value: str) -> str:
        normalized = value.strip()
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", normalized):
            raise ValueError("PGVector table name must be a simple SQL identifier")
        return normalized


class RetrievedNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    text: str
    retrieval_score: float
    rerank_score: float
    rerank_reason: str
    metadata: dict[str, Any]


class RetrieveEvidenceResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    ticker: str
    task_type: ResearchTaskType
    query: str
    retrieved_nodes: list[RetrievedNode]
    source_refs: list[SourceRef]
    latency_ms: int = 0
    fallback_status: RetrievalFallbackStatus = RetrievalFallbackStatus.NONE


class EmbeddingBackend(Protocol):
    def embed(self, text: str) -> dict[str, float]:
        """Return a deterministic sparse embedding for local retrieval experiments."""


class DatabaseConnection(Protocol):
    def execute(self, query: str, params: dict[str, object]) -> list[dict[str, object]]:
        """Execute a database statement and return materialized mapping rows."""

    def commit(self) -> None:
        """Commit pending database changes."""

    def close(self) -> None:
        """Release the database connection."""


class VectorStore(Protocol):
    def upsert(self, node: TextNode) -> None:
        """Persist or refresh a node embedding."""

    def search(
        self,
        *,
        query: str,
        nodes: list[TextNode],
        top_k: int,
    ) -> list[NodeWithScore]:
        """Return nearest vector candidates constrained to candidate nodes."""


class EmbeddingTransport(Protocol):
    def __call__(
        self,
        url: str,
        payload: dict[str, object],
        timeout_seconds: float,
    ) -> dict[str, object]:
        """POST an embedding request and return the decoded JSON response."""


class EmbeddingProvider(StrEnum):
    DETERMINISTIC = "deterministic"
    SILICONFLOW = "siliconflow"
    OPENAI = "openai"
    GEMINI = "gemini"


@dataclass(frozen=True)
class _SectionHeading:
    pattern: re.Pattern[str]
    canonical_name: str


@dataclass(frozen=True)
class _SectionMatch:
    start: int
    end: int
    canonical_name: str


class DeterministicFinancialEmbeddingBackend:
    def embed(self, text: str) -> dict[str, float]:
        vector: dict[str, float] = {}
        terms = _term_counts(text)
        for term, count in terms.items():
            _add_vector_weight(vector, term, float(count))
            for semantic_term in _SEMANTIC_EMBEDDING_EXPANSIONS.get(term, []):
                _add_vector_weight(vector, semantic_term, float(count))
        for phrase, semantic_terms in _SEMANTIC_PHRASE_EMBEDDINGS.items():
            if phrase in text.lower():
                for semantic_term in semantic_terms:
                    _add_vector_weight(vector, semantic_term, 1.5)
        return vector


class ProviderEmbeddingFallbackBackend:
    def __init__(
        self,
        *,
        provider: EmbeddingProvider,
        fallback_backend: EmbeddingBackend | None = None,
        degraded_reason: str,
    ) -> None:
        self.provider = provider
        self.fallback_backend = fallback_backend or DeterministicFinancialEmbeddingBackend()
        self.degraded_reason = degraded_reason

    def embed(self, text: str) -> dict[str, float]:
        return self.fallback_backend.embed(text)


class GeminiEmbeddingBackend:
    def __init__(
        self,
        *,
        api_key: str,
        model: str = "gemini-embedding-001",
        timeout_seconds: float = 8.0,
        transport: EmbeddingTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._transport = transport or _urllib_json_transport

    def embed(self, text: str) -> dict[str, float]:
        response = self._transport(
            self._embedding_url(),
            {
                "model": f"models/{self.model}",
                "content": {"parts": [{"text": text}]},
            },
            self.timeout_seconds,
        )
        values = _embedding_values_from_response(response)
        return {f"dim_{index}": value for index, value in enumerate(values)}

    def _embedding_url(self) -> str:
        return (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:embedContent?key={url_parse.quote(self.api_key)}"
        )


class InMemoryVectorStore:
    def __init__(self, embedding_backend: EmbeddingBackend) -> None:
        self.embedding_backend = embedding_backend
        self._vectors: dict[str, dict[str, float]] = {}

    def upsert(self, node: TextNode) -> None:
        self._vectors[node.node_id] = self.embedding_backend.embed(_node_embedding_text(node))

    def search(
        self,
        *,
        query: str,
        nodes: list[TextNode],
        top_k: int,
    ) -> list[NodeWithScore]:
        query_vector = self.embedding_backend.embed(query)
        scored_nodes = [
            NodeWithScore(node=node, score=score)
            for node in nodes
            for score in [_cosine_similarity(query_vector, self._vectors.get(node.node_id, {}))]
            if score > 0
        ]
        return sorted(
            scored_nodes,
            key=lambda candidate: float(candidate.score or 0.0),
            reverse=True,
        )[:top_k]


class PgVectorStore:
    def __init__(
        self,
        *,
        config: PgVectorStoreConfig,
        embedding_backend: EmbeddingBackend,
        connection_factory: Callable[[str], DatabaseConnection] | None = None,
    ) -> None:
        self.config = config
        self.embedding_backend = embedding_backend
        self._connection_factory = connection_factory or PsycopgDatabaseConnection.connect

    def initialize_schema(self) -> None:
        connection = self._connection_factory(self.config.database_url)
        try:
            connection.execute("CREATE EXTENSION IF NOT EXISTS vector", {})
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.config.table_name} (
                    node_id text PRIMARY KEY,
                    text text NOT NULL,
                    metadata jsonb NOT NULL,
                    embedding vector({self.config.embedding_dimension}) NOT NULL,
                    updated_at timestamptz NOT NULL DEFAULT now()
                )
                """,
                {},
            )
            if self.config.embedding_dimension <= 2000:
                connection.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.config.table_name}_embedding_idx
                    ON {self.config.table_name}
                    USING hnsw (embedding vector_cosine_ops)
                    """,
                    {},
                )
            connection.commit()
        finally:
            connection.close()

    def upsert(self, node: TextNode) -> None:
        connection = self._connection_factory(self.config.database_url)
        try:
            connection.execute(
                f"""
                INSERT INTO {self.config.table_name}
                    (node_id, text, metadata, embedding)
                VALUES
                    (%(node_id)s, %(text)s, %(metadata)s, %(embedding)s::vector)
                ON CONFLICT (node_id) DO UPDATE SET
                    text = EXCLUDED.text,
                    metadata = EXCLUDED.metadata,
                    embedding = EXCLUDED.embedding,
                    updated_at = now()
                """,
                {
                    "node_id": node.node_id,
                    "text": node.get_content(),
                    "metadata": _jsonb_parameter(dict(node.metadata)),
                    "embedding": _dense_vector_literal(
                        self.embedding_backend.embed(_node_embedding_text(node)),
                        self.config.embedding_dimension,
                    ),
                },
            )
            connection.commit()
        finally:
            connection.close()

    def search(
        self,
        *,
        query: str,
        nodes: list[TextNode],
        top_k: int,
    ) -> list[NodeWithScore]:
        node_by_id = {node.node_id: node for node in nodes}
        if not node_by_id:
            return []

        connection = self._connection_factory(self.config.database_url)
        try:
            rows = connection.execute(
                f"""
                SELECT
                    node_id,
                    1 - (embedding <=> %(embedding)s::vector) AS score
                FROM {self.config.table_name}
                WHERE node_id = ANY(%(node_ids)s)
                ORDER BY embedding <=> %(embedding)s::vector
                LIMIT %(limit)s
                """,
                {
                    "embedding": _dense_vector_literal(
                        self.embedding_backend.embed(query),
                        self.config.embedding_dimension,
                    ),
                    "node_ids": list(node_by_id.keys()),
                    "limit": top_k,
                },
            )
        finally:
            connection.close()

        return [
            NodeWithScore(node=node_by_id[node_id], score=score)
            for row in rows
            for node_id in [str(row["node_id"])]
            for score in [_float_from_row_value(row["score"])]
            if node_id in node_by_id and score > 0
        ]


class PsycopgDatabaseConnection:
    def __init__(self, raw_connection: Any) -> None:
        self._raw_connection = raw_connection

    @classmethod
    def connect(cls, database_url: str) -> "PsycopgDatabaseConnection":
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("Install psycopg[binary] to use the PGVector RAG store.") from error

        return cls(psycopg.connect(database_url, row_factory=dict_row))

    def execute(self, query: str, params: dict[str, object]) -> list[dict[str, object]]:
        with self._raw_connection.cursor() as cursor:
            cursor.execute(query, params)
            if cursor.description is None:
                return []
            return [dict(row) for row in cursor.fetchall()]

    def commit(self) -> None:
        self._raw_connection.commit()

    def close(self) -> None:
        self._raw_connection.close()


def build_vector_store_from_env(
    embedding_backend: EmbeddingBackend,
) -> VectorStore:
    provider_name = getenv(
        "RAG_VECTOR_STORE_PROVIDER",
        "pgvector" if getenv("RAG_VECTOR_DATABASE_URL") else "memory",
    ).lower()
    if provider_name != "pgvector":
        return InMemoryVectorStore(embedding_backend)

    database_url = getenv("RAG_VECTOR_DATABASE_URL")
    if not database_url:
        return InMemoryVectorStore(embedding_backend)

    store = PgVectorStore(
        config=PgVectorStoreConfig(
            database_url=database_url,
            table_name=getenv("RAG_VECTOR_TABLE_NAME", "rag_chunks"),
            embedding_dimension=int(getenv("RAG_EMBEDDING_DIMENSION", "3072")),
        ),
        embedding_backend=embedding_backend,
    )
    if getenv("RAG_VECTOR_INITIALIZE_SCHEMA", "false").lower() == "true":
        store.initialize_schema()
    return store


def build_embedding_backend_from_env() -> EmbeddingBackend:
    provider_name = getenv("RAG_EMBEDDING_PROVIDER", _default_embedding_provider_name()).lower()
    provider = _embedding_provider_from_name(provider_name)
    if provider == EmbeddingProvider.DETERMINISTIC:
        return DeterministicFinancialEmbeddingBackend()

    api_key = getenv("RAG_EMBEDDING_API_KEY") or _provider_default_api_key(provider)
    if not api_key:
        return ProviderEmbeddingFallbackBackend(
            provider=provider,
            degraded_reason=f"{provider.value} embedding provider is not configured.",
        )

    if provider == EmbeddingProvider.GEMINI:
        return GeminiEmbeddingBackend(api_key=api_key)

    return ProviderEmbeddingFallbackBackend(
        provider=provider,
        degraded_reason=f"{provider.value} embedding provider is not enabled in local tests.",
    )


def build_production_rag_pipeline_from_env() -> "LlamaIndexRagPipeline":
    embedding_backend = build_embedding_backend_from_env()
    return LlamaIndexRagPipeline(
        enable_hybrid_retrieval=True,
        embedding_backend=embedding_backend,
        vector_store=build_vector_store_from_env(embedding_backend),
    )


class SectionAwareFilingParser:
    def __init__(self, text_preprocessor: "FilingTextPreprocessor | None" = None) -> None:
        self.text_preprocessor = text_preprocessor or FilingTextPreprocessor()

    def parse(self, filing: FilingDocument) -> list[FilingSection]:
        cleaned_text = self.text_preprocessor.clean(filing.text)
        matches = _section_matches(cleaned_text)
        if not matches:
            return [
                FilingSection(
                    ticker=filing.ticker.upper(),
                    filing_type=filing.filing_type,
                    filing_date=filing.filing_date,
                    accession_number=filing.accession_number,
                    section="Full Filing",
                    text=cleaned_text,
                )
            ]

        sections: list[FilingSection] = []
        for index, match in enumerate(matches):
            start = match.end
            end = matches[index + 1].start if index + 1 < len(matches) else len(cleaned_text)
            text = cleaned_text[start:end].strip()
            if not text:
                continue
            sections.append(
                FilingSection(
                    ticker=filing.ticker.upper(),
                    filing_type=filing.filing_type,
                    filing_date=filing.filing_date,
                    accession_number=filing.accession_number,
                    section=match.canonical_name,
                    text=text,
                )
            )
        return sections


class FilingTextPreprocessor:
    def clean(self, text: str) -> str:
        normalized = text.replace("\u00a0", " ")
        normalized = re.sub(r"\r\n?", "\n", normalized)
        normalized = re.sub(r"[ \t]+", " ", normalized)
        normalized = re.sub(r"\n{3,}", "\n\n", normalized)
        normalized = _dedupe_repeated_lines(normalized)
        return normalized.strip()


class LlamaIndexRagPipeline:
    def __init__(
        self,
        parser: SectionAwareFilingParser | None = None,
        *,
        enable_section_filter: bool = True,
        enable_query_expansion: bool = True,
        enable_hybrid_retrieval: bool = False,
        embedding_backend: EmbeddingBackend | None = None,
        vector_store: VectorStore | None = None,
        section_chunk_max_chars: int = 1400,
        section_chunk_overlap_sentences: int = 1,
    ) -> None:
        self.parser = parser or SectionAwareFilingParser()
        self.enable_section_filter = enable_section_filter
        self.enable_query_expansion = enable_query_expansion
        self.enable_hybrid_retrieval = enable_hybrid_retrieval
        self.section_chunk_max_chars = section_chunk_max_chars
        self.section_chunk_overlap_sentences = section_chunk_overlap_sentences
        self.section_splitter = SentenceSplitter(
            chunk_size=_chunk_token_budget(section_chunk_max_chars),
            chunk_overlap=_chunk_overlap_token_budget(
                section_chunk_max_chars,
                section_chunk_overlap_sentences,
            ),
        )
        self.embedding_backend = embedding_backend or (
            build_embedding_backend_from_env()
            if enable_hybrid_retrieval
            else DeterministicFinancialEmbeddingBackend()
        )
        self.vector_store = vector_store or build_vector_store_from_env(self.embedding_backend)
        self._nodes: list[TextNode] = []
        self._node_ids: set[str] = set()
        self._hybrid_degraded_reason: str | None = None

    def ingest_filing(self, filing: FilingDocument) -> list[TextNode]:
        sections = self.parser.parse(filing)
        nodes = [
            node
            for section_index, section in enumerate(sections)
            for node in _section_to_nodes(
                section,
                section_index,
                self.section_splitter,
                self.section_chunk_max_chars,
                self.section_chunk_overlap_sentences,
            )
        ]
        new_nodes = [node for node in nodes if node.node_id not in self._node_ids]
        self._nodes.extend(new_nodes)
        self._node_ids.update(node.node_id for node in new_nodes)
        if self.enable_hybrid_retrieval and not self._hybrid_degraded_reason:
            for node in new_nodes:
                try:
                    self.vector_store.upsert(node)
                except Exception as error:
                    self._degrade_hybrid_retrieval(error)
                    break
        return new_nodes

    def retrieve_evidence(
        self,
        *,
        run_id: str,
        ticker: str,
        task_type: ResearchTaskType,
        query: str,
        sections: list[str] | None = None,
        top_k: int = 5,
    ) -> RetrieveEvidenceResult:
        started_at = perf_counter()
        expanded_query = _expand_financial_query(query) if self.enable_query_expansion else query
        requested_sections = sections if self.enable_section_filter else None
        candidates = self._retrieve_candidates(
            ticker=ticker,
            query=expanded_query,
            sections=requested_sections,
            top_k=max(top_k * 2, top_k),
        )
        ranked_nodes = self._rerank_candidates(
            query=expanded_query,
            sections=requested_sections,
            candidates=candidates,
            top_k=top_k,
            rerank_reason="hybrid_section_vector_lexical_overlap"
            if self.enable_hybrid_retrieval
            else None,
        )
        retrieved_nodes = [
            RetrievedNode(
                node_id=node.node_id,
                text=node.get_content(),
                retrieval_score=float(candidate.score or 0.0),
                rerank_score=rerank_score,
                rerank_reason=rerank_reason,
                metadata=dict(node.metadata),
            )
            for candidate, rerank_score, rerank_reason in ranked_nodes
            for node in [candidate.node]
            if isinstance(node, TextNode)
        ]
        source_refs = [
            _node_to_source_ref(candidate.node, expanded_query)
            for candidate, _, _ in ranked_nodes
            if isinstance(candidate.node, TextNode)
        ]
        return RetrieveEvidenceResult(
            run_id=run_id,
            ticker=ticker.upper(),
            task_type=task_type,
            query=query,
            retrieved_nodes=retrieved_nodes,
            source_refs=source_refs,
            latency_ms=int((perf_counter() - started_at) * 1000),
            fallback_status=self._retrieval_fallback_status(retrieved_nodes),
        )

    def _retrieve_candidates(
        self,
        *,
        ticker: str,
        query: str,
        sections: list[str] | None,
        top_k: int,
    ) -> list[NodeWithScore]:
        query_terms = _term_counts(query)
        requested_sections = _canonical_section_set(sections or [])
        ticker_nodes = [
            node
            for node in self._nodes
            if str(node.metadata.get("ticker", "")).upper() == ticker.upper()
        ]
        section_filtered_nodes = [
            node
            for node in ticker_nodes
            if not requested_sections
            or _canonical_section_name(str(node.metadata.get("section", ""))) in requested_sections
        ]
        candidate_nodes = section_filtered_nodes or ticker_nodes
        lexical_candidates = [
            NodeWithScore(node=node, score=score)
            for node in candidate_nodes
            for score in [_score_node(query_terms, node)]
            if score > 0
        ]
        if self.enable_hybrid_retrieval and not self._hybrid_degraded_reason:
            try:
                vector_candidates = self.vector_store.search(
                    query=query,
                    nodes=candidate_nodes,
                    top_k=top_k,
                )
            except Exception as error:
                self._degrade_hybrid_retrieval(error)
                vector_candidates = []
            scored_nodes = _merge_candidate_scores(lexical_candidates, vector_candidates)
        else:
            scored_nodes = lexical_candidates
        return sorted(
            scored_nodes,
            key=lambda candidate: float(candidate.score or 0.0),
            reverse=True,
        )[:top_k]

    def _rerank_candidates(
        self,
        *,
        query: str,
        sections: list[str] | None,
        candidates: list[NodeWithScore],
        top_k: int,
        rerank_reason: str | None = None,
    ) -> list[tuple[NodeWithScore, float, str]]:
        query_terms = _term_counts(query)
        requested_sections = _canonical_section_set(sections or [])
        reranked = [
            (
                candidate,
                _rerank_score(query_terms, requested_sections, candidate),
                rerank_reason
                or (
                    "section_filtered_financial_lexical_overlap"
                    if requested_sections
                    else "lexical_overlap_with_section_metadata"
                ),
            )
            for candidate in candidates
        ]
        return sorted(reranked, key=lambda item: item[1], reverse=True)[:top_k]

    def _degrade_hybrid_retrieval(self, error: Exception) -> None:
        self._hybrid_degraded_reason = f"{type(error).__name__}: {error}"

    def _retrieval_fallback_status(
        self,
        retrieved_nodes: list[RetrievedNode],
    ) -> RetrievalFallbackStatus:
        if self._hybrid_degraded_reason:
            return RetrievalFallbackStatus.DEGRADED
        if retrieved_nodes:
            return RetrievalFallbackStatus.NONE
        return RetrievalFallbackStatus.EMPTY


def _section_matches(text: str) -> list[_SectionMatch]:
    matches: list[_SectionMatch] = []
    for heading in _SECTION_HEADINGS:
        for match in heading.pattern.finditer(text):
            matches.append(
                _SectionMatch(
                    start=match.start(),
                    end=match.end(),
                    canonical_name=heading.canonical_name,
                )
            )
    return sorted(matches, key=lambda match: match.start)


def _dedupe_repeated_lines(text: str) -> str:
    lines = text.split("\n")
    counts = Counter(line.strip() for line in lines if line.strip())
    noisy_lines = {
        line
        for line, count in counts.items()
        if count >= 3 and _looks_like_filing_boilerplate_line(line)
    }
    if not noisy_lines:
        return text
    return "\n".join(line for line in lines if line.strip() not in noisy_lines)


def _looks_like_filing_boilerplate_line(line: str) -> bool:
    normalized = line.lower()
    if len(normalized) > 120:
        return False
    return any(
        marker in normalized
        for marker in (
            "table of contents",
            "page ",
            "form 10-q",
            "form 10-k",
            "commission file number",
        )
    )


def _embedding_provider_from_name(name: str) -> EmbeddingProvider:
    try:
        return EmbeddingProvider(name)
    except ValueError:
        return EmbeddingProvider.DETERMINISTIC


def _default_embedding_provider_name() -> str:
    if getenv("GEMINI_API_KEY"):
        return EmbeddingProvider.GEMINI.value
    return EmbeddingProvider.DETERMINISTIC.value


def _provider_default_api_key(provider: EmbeddingProvider) -> str | None:
    if provider == EmbeddingProvider.GEMINI:
        return getenv("GEMINI_API_KEY")
    if provider == EmbeddingProvider.SILICONFLOW:
        return getenv("SILICONFLOW_API_KEY")
    if provider == EmbeddingProvider.OPENAI:
        return getenv("OPENAI_API_KEY")
    return None


def _urllib_json_transport(
    url: str,
    payload: dict[str, object],
    timeout_seconds: float,
) -> dict[str, object]:
    body = json.dumps(payload).encode("utf-8")
    request = url_request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with url_request.urlopen(request, timeout=timeout_seconds) as response:
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Embedding provider response must be a JSON object")
    return decoded


def _embedding_values_from_response(response: dict[str, object]) -> list[float]:
    embedding = response.get("embedding")
    if not isinstance(embedding, dict):
        raise ValueError("Embedding provider response did not include embedding")
    values = embedding.get("values")
    if not isinstance(values, list):
        raise ValueError("Embedding provider response did not include embedding values")
    parsed_values: list[float] = []
    for value in values:
        if not isinstance(value, int | float):
            raise ValueError("Embedding provider returned a non-numeric embedding value")
        parsed_values.append(float(value))
    return parsed_values


def _chunk_token_budget(max_chars: int) -> int:
    return max(64, max_chars // 4)


def _chunk_overlap_token_budget(max_chars: int, overlap_sentences: int) -> int:
    if overlap_sentences <= 0:
        return 0
    return min(max(12, overlap_sentences * 32), max(16, _chunk_token_budget(max_chars) // 3))


def _section_to_nodes(
    section: FilingSection,
    section_index: int,
    splitter: SentenceSplitter,
    max_chars: int,
    overlap_sentences: int,
) -> list[TextNode]:
    chunk_texts = _split_section_text(section.text, splitter, max_chars, overlap_sentences)
    return [
        _section_chunk_to_node(
            section,
            section_index=section_index,
            chunk_index=chunk_index,
            chunk_count=len(chunk_texts),
            chunk_text=chunk_text,
        )
        for chunk_index, chunk_text in enumerate(chunk_texts)
    ]


def _split_section_text(
    text: str,
    splitter: SentenceSplitter,
    max_chars: int,
    overlap_sentences: int,
) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks = []
    for chunk in splitter.split_text(text):
        normalized_chunk = _normalize_snippet_whitespace(chunk)
        if not normalized_chunk:
            continue
        if len(normalized_chunk) <= max_chars:
            chunks.append(normalized_chunk)
            continue
        chunks.extend(_sentence_windows(normalized_chunk, max_chars, overlap_sentences))
    if chunks:
        return chunks
    return [_normalize_snippet_whitespace(text)]


def _sentence_windows(text: str, max_chars: int, overlap_sentences: int) -> list[str]:
    sentences = _sentence_units(text)
    if not sentences:
        return [_normalize_snippet_whitespace(text[:max_chars])]
    windows: list[str] = []
    start = 0
    while start < len(sentences):
        selected: list[str] = []
        cursor = start
        while cursor < len(sentences):
            candidate = _normalize_snippet_whitespace(" ".join([*selected, sentences[cursor]]))
            if selected and len(candidate) > max_chars:
                break
            selected.append(sentences[cursor])
            cursor += 1
            if len(candidate) >= max_chars:
                break
        if not selected:
            selected = [sentences[start][:max_chars]]
            cursor = start + 1
        windows.append(_normalize_snippet_whitespace(" ".join(selected)))
        if cursor >= len(sentences):
            break
        next_start = cursor - overlap_sentences
        start = max(start + 1, next_start)
    return windows


def _sentence_units(text: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text.strip())
        if sentence.strip()
    ]


def _section_chunk_to_node(
    section: FilingSection,
    *,
    section_index: int,
    chunk_index: int,
    chunk_count: int,
    chunk_text: str,
) -> TextNode:
    content_hash = sha1(chunk_text.encode("utf-8")).hexdigest()[:12]
    node_id = (
        f"{section.ticker}:{section.accession_number or 'unknown'}:"
        f"{_slug(section.section)}:{section_index}:{chunk_index}:{content_hash}"
    )
    return TextNode(
        id_=node_id,
        text=chunk_text,
        metadata={
            "ticker": section.ticker,
            "filing_type": section.filing_type,
            "filing_date": section.filing_date,
            "accession_number": section.accession_number,
            "section": section.section,
            "section_index": section_index,
            "section_chunk_index": chunk_index,
            "section_chunk_count": chunk_count,
        },
    )


def _node_to_source_ref(node: TextNode, query: str) -> SourceRef:
    return SourceRef(
        source_id=node.node_id,
        section=str(node.metadata.get("section", "unknown")),
        snippet=_matched_snippet(node.get_content(), _term_counts(query)),
        filing_type=_optional_str(node.metadata.get("filing_type")),
        filing_date=_optional_str(node.metadata.get("filing_date")),
        accession_number=_optional_str(node.metadata.get("accession_number")),
        citation_status=CitationStatus.UNVERIFIED,
    )


def _score_node(query_terms: Counter[str], node: TextNode) -> float:
    node_terms = _term_counts(node.get_content())
    return float(sum(min(count, node_terms.get(term, 0)) for term, count in query_terms.items()))


def _node_embedding_text(node: TextNode) -> str:
    return " ".join([str(node.metadata.get("section", "")), node.get_content()])


def _add_vector_weight(vector: dict[str, float], term: str, weight: float) -> None:
    vector[term] = vector.get(term, 0.0) + weight


def _cosine_similarity(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    dot_product = sum(weight * right.get(term, 0.0) for term, weight in left.items())
    if dot_product == 0:
        return 0.0
    left_norm = sqrt(sum(weight * weight for weight in left.values()))
    right_norm = sqrt(sum(weight * weight for weight in right.values()))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _dense_vector_literal(vector: dict[str, float], dimension: int) -> str:
    dense_values = [0.0] * dimension
    for key, value in vector.items():
        index = _vector_dimension_index(key, dimension)
        dense_values[index] += value
    norm = sqrt(sum(value * value for value in dense_values))
    if norm > 0:
        dense_values = [value / norm for value in dense_values]
    return "[" + ",".join(f"{value:.10g}" for value in dense_values) + "]"


def _float_from_row_value(value: object) -> float:
    if not isinstance(value, int | float | str):
        raise ValueError("PGVector score must be numeric")
    return float(value)


def _jsonb_parameter(value: dict[str, Any]) -> object:
    try:
        from psycopg.types.json import Jsonb
    except ImportError:
        return value
    return Jsonb(value)


def _vector_dimension_index(key: str, dimension: int) -> int:
    match = re.fullmatch(r"dim_(\d+)", key)
    if match:
        return int(match.group(1)) % dimension
    digest = sha1(key.encode("utf-8")).digest()
    return int.from_bytes(digest[:4], byteorder="big") % dimension


def _merge_candidate_scores(
    lexical_candidates: list[NodeWithScore],
    vector_candidates: list[NodeWithScore],
) -> list[NodeWithScore]:
    merged: dict[str, NodeWithScore] = {}
    for candidate in lexical_candidates:
        merged[candidate.node.node_id] = NodeWithScore(
            node=candidate.node,
            score=float(candidate.score or 0.0),
        )
    for candidate in vector_candidates:
        existing = merged.get(candidate.node.node_id)
        vector_score = float(candidate.score or 0.0)
        if existing is None:
            merged[candidate.node.node_id] = NodeWithScore(
                node=candidate.node,
                score=vector_score,
            )
        else:
            existing.score = float(existing.score or 0.0) + vector_score
    return list(merged.values())


def _rerank_score(
    query_terms: Counter[str],
    requested_sections: set[str],
    candidate: NodeWithScore,
) -> float:
    retrieval_score = float(candidate.score or 0.0)
    node = candidate.node
    if not isinstance(node, TextNode):
        return retrieval_score
    section_terms = _term_counts(str(node.metadata.get("section", "")))
    section_bonus = sum(1 for term in query_terms if term in section_terms) * 0.25
    requested_section_bonus = (
        2.0
        if requested_sections
        and _canonical_section_name(str(node.metadata.get("section", ""))) in requested_sections
        else 0.0
    )
    return retrieval_score + section_bonus + requested_section_bonus


def _term_counts(text: str) -> Counter[str]:
    return Counter(re.findall(r"[a-z0-9]+", text.lower()))


def _expand_financial_query(query: str) -> str:
    terms = _term_counts(query)
    expansions: list[str] = []
    normalized_query = query.lower()
    for trigger, synonyms in _FINANCIAL_QUERY_EXPANSIONS.items():
        trigger_terms = _term_counts(trigger)
        if trigger in normalized_query or all(term in terms for term in trigger_terms):
            expansions.extend(synonyms)
    return " ".join([query, *expansions])


def _canonical_section_set(sections: list[str]) -> set[str]:
    return {_canonical_section_name(section) for section in sections if section.strip()}


def _canonical_section_name(section: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", section.lower()).strip()
    aliases = {
        "mda": "md a",
        "management discussion and analysis": "md a",
        "management s discussion and analysis": "md a",
        "results of operations": "md a",
        "liquidity": "liquidity and capital resources",
        "capital resources": "liquidity and capital resources",
        "cash flow": "cash flow statement",
        "cash flows": "cash flow statement",
        "statement of cash flows": "cash flow statement",
        "statements of cash flows": "cash flow statement",
        "business drivers": "business",
    }
    return aliases.get(normalized, normalized)


def _matched_snippet(text: str, query_terms: Counter[str], max_chars: int = 500) -> str:
    sentences = [sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+", text.strip())]
    scored_sentences = [
        (index, _score_text(query_terms, sentence), sentence)
        for index, sentence in enumerate(sentences)
        if sentence
    ]
    matched = [item for item in scored_sentences if item[1] > 0]
    if not matched:
        return _normalize_snippet_whitespace(text.strip()[:max_chars])

    best_index = max(matched, key=lambda item: item[1])[0]
    start_index = best_index
    if best_index > 0 and scored_sentences[best_index - 1][1] > 0:
        start_index = best_index - 1
    selected: list[str] = []
    total_length = 0
    for _, _, sentence in scored_sentences[start_index:]:
        next_length = total_length + len(sentence) + (1 if selected else 0)
        if selected and next_length > max_chars:
            break
        selected.append(sentence)
        total_length = next_length
        if len(selected) >= 3:
            break
    return _normalize_snippet_whitespace(" ".join(selected)[:max_chars])


def _normalize_snippet_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _score_text(query_terms: Counter[str], text: str) -> float:
    text_terms = _term_counts(text)
    return float(sum(min(count, text_terms.get(term, 0)) for term, count in query_terms.items()))


def _slug(value: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", value.lower())) or "section"


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


_SECTION_HEADINGS = [
    _SectionHeading(
        re.compile(r"(?im)^\s*Item\s+1\.\s+Business\s*\n"),
        "Business",
    ),
    _SectionHeading(
        re.compile(
            r"(?im)^\s*Item\s+(?:2|7)\.\s+Management's Discussion and Analysis[^\n]*\n",
        ),
        "MD&A",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Results of Operations\s*\n"),
        "MD&A",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Item\s+1A\.\s+Risk Factors\s*\n"),
        "Risk Factors",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Segment Information\s*\n"),
        "Segment Information",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Net Sales\s*\n"),
        "Net Sales",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Liquidity and Capital Resources\s*\n"),
        "Liquidity and Capital Resources",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*(?:Consolidated\s+)?Statements? of Cash Flows\s*\n"),
        "Cash Flow Statement",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Quantitative and Qualitative Disclosures[^\n]*\n"),
        "Market Risk",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Legal Proceedings\s*\n"),
        "Legal Proceedings",
    ),
    _SectionHeading(
        re.compile(r"(?im)^\s*Controls and Procedures\s*\n"),
        "Controls and Procedures",
    ),
]


_FINANCIAL_QUERY_EXPANSIONS = {
    "gross margin": ["gross profit", "cost of sales", "margin"],
    "operating cash flow": [
        "net cash provided by operating activities",
        "cash provided by operations",
    ],
    "cash flow": ["net cash provided by operating activities", "cash flows"],
    "buybacks": ["repurchases of common stock", "share repurchases", "repurchased shares"],
    "buyback": ["repurchases of common stock", "share repurchases", "repurchased shares"],
    "capex": ["capital expenditures", "property plant equipment"],
    "guidance": ["outlook", "expectations", "forecast"],
}

_SEMANTIC_EMBEDDING_EXPANSIONS = {
    "platform": ["azure", "services", "infrastructure"],
    "support": ["services", "enterprise"],
    "cloud": ["azure", "aws", "infrastructure", "data center"],
    "restrictions": ["controls", "regulation", "regulatory"],
    "constrained": ["constraints", "supply"],
    "customers": ["customer", "demand", "usage"],
    "price": ["pricing"],
    "cuts": ["pressure", "decreased"],
    "input": ["battery", "supply"],
    "process": ["operational"],
    "failures": ["risk"],
    "trading": ["market"],
}

_SEMANTIC_PHRASE_EMBEDDINGS = {
    "enterprise services": ["support", "platform"],
    "server products": ["platform", "infrastructure"],
    "intelligent cloud": ["platform", "cloud"],
    "data centers": ["cloud", "infrastructure"],
    "export controls": ["restrictions", "regulation"],
    "supply constraints": ["constrained", "supply"],
    "customer concentration": ["customers", "risk"],
    "credit losses": ["credit", "deterioration"],
    "interest rate volatility": ["rate", "swings", "market"],
    "operational risk": ["process", "failures", "risk"],
    "pricing pressure": ["price", "cuts"],
    "battery supply": ["input", "constraints"],
    "manufacturing execution": ["execution", "uncertainty"],
}
