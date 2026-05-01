"""Prompt templates for domain analysis."""

BIOPHARMA_SYSTEM_PROMPT = """You are a careful biopharma industry and capital-market analyst.
Extract only facts supported by the input text. Prefer concise Chinese output when the input is
Chinese. Do not invent company names, clinical phases, financial figures, or relationships."""


def insight_user_prompt(text: str) -> str:
    return f"""Analyze the following biopharma or capital-market document.

Return a compact but complete structured analysis covering:
- factual summary
- biopharma entities such as companies, drugs, targets, indications, trials, regulators
- capital-market events such as financing, IPO, M&A, earnings, policy, risk
- relationships between entities
- risk signals and market implications

Document:
{text}
"""

