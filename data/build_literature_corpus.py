"""
Pull the RAG corpus straight from PubMed so every document the chat cites is a real,
checkable record (title, authors, journal, year, DOI and abstract exactly as indexed).

Run once (needs internet), commit the resulting JSON:
    python data/build_literature_corpus.py

Output: data/literature_corpus.json  -> {pmid: {...PubMed metadata + abstract...}}
Our own annotations (which sensor a paper informs, thresholds it reports, graph links)
live separately in data/literature_data.py and are keyed by the same PMID.
"""

import json
import time
import xml.etree.ElementTree as ET
from pathlib import Path

import requests

from literature_data import PAPER_ANNOTATIONS

OUT = Path(__file__).resolve().parent / "literature_corpus.json"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def text_of(el):
    return "".join(el.itertext()).strip() if el is not None else ""


def parse_article(art):
    cit = art.find("MedlineCitation")
    a = cit.find("Article")
    pmid = text_of(cit.find("PMID"))

    authors = []
    for au in a.findall("AuthorList/Author"):
        last, init = text_of(au.find("LastName")), text_of(au.find("Initials"))
        if last:
            authors.append(f"{last} {init}".strip())
        elif au.find("CollectiveName") is not None:
            authors.append(text_of(au.find("CollectiveName")))

    sections = []
    for ab in a.findall("Abstract/AbstractText"):
        label = ab.get("Label")
        body = text_of(ab)
        sections.append(f"{label}: {body}" if label else body)

    year = text_of(a.find("Journal/JournalIssue/PubDate/Year"))
    if not year:
        year = text_of(a.find("Journal/JournalIssue/PubDate/MedlineDate"))[:4]

    doi = ""
    for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "doi":
            doi = text_of(aid)
    pmcid = ""
    for aid in art.findall("PubmedData/ArticleIdList/ArticleId"):
        if aid.get("IdType") == "pmc":
            pmcid = text_of(aid)

    return pmid, {
        "pmid": pmid,
        "pmcid": pmcid,
        "doi": doi,
        "title": text_of(a.find("ArticleTitle")).rstrip("."),
        "authors": ", ".join(authors),
        "journal": text_of(a.find("Journal/ISOAbbreviation")) or text_of(a.find("Journal/Title")),
        "year": int(year) if year.isdigit() else None,
        "abstract": "\n".join(sections),
        "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
        "doi_url": f"https://doi.org/{doi}" if doi else "",
    }


def main():
    pmids = [a["pmid"] for a in PAPER_ANNOTATIONS]
    corpus = {}
    for i in range(0, len(pmids), 20):
        batch = pmids[i:i + 20]
        resp = requests.get(EFETCH, params={"db": "pubmed", "id": ",".join(batch), "retmode": "xml"}, timeout=60)
        resp.raise_for_status()
        for art in ET.fromstring(resp.content).findall("PubmedArticle"):
            pmid, rec = parse_article(art)
            corpus[pmid] = rec
        time.sleep(0.4)

    missing = set(pmids) - set(corpus)
    if missing:
        raise SystemExit(f"PubMed returned nothing for PMIDs: {sorted(missing)}")
    OUT.write_text(json.dumps(corpus, indent=2, ensure_ascii=False), encoding="utf-8")
    no_abs = [p for p, r in corpus.items() if not r["abstract"]]
    print(f"Wrote {len(corpus)} PubMed records -> {OUT}")
    if no_abs:
        print(f"Note: no abstract indexed on PubMed for {no_abs} (title + annotations only)")


if __name__ == "__main__":
    main()
