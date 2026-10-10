import datetime as dt
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = "https://ojoisrael.github.io"
TAVILY_KEY = os.environ["TAVILY_API_KEY"]
GEMINI_KEY = os.environ["GEMINI_API_KEY"]
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
TODAY = dt.datetime.now(dt.timezone.utc).date().isoformat()

def request_json(url, payload=None, headers=None, method=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:1500]
        raise RuntimeError(f"API request failed ({exc.code}): {detail}") from exc

def safe_slug(value):
    value = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return value[:65].strip("-") or "ai-automation-update"

def esc(value):
    return html.escape(str(value or ""), quote=True)

def clean_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()

def get_recent_titles():
    # Avoid repeating topics by giving the model recent published titles.
    try:
        with urllib.request.urlopen(f"{ROOT}/news.html", timeout=20) as response:
            page = response.read().decode("utf-8", "replace")
        return re.findall(r"<h[23][^>]*>(.*?)</h[23]>", page, flags=re.I | re.S)[:15]
    except Exception:
        return []

def main():
    query = (
        "latest important AI artificial intelligence AI agents workflow automation "
        "n8n Make.com API business automation announcements research product releases "
        "published in the last 24 hours official sources"
    )
    search = request_json(
        "https://api.tavily.com/search",
        {"api_key": TAVILY_KEY, "query": query, "topic": "news",
         "search_depth": "advanced", "max_results": 10, "days": 2,
         "include_answer": False, "include_raw_content": False}
    )
    results = search.get("results", [])
    sources = []
    seen_urls = set()
    for item in results:
        url = clean_text(item.get("url"))
        title = clean_text(item.get("title"))
        content = clean_text(item.get("content"))
        if not url.startswith("https://") or not title or not content or url in seen_urls:
            continue
        seen_urls.add(url)
        sources.append({"title": title, "url": url, "content": content[:1800],
                        "published_date": item.get("published_date")})
    if len(sources) < 2:
        print("Skipping publication: fewer than two usable sources.")
        return

    recent_titles = [clean_text(re.sub(r"<[^>]+>", "", x)) for x in get_recent_titles()]
    prompt = f"""
You are an accurate technology journalist writing for Nigerian business owners, marketers,
operations teams and automation builders. Select at most ONE genuinely important and timely
development from these search results. Prefer official announcements, documentation, original
research or reputable reporting. Do not invent facts, dates, numbers, quotes, capabilities,
availability or source links. Do not simply rewrite a headline. Explain what is confirmed,
what remains uncertain, and practical implications. Avoid promotional language and SEO filler.
Do not make financial, legal or safety claims without evidence. If none merits a useful article,
return exactly a JSON object with publish=false and reason.
Do not repeat or closely duplicate these recent headings: {json.dumps(recent_titles)}.
Use only facts supported by the supplied search results. Use source indices for citations.
Aim for 700-1000 words, but be concise where the story warrants it.
Return JSON only, matching this schema:
{{
 "publish": true,
 "reason": "",
 "title": "specific factual title, not clickbait",
 "meta_description": "120-160 characters",
 "excerpt": "2-3 sentence summary for the News page",
 "search_intent": "short description",
 "sections": [{{"heading":"...", "paragraphs":["...","..."]}}],
 "takeaways": ["...","...","..."],
 "source_indices": [0,1]
}}
Rules: 4-6 sections, each with 1-3 clear paragraphs. Include a section explaining practical implications. Only cite source indices that directly support the story. Require at least two distinct sources, preferably one primary source. Never fabricate a first-person test or imply the author tested a product.
SEARCH RESULTS:
{json.dumps(sources, ensure_ascii=False)}
"""
    gemini = request_json(
        f"https://generativelanguage.googleapis.com/v1beta/models/{urllib.parse.quote(MODEL)}:generateContent?key={urllib.parse.quote(GEMINI_KEY)}",
        {"contents": [{"parts": [{"text": prompt}]}],
         "generationConfig": {"temperature": 0.25, "responseMimeType": "application/json"}}
    )
    try:
        raw = gemini["candidates"][0]["content"]["parts"][0]["text"]
        article = json.loads(raw)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Gemini did not return valid article JSON.") from exc

    if not article.get("publish"):
        print("Skipping publication: " + clean_text(article.get("reason", "No story passed quality checks.")))
        return
    title = clean_text(article.get("title"))
    meta = clean_text(article.get("meta_description"))
    excerpt = clean_text(article.get("excerpt"))
    sections = article.get("sections", [])
    takeaways = article.get("takeaways", [])
    indices = article.get("source_indices", [])
    chosen = []
    for index in indices:
        if isinstance(index, int) and 0 <= index < len(sources):
            candidate = sources[index]
            if candidate["url"] not in [s["url"] for s in chosen]:
                chosen.append(candidate)
    if not title or not meta or not excerpt or len(sections) < 3 or len(chosen) < 2:
        raise RuntimeError("Article failed quality checks: missing title/meta/sections or fewer than two cited sources.")
    if len(meta) > 180:
        meta = meta[:177].rsplit(" ", 1)[0] + "..."
    slug = f"{TODAY}-{safe_slug(title)}"
    path = f"news/{slug}.html"
    published = dt.datetime.now(dt.timezone.utc).strftime("%B %-d, %Y")
    nav = '<header class="site-header"><div class="container nav"><a class="brand" href="/">Ojo Israel</a><nav><a href="/">Guides</a><a href="/articles/">Articles</a><a href="/news.html">AI News</a><a href="/about.html">About</a><a href="https://ojo-israel-portfolio.lovable.app" target="_blank" rel="noopener">Portfolio</a></nav></div></header>'
    parts = [
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">",
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{esc(title)} | Ojo Israel</title>",
        f'<meta name="description" content="{esc(meta)}">',
        f'<link rel="canonical" href="{ROOT}/{path}">',
        '<link rel="stylesheet" href="../styles.css"></head><body>',
        nav,
        '<main class="container article">',
        '<p class="back"><a href="/news.html">← Back to AI News</a></p>',
        '<p class="eyebrow">AI NEWS · PRACTICAL ANALYSIS</p>',
        f"<h1>{esc(title)}</h1>",
        f'<p class="intro">{esc(excerpt)}</p>',
        f'<p><strong>Published:</strong> {esc(published)} · <strong>Reading time:</strong> about {max(3, min(8, sum(len(clean_text(p).split()) for s in sections for p in s.get("paragraphs", [])) // 220))} minutes</p>'
    ]
    for section in sections:
        heading = clean_text(section.get("heading"))
        if not heading:
            continue
        parts.append(f"<h2>{esc(heading)}</h2>")
        for paragraph in section.get("paragraphs", []):
            paragraph = clean_text(paragraph)
            if paragraph:
                parts.append(f"<p>{esc(paragraph)}</p>")
    if takeaways:
        parts.append("<h2>Practical takeaways</h2><ul>")
        for takeaway in takeaways[:6]:
            parts.append(f"<li>{esc(clean_text(takeaway))}</li>")
        parts.append("</ul>")
    parts.append("<h2>Sources</h2><ol>")
    for source in chosen:
        parts.append(f'<li><a href="{esc(source["url"])}" target="_blank" rel="noopener noreferrer">{esc(source["title"])}</a>')
        if source.get("published_date"):
            parts.append(f" <span>({esc(source['published_date'])})</span>")
        parts.append("</li>")
    parts.append("</ol><p class=\"note\">This article summarizes publicly available sources. Details can change; follow the linked original sources for the latest information.</p>")
    parts.append('<p><a href="/articles/">Explore practical AI and workflow automation guides →</a></p></main>')
    parts.append('<footer><div class="container">Built by Ojo Israel — AI & Workflow Automation Specialist · <a href="https://ojo-israel-portfolio.lovable.app">Portfolio</a></div></footer></body></html>')
    article_html = "\n".join(parts) + "\n"

    os.makedirs("news", exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        file.write(article_html)

    news_path = "news.html"
    with open(news_path, encoding="utf-8") as file:
        page = file.read()
    card = (
        '\n    <article class="card">\n'
        f'      <p class="tag">AI NEWS · {esc(published.upper())}</p>\n'
        f'      <h3><a href="/{path}">{esc(title)}</a></h3>\n'
        f'      <p>{esc(excerpt)}</p>\n'
        f'      <a class="read" href="/{path}">Read the analysis →</a>\n'
        '    </article>\n'
    )
    marker = '<h2>Latest updates</h2>'
    if marker not in page:
        raise RuntimeError("Could not find Latest updates section in news.html.")
    page = page.replace(marker, marker + card, 1)
    with open(news_path, "w", encoding="utf-8") as file:
        file.write(page)

    sitemap_path = "sitemap.xml"
    tree = ET.parse(sitemap_path)
    root = tree.getroot()
    ns = "{http://www.sitemaps.org/schemas/sitemap/0.9}"
    new_url = f"{ROOT}/{path}"
    if not any(node.find(f"{ns}loc") is not None and node.find(f"{ns}loc").text == new_url for node in root.findall(f"{ns}url")):
        url_node = ET.SubElement(root, f"{ns}url")
        ET.SubElement(url_node, f"{ns}loc").text = new_url
        ET.SubElement(url_node, f"{ns}lastmod").text = TODAY
    tree.write(sitemap_path, encoding="utf-8", xml_declaration=True)
    print(f"Prepared article: {path}")
    print(f"Title: {title}")
    print(f"Sources used: {len(chosen)}")
    print("GitHub Actions will commit the article, News listing and sitemap.")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
