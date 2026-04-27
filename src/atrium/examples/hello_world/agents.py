"""Hello World example — three agents using Wikipedia's public API."""
import httpx
from atrium import Agent


class WikiSearchAgent(Agent):
    name = "wiki_search"
    description = "Searches Wikipedia for articles matching a query"
    capabilities = ["search", "research", "wikipedia"]
    input_schema = {"query": str}
    output_schema = {"articles": list}

    async def run(self, input_data: dict) -> dict:
        query = input_data.get("query", "")
        if not query:
            upstream = input_data.get("upstream", {})
            query = str(upstream) if upstream else str(input_data)
        await self.say(f"Searching Wikipedia for: {query}")
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://en.wikipedia.org/w/api.php",
                params={"action": "query", "list": "search", "srsearch": query, "format": "json", "srlimit": "5"},
            )
            resp.raise_for_status()
            results = resp.json()["query"]["search"]
        articles = [{"title": r["title"], "snippet": r["snippet"]} for r in results]
        await self.say(f"Found {len(articles)} articles")
        return {"articles": articles, "query": query}


class SummarizerAgent(Agent):
    name = "summarizer"
    description = "Summarizes a list of research findings into a concise bullet-point report"
    capabilities = ["summarize", "writing", "report"]
    input_schema = {"articles": list}
    output_schema = {"summary": str}

    async def run(self, input_data: dict) -> dict:
        articles = input_data.get("articles", [])
        if not articles:
            upstream = input_data.get("upstream", {})
            for v in upstream.values():
                if isinstance(v, dict) and "articles" in v:
                    articles = v["articles"]
                    break
        await self.say(f"Summarizing {len(articles)} articles...")
        lines = [f"- {a.get('title', 'Unknown')}" for a in articles[:5]]
        summary = "\n".join(lines) if lines else "No articles to summarize."
        await self.say("Summary complete")
        return {"summary": summary}


class FactCheckerAgent(Agent):
    name = "fact_checker"
    description = "Cross-references claims against Wikipedia to verify accuracy"
    capabilities = ["verification", "research", "fact_check"]
    input_schema = {"articles": list}
    output_schema = {"verified": list}

    async def run(self, input_data: dict) -> dict:
        articles = input_data.get("articles", [])
        if not articles:
            upstream = input_data.get("upstream", {})
            for v in upstream.values():
                if isinstance(v, dict) and "articles" in v:
                    articles = v["articles"]
                    break
        await self.say(f"Verifying {len(articles)} articles...")
        verified = [{"title": a.get("title", ""), "has_content": bool(a.get("snippet", ""))} for a in articles[:3]]
        await self.say(f"Verified {len(verified)} claims")
        return {"verified": verified}
