"""
Groq LLM processing pipeline.
Pass 1: Relevance scoring + categorization (batch filtering)
Pass 2: Summarization + why-it-matters (only for relevant articles)
"""

import os
import json
import logging
import time
import requests
from typing import Optional

from src.database.db import fetch_unscored, update_article_processing

logger = logging.getLogger(__name__)

GROQ_URL = 'https://api.groq.com/openai/v1/chat/completions'
GROQ_MODEL = 'llama-3.3-70b-versatile'
MIN_RELEVANCE_SCORE = 6.0

CATEGORIES = [
    'REGULATORY', 'PBR_VM20_VM22', 'LDTI_GAAP', 'MARKET_INTELLIGENCE',
    'COMPETITOR_INSIGHTS', 'RATINGS', 'RESEARCH', 'M_AND_A', 'TECHNOLOGY', 'ECONOMICS',
]

RELEVANCE_PROMPT = """\
You are a senior life and annuity actuarial consultant with 20+ years of experience.
Your clients are mid-to-large US life insurance carriers. You specialize in:
- Principle-Based Reserving (PBR), VM-20, VM-22
- LDTI / ASC 944 GAAP accounting
- Life reinsurance and block transactions
- Actuarial modeling (MG-ALFA, Prophet, AXIS)
- Regulatory compliance (NAIC, state DOI)
- Annuity product development (FIA, RILA, VA)
- Carrier financial analysis and M&A

You have received an article. Score its relevance to your consulting practice.

Article title: {title}
Article source: {source}
Article excerpt: {content}

Return ONLY valid JSON with no explanation, no markdown, no backticks:
{{
  "relevance_score": <integer 1-10>,
  "category": "<one of: {categories}>",
  "relevance_reason": "<one sentence explaining the score>"
}}

Scoring guide:
10 - Direct regulatory action (new actuarial guideline, NAIC vote, VM amendment)
9  - Major carrier event (earnings surprise, rating action, large reinsurance deal)
8  - Important industry development (significant research, product trend data, M&A)
7  - Useful context (consulting firm insight, economic indicator, regulatory process update)
6  - Marginally relevant (general insurance news with some L&A angle)
5  - Borderline (tangential to L&A, could be useful background)
1-4 - Not relevant (property & casualty, health only, general finance, unrelated)
"""

SUMMARIZE_PROMPT = """\
You are a senior L&A actuarial consultant writing a daily intelligence briefing for peers.
Your audience: consulting actuaries who specialize in life insurance reserving, GAAP/stat reporting, reinsurance, and product development.

Article title: {title}
Article source: {source}
Article category: {category}
Article content: {content}

Return ONLY valid JSON with no explanation, no markdown, no backticks:
{{
  "summary": "<2-3 crisp bullet points summarizing the key facts. Use '• ' prefix for each bullet. Be specific: include numbers, names, dates where available.>",
  "why_it_matters": "<1-2 sentences explaining the direct implication for L&A consulting actuaries. Be specific about which work streams are affected: reserving, GAAP, reinsurance, modeling, product, capital, etc.>"
}}
"""


def _groq_request(prompt: str, max_retries: int = 3) -> Optional[str]:
    """Make a Groq API call with retry logic. Returns response text or None."""
    api_key = os.getenv('GROQ_API_KEY')
    if not api_key:
        raise EnvironmentError("GROQ_API_KEY not set")

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }
    payload = {
        'model': GROQ_MODEL,
        'messages': [{'role': 'user', 'content': prompt}],
        'temperature': 0.1,
        'max_tokens': 400,
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(GROQ_URL, headers=headers, json=payload, timeout=60)
            if resp.status_code == 429:
                wait = 2 ** attempt
                logger.warning("Groq rate limited — waiting %ds", wait)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()['choices'][0]['message']['content'].strip()
        except requests.exceptions.Timeout:
            logger.warning("Groq timeout (attempt %d/%d)", attempt + 1, max_retries)
            time.sleep(2)
        except Exception as exc:
            logger.error("Groq error: %s", exc)
            return None

    return None


def _parse_json(text: str) -> Optional[dict]:
    """Parse JSON from Groq response, stripping any accidental markdown."""
    if not text:
        return None
    # Strip ```json fences if present
    text = text.strip()
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError as exc:
        logger.warning("JSON parse failed: %s | text: %s", exc, text[:200])
        return None


def score_article(article) -> Optional[dict]:
    """
    Pass 1: Score relevance and categorize an article.
    Returns dict with relevance_score, category, or None on failure.
    """
    content_preview = (article['content'] or article['title'] or '')[:1500]
    prompt = RELEVANCE_PROMPT.format(
        title=article['title'],
        source=article['source'],
        content=content_preview,
        categories=', '.join(CATEGORIES),
    )
    text = _groq_request(prompt)
    return _parse_json(text)


def summarize_article(article, category: str) -> Optional[dict]:
    """
    Pass 2: Generate summary bullets and why-it-matters for relevant articles.
    Returns dict with summary, why_it_matters, or None on failure.
    """
    content_preview = (article['content'] or article['title'] or '')[:2000]
    prompt = SUMMARIZE_PROMPT.format(
        title=article['title'],
        source=article['source'],
        category=category,
        content=content_preview,
    )
    text = _groq_request(prompt)
    return _parse_json(text)


def process_unscored(batch_size: int = 50, rate_limit_delay: float = 0.5) -> dict:
    """
    Main processing loop. Fetches unscored articles, runs both Groq passes.
    Returns summary stats.
    """
    articles = fetch_unscored(limit=batch_size)
    logger.info("Processing %d unscored articles through Groq", len(articles))

    stats = {'processed': 0, 'relevant': 0, 'skipped': 0, 'errors': 0}

    for article in articles:
        # Pass 1: Score relevance
        score_result = score_article(article)
        if score_result is None:
            stats['errors'] += 1
            # Mark with score=0 so we don't retry indefinitely
            update_article_processing(article['id'], article['category'] or 'MARKET_INTELLIGENCE',
                                      0.0, '', '')
            continue

        relevance_score = float(score_result.get('relevance_score', 0))
        category = score_result.get('category', article['category'] or 'MARKET_INTELLIGENCE')

        # Validate category
        if category not in CATEGORIES:
            category = article['category'] or 'MARKET_INTELLIGENCE'

        if relevance_score < MIN_RELEVANCE_SCORE:
            # Not relevant enough — save score but skip summarization
            update_article_processing(article['id'], category, relevance_score, '', '')
            stats['skipped'] += 1
            logger.debug("Scored %.1f (skip): %s", relevance_score, article['title'][:60])
        else:
            # Pass 2: Summarize
            time.sleep(rate_limit_delay)
            summary_result = summarize_article(article, category)

            summary = ''
            why_it_matters = ''
            if summary_result:
                summary = summary_result.get('summary', '')
                why_it_matters = summary_result.get('why_it_matters', '')

            update_article_processing(article['id'], category, relevance_score,
                                      summary, why_it_matters)
            stats['relevant'] += 1
            logger.info("Scored %.1f [%s]: %s", relevance_score, category, article['title'][:60])

        stats['processed'] += 1
        time.sleep(rate_limit_delay)   # be polite to the free tier

    logger.info("Groq processing complete: %s", stats)
    return stats


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    process_unscored()
