"""Research tool for Robert — search GitHub, docs, and PyPI before building."""

import json
import os
import urllib.parse
from typing import Optional

from tools.base import sanitize_error
from tools.safe_fetch import safe_fetch


def search_github(query: str, language: str = "python") -> str:
    """Search GitHub repositories for relevant code and solutions."""
    try:
        encoded = urllib.parse.quote(f"{query} language:{language}")
        url = f"https://api.github.com/search/repositories?q={encoded}&sort=stars&order=desc&per_page=5"
        headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "Robert-Agent/2.0"}
        token = os.environ.get("GITHUB_TOKEN", "")
        if token:
            headers["Authorization"] = f"token {token}"

        status, body, _ = safe_fetch(url, headers=headers, timeout=10)
        data = json.loads(body.decode())

        results = []
        for repo in data.get("items", [])[:5]:
            results.append(
                f"- {repo['full_name']} ⭐{repo['stargazers_count']}: {repo.get('description','')[:100]}\n"
                f"  URL: {repo['html_url']}"
            )
        return "GitHub Results:\n" + "\n".join(results) if results else "No GitHub results found."
    except Exception as e:
        return f"GitHub search failed: {sanitize_error(str(e))}"


def search_pypi(package_name: str) -> str:
    """Get package info from PyPI."""
    try:
        # package names are path segments — keep conservative
        safe_name = urllib.parse.quote(package_name.strip(), safe="-_.")
        url = f"https://pypi.org/pypi/{safe_name}/json"
        status, body, _ = safe_fetch(
            url,
            headers={"User-Agent": "Robert-Agent/2.0"},
            timeout=10,
        )
        data = json.loads(body.decode())

        info = data.get("info", {})
        latest = max(data.get("releases", {}).keys(), default="unknown")
        return (
            f"Package: {info.get('name')}\n"
            f"Version: {latest}\n"
            f"Summary: {info.get('summary','')}\n"
            f"License: {info.get('license','')}\n"
            f"Requires Python: {info.get('requires_python','')}\n"
            f"Homepage: {info.get('home_page','') or info.get('project_url','')}"
        )
    except Exception as e:
        return f"PyPI lookup failed for '{package_name}': {sanitize_error(str(e))}"


def search_docs(query: str, source: str = "auto") -> str:
    """Fetch relevant documentation snippets (URL pointers only — no crawl)."""
    doc_sources = {
        "nextjs": "https://nextjs.org/docs",
        "supabase": "https://supabase.com/docs",
        "langgraph": "https://langchain-ai.github.io/langgraph/",
        "langchain": "https://python.langchain.com/docs/",
        "anthropic": "https://docs.anthropic.com/",
        "openai": "https://platform.openai.com/docs/",
    }

    if source == "auto":
        q_lower = query.lower()
        for key in doc_sources:
            if key in q_lower:
                source = key
                break
        else:
            source = "general"

    base_url = doc_sources.get(source, "")
    if base_url:
        return f"Documentation source for '{query}': {base_url}\nSearch this URL for: {query}"

    return (
        f"Docs search for '{query}': Use official documentation at docs.{source}.com "
        f"or search '{query} docs site:github.com'"
    )


def research(topic: str) -> str:
    """All-in-one research function — searches GitHub + PyPI for a topic."""
    results = [f"=== Research: {topic} ===\n", search_github(topic), ""]
    if " " not in topic.strip():
        results.append(search_pypi(topic.strip()))
    return "\n".join(results)


RESEARCH_TOOLS = [
    {
        "name": "search_github",
        "description": "Search GitHub repositories for code, libraries, and solutions related to a query",
        "function": search_github,
        "parameters": {
            "query": "str — search query",
            "language": "str — programming language filter (default: python)",
        },
    },
    {
        "name": "search_pypi",
        "description": "Look up a Python package on PyPI — version, description, license",
        "function": search_pypi,
        "parameters": {"package_name": "str — exact package name"},
    },
    {
        "name": "search_docs",
        "description": "Get relevant documentation for a topic (Next.js, Supabase, LangGraph, etc.)",
        "function": search_docs,
        "parameters": {
            "query": "str — what to look up",
            "source": "str — docs source: nextjs, supabase, langgraph, langchain, anthropic, openai, auto",
        },
    },
]
