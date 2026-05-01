"""Local end-to-end document workflow."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import uuid4

from biopharma_agent.analysis.pipeline import BiopharmaAnalysisPipeline
from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.contracts import PipelineResult, RawDocument, SourceRef
from biopharma_agent.llm.base import LLMProvider
from biopharma_agent.parsing.text import parse_raw_document
from biopharma_agent.storage.graph import KnowledgeGraphWriter
from biopharma_agent.storage.raw_archive import RawArchive
from biopharma_agent.storage.repository import AnalysisRepository


@dataclass
class LocalDocumentWorkflow:
    """Run a single document through archive, parse, LLM analysis, and result storage."""

    llm: LLMProvider
    raw_archive: RawArchive | None = None
    analysis_repository: AnalysisRepository | None = None
    graph_writer: KnowledgeGraphWriter | None = None

    def run_text(
        self,
        text: str,
        source_name: str = "manual",
        title: str | None = None,
        url: str | None = None,
        document_id: str | None = None,
    ) -> PipelineResult:
        raw = RawDocument(
            source=SourceRef(name=source_name, kind="manual", url=url),
            document_id=document_id or str(uuid4()),
            url=url,
            title=title,
            raw_text=text,
        )
        return self.run_raw(raw)

    def run_raw(self, raw: RawDocument) -> PipelineResult:
        if self.raw_archive:
            raw_uri = self.raw_archive.save(raw)
            raw = RawDocument(
                source=raw.source,
                document_id=raw.document_id,
                collected_at=raw.collected_at,
                url=raw.url,
                title=raw.title,
                raw_text=raw.raw_text,
                raw_uri=raw_uri,
                metadata=raw.metadata,
            )

        parsed = parse_raw_document(raw)
        pipeline = BiopharmaAnalysisPipeline(self.llm)
        insight = pipeline.extract_insight(parsed.text)
        result = PipelineResult(
            document=parsed,
            insight=insight,
            model=getattr(self.llm, "settings", None).model
            if hasattr(getattr(self.llm, "settings", None), "model")
            else "unknown",
            provider=self.llm.provider_name,
        )

        if self.analysis_repository:
            self.analysis_repository.append(result)
        if self.graph_writer:
            self.graph_writer.write_insight(result)
        return result

    def run_url(
        self,
        url: str,
        source_name: str | None = None,
        fetcher: HTTPSourceFetcher | None = None,
    ) -> PipelineResult:
        fetcher = fetcher or HTTPSourceFetcher()
        source = SourceRef(name=source_name or url, kind="web", url=url)
        fetched = fetcher.fetch(url, source=source)
        return self.run_raw(fetched.raw_document)
