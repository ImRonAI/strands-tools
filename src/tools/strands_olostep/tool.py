"""Olostep tools for Strands Agents."""

import logging
from typing import Any

from strands import tool

from strands_olostep._client import (
    ENDPOINT_ANSWERS,
    ENDPOINT_CRAWL,
    ENDPOINT_MAP,
    ENDPOINT_RETRIEVE,
    ENDPOINT_SCRAPE,
    ENDPOINT_SEARCH,
    OlostepError,
    error,
    get,
    ok,
    post,
)

logger = logging.getLogger(__name__)


@tool
def olostep_search(query: str, country: str = "US") -> dict[str, Any]:
    """Search the live web and return a deduplicated list of relevant links.

    Use this to discover pages relevant to a query. To read the full content of
    a result, follow up with ``olostep_scrape``. If you want a synthesized
    answer rather than a list of links, use ``olostep_answers`` instead.

    Args:
        query: The search query in plain English.
        country: Two-letter country code for localized results, e.g. ``US``, ``GB``.

    Returns:
        Dict containing status and the search results.
    """
    try:
        data = post(ENDPOINT_SEARCH, {"query": query, "country": country})
    except OlostepError as exc:
        logger.warning("olostep_search failed: %s", exc)
        return error(str(exc))
    return ok(data)


@tool
def olostep_scrape(
    url: str,
    output_format: str = "markdown",
    country: str | None = None,
    wait_before_scraping: int = 0,
) -> dict[str, Any]:
    """Fetch the content of a single web page as clean, LLM-ready text.

    Args:
        url: The URL to scrape.
        output_format: One of ``markdown``, ``html``, ``json``, or ``text``.
        country: Optional two-letter country code to route the request through.
        wait_before_scraping: Milliseconds to wait for JavaScript to render (0-10000).

    Returns:
        Dict containing status and the scraped page content.
    """
    try:
        data = post(
            ENDPOINT_SCRAPE,
            {
                "url_to_scrape": url,
                "formats": [output_format],
                "country": country,
                "wait_before_scraping": wait_before_scraping,
            },
        )
    except OlostepError as exc:
        logger.warning("olostep_scrape failed: %s", exc)
        return error(str(exc))
    return ok(data)


@tool
def olostep_answers(task: str, json_shape: str | None = None) -> dict[str, Any]:
    """Answer a question using live web data, with sources and citations.

    Prefer this over ``olostep_search`` when you want a synthesized answer
    rather than a list of links. Returns NOT_FOUND rather than guessing when
    the web cannot support a claim.

    Args:
        task: The question or research task to answer from the web.
        json_shape: Optional description or JSON schema for the desired output shape.

    Returns:
        Dict containing status, the answer, and its sources.
    """
    try:
        data = post(ENDPOINT_ANSWERS, {"task": task, "json": json_shape})
    except OlostepError as exc:
        logger.warning("olostep_answers failed: %s", exc)
        return error(str(exc))
    return ok(data)


@tool
def olostep_map(
    website_url: str,
    search_query: str | None = None,
    top_n: int = 100,
) -> dict[str, Any]:
    """Discover the URLs on a website, optionally ranked by relevance to a query.

    Args:
        website_url: The site to map, e.g. ``https://example.com``.
        search_query: Optional query used to rank the returned URLs.
        top_n: Maximum number of URLs to return.

    Returns:
        Dict containing status and the discovered URLs.
    """
    try:
        data = post(
            ENDPOINT_MAP,
            {"url": website_url, "search_query": search_query, "top_n": top_n},
        )
    except OlostepError as exc:
        logger.warning("olostep_map failed: %s", exc)
        return error(str(exc))
    return ok(data)


@tool
def olostep_crawl(
    start_url: str,
    max_pages: int = 25,
    include_urls: list[str] | None = None,
    exclude_urls: list[str] | None = None,
) -> dict[str, Any]:
    """Start a crawl that follows links from a starting URL.

    This kicks off an asynchronous job and returns a crawl id. The crawl runs in
    the background and this call does NOT return page content. Call
    ``olostep_get_crawl_results`` with the returned id to poll status and fetch
    the crawled pages.

    Args:
        start_url: The URL to begin crawling from.
        max_pages: Maximum number of pages to crawl.
        include_urls: Optional glob patterns to include, e.g. ``["/docs/**"]``.
        exclude_urls: Optional glob patterns to exclude, e.g. ``["/blog/**"]``.

    Returns:
        Dict containing status and the crawl job details, including its id.
    """
    try:
        data = post(
            ENDPOINT_CRAWL,
            {
                "start_url": start_url,
                "max_pages": max_pages,
                "include_urls": include_urls,
                "exclude_urls": exclude_urls,
            },
        )
    except OlostepError as exc:
        logger.warning("olostep_crawl failed: %s", exc)
        return error(str(exc))
    return ok(data)


@tool
def olostep_get_crawl_results(
    crawl_id: str,
    output_format: str = "markdown",
    items_limit: int = 10,
) -> dict[str, Any]:
    """Fetch the status and page content for a crawl started with ``olostep_crawl``.

    This is the required companion to ``olostep_crawl``. If the crawl is still
    running, this returns its progress so you can call again shortly.

    Args:
        crawl_id: The id returned by ``olostep_crawl``.
        output_format: One of ``markdown``, ``html``, ``json``, or ``text``.
        items_limit: Maximum number of pages to fetch content for (1-100).

    Returns:
        Dict containing status, crawl progress, and the retrieved pages.
    """
    try:
        status = get(f"{ENDPOINT_CRAWL}/{crawl_id}")

        if status.get("status") != "completed":
            return ok(
                {
                    "crawl_id": crawl_id,
                    "status": status.get("status"),
                    "pages_count": status.get("pages_count"),
                    "max_pages": status.get("max_pages"),
                    "message": "Crawl is still running. Call this tool again in about 10 seconds.",
                }
            )

        listing = get(f"{ENDPOINT_CRAWL}/{crawl_id}/pages")
        entries = listing.get("pages") or listing.get("items") or []

        pages: list[dict[str, Any]] = []
        for entry in entries[:items_limit]:
            retrieve_id = entry.get("retrieve_id")
            page: dict[str, Any] = {"url": entry.get("url")}
            if retrieve_id:
                try:
                    content = get(
                        ENDPOINT_RETRIEVE,
                        {"retrieve_id": retrieve_id, "formats": output_format},
                    )
                    page["content"] = content
                except OlostepError as exc:
                    page["error"] = str(exc)
            pages.append(page)
    except OlostepError as exc:
        logger.warning("olostep_get_crawl_results failed: %s", exc)
        return error(str(exc))

    return ok(
        {
            "crawl_id": crawl_id,
            "status": "completed",
            "pages_returned": len(pages),
            "pages_total": len(entries),
            "pages": pages,
        }
    )
