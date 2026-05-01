"""SEC EDGAR submissions collection adapters."""

from __future__ import annotations

import hashlib
import json
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from email.message import Message
from typing import Any, Protocol

from biopharma_agent.collection.http_fetcher import HTTPSourceFetcher
from biopharma_agent.contracts import RawDocument, SourceRef, utc_now
from biopharma_agent.parsing.text import extract_main_text


class SECTransport(Protocol):
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        """Fetch a SEC data URL."""


class UrllibSECTransport:
    def get(self, url: str, headers: dict[str, str], timeout: float) -> tuple[int, Message, bytes]:
        request = urllib.request.Request(url=url, headers=headers, method="GET")
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.headers, response.read()


@dataclass(frozen=True)
class SECFiling:
    cik: str
    company: str
    form: str
    accession_number: str
    filing_date: str
    report_date: str
    primary_document: str
    primary_doc_description: str
    filing_url: str
    document_url: str


@dataclass(frozen=True)
class SECFetchResult:
    source: SourceRef
    status_code: int
    filings: list[SECFiling]
    searched_ciks: list[str]
    errors: list[str] | None = None

    def to_raw_documents(
        self,
        *,
        limit: int | None = None,
        fetch_details: bool = False,
        clean_html: bool = False,
        fetcher: HTTPSourceFetcher | None = None,
    ) -> list[RawDocument]:
        selected = self.filings[:limit] if limit is not None else self.filings
        documents: list[RawDocument] = []
        detail_fetcher = fetcher or HTTPSourceFetcher(respect_robots_txt=False)
        for filing in selected:
            metadata = {
                "content_type": "sec_filing",
                "collector": "sec_submissions",
                "cik": filing.cik,
                "company": filing.company,
                "form": filing.form,
                "accession_number": filing.accession_number,
                "filing_date": filing.filing_date,
                "report_date": filing.report_date,
                "primary_document": filing.primary_document,
                "primary_doc_description": filing.primary_doc_description,
                "filing_url": filing.filing_url,
            }
            raw_text = "\n\n".join(
                part
                for part in [
                    filing.company,
                    filing.form,
                    filing.primary_doc_description,
                    filing.filing_date,
                    filing.document_url,
                ]
                if part
            )
            if fetch_details and filing.document_url:
                try:
                    fetched = detail_fetcher.fetch(
                        filing.document_url,
                        source=self.source,
                        document_id=_stable_document_id(self.source.name, filing.accession_number),
                    )
                    raw_text = fetched.raw_document.raw_text or ""
                    metadata.update(
                        {
                            "detail_status_code": fetched.status_code,
                            "original_content_type": fetched.raw_document.metadata.get("content_type"),
                        }
                    )
                except Exception as exc:
                    metadata["detail_error"] = str(exc)
                if clean_html and "detail_error" not in metadata:
                    extracted = extract_main_text(raw_text)
                    metadata.update(
                        {
                            "content_type": "text/plain; charset=utf-8",
                            "original_html_length": len(raw_text),
                            "html_cleaned": True,
                            "html_extraction_method": extracted.method,
                            "html_extraction_score": extracted.score,
                        }
                    )
                    raw_text = extracted.text
            documents.append(
                RawDocument(
                    source=self.source,
                    document_id=_stable_document_id(self.source.name, filing.accession_number),
                    collected_at=utc_now(),
                    url=filing.document_url or filing.filing_url,
                    title=f"{filing.company} {filing.form} {filing.filing_date}".strip(),
                    raw_text=raw_text,
                    metadata=metadata,
                )
            )
        return documents


@dataclass
class SECSubmissionsFetcher:
    """Fetch SEC company submissions JSON for a configured CIK watchlist."""

    transport: SECTransport = UrllibSECTransport()
    user_agent: str = "biopharma-agent contact@example.com"
    timeout_seconds: float = 30.0

    def fetch(self, source: SourceRef) -> SECFetchResult:
        ciks = _string_list(source.metadata.get("ciks")) or [
            "0000078003",
            "0001682852",
            "0000318154",
            "0000882095",
            "0001804220",
        ]
        forms = set(_string_list(source.metadata.get("forms")) or ["8-K", "10-K", "10-Q", "S-1", "424B"])
        filings: list[SECFiling] = []
        errors: list[str] = []
        status_code = 0
        for cik in ciks:
            normalized_cik = normalize_cik(cik)
            url = f"https://data.sec.gov/submissions/CIK{normalized_cik}.json"
            try:
                status, headers, body = self.transport.get(
                    url,
                    headers={"User-Agent": self.user_agent, "Accept": "application/json"},
                    timeout=self.timeout_seconds,
                )
            except urllib.error.HTTPError as exc:
                errors.append(f"HTTP {exc.code} while fetching SEC submissions for {normalized_cik}")
                continue
            except (urllib.error.URLError, socket.timeout) as exc:
                errors.append(f"Failed to fetch SEC submissions for {normalized_cik}: {exc}")
                continue
            status_code = status
            charset = headers.get_content_charset() or "utf-8"
            payload = json.loads(body.decode(charset, errors="replace"))
            filings.extend(parse_sec_submissions(payload, forms=forms))
        return SECFetchResult(
            source=source,
            status_code=status_code or 200,
            filings=filings,
            searched_ciks=[normalize_cik(cik) for cik in ciks],
            errors=errors,
        )


def parse_sec_submissions(payload: dict[str, Any], *, forms: set[str]) -> list[SECFiling]:
    cik = normalize_cik(str(payload.get("cik", "")))
    company = str(payload.get("name", ""))
    recent = payload.get("filings", {}).get("recent", {}) if isinstance(payload.get("filings"), dict) else {}
    accession_numbers = _list_field(recent, "accessionNumber")
    filings: list[SECFiling] = []
    for index, accession in enumerate(accession_numbers):
        form = _field_at(recent, "form", index)
        if not _form_allowed(form, forms):
            continue
        primary_document = _field_at(recent, "primaryDocument", index)
        filing_url, document_url = sec_filing_urls(cik, accession, primary_document)
        filings.append(
            SECFiling(
                cik=cik,
                company=company,
                form=form,
                accession_number=accession,
                filing_date=_field_at(recent, "filingDate", index),
                report_date=_field_at(recent, "reportDate", index),
                primary_document=primary_document,
                primary_doc_description=_field_at(recent, "primaryDocDescription", index),
                filing_url=filing_url,
                document_url=document_url,
            )
        )
    return filings


def sec_filing_urls(cik: str, accession_number: str, primary_document: str) -> tuple[str, str]:
    accession_no_dashes = accession_number.replace("-", "")
    cik_no_leading_zero = str(int(normalize_cik(cik)))
    base = f"https://www.sec.gov/Archives/edgar/data/{cik_no_leading_zero}/{accession_no_dashes}"
    filing_url = f"{base}/{accession_number}-index.html"
    document_url = f"{base}/{primary_document}" if primary_document else filing_url
    return filing_url, document_url


def normalize_cik(value: str) -> str:
    digits = re.sub(r"\D+", "", value)
    return digits.zfill(10)


def _form_allowed(form: str, forms: set[str]) -> bool:
    if form in forms:
        return True
    return any(allowed.endswith("*") and form.startswith(allowed[:-1]) for allowed in forms) or (
        "424B" in forms and form.startswith("424B")
    )


def _list_field(payload: dict[str, Any], key: str) -> list[Any]:
    value = payload.get(key, [])
    return value if isinstance(value, list) else []


def _field_at(payload: dict[str, Any], key: str, index: int) -> str:
    values = _list_field(payload, key)
    if index >= len(values):
        return ""
    return str(values[index] or "")


def _string_list(value: object) -> list[str]:
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _stable_document_id(source_name: str, key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]
    safe_source = re.sub(r"[^a-zA-Z0-9_-]+", "-", source_name.lower()).strip("-")
    return f"{safe_source}-{digest}"
