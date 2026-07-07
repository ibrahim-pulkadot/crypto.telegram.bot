"""Kripto haberlerini arayıp okur (Google News RSS — API anahtarı gerekmez, saf Python)."""
from __future__ import annotations

import xml.etree.ElementTree as ET

import requests

# Yaygın coin sembollerini tam isimlerine çevirir — arama sonucunu alakalı tutmak için.
_COIN_NAMES = {
    "BTC": "Bitcoin", "ETH": "Ethereum", "SOL": "Solana", "BNB": "BNB",
    "XRP": "XRP Ripple", "ADA": "Cardano", "DOGE": "Dogecoin", "AVAX": "Avalanche",
    "DOT": "Polkadot", "MATIC": "Polygon", "LINK": "Chainlink", "LTC": "Litecoin",
    "TRX": "TRON kripto", "SHIB": "Shiba Inu coin", "ATOM": "Cosmos kripto",
    "UNI": "Uniswap", "TON": "Toncoin", "NEAR": "NEAR Protocol", "ARB": "Arbitrum kripto",
    "OP": "Optimism kripto", "APT": "Aptos kripto", "FIL": "Filecoin",
    "ICP": "Internet Computer kripto", "ETC": "Ethereum Classic", "XLM": "Stellar Lumens",
    "HBAR": "Hedera", "VET": "VeChain", "ALGO": "Algorand", "SUI": "Sui kripto",
    "PEPE": "Pepe coin",
}


def _search_query(symbol: str) -> str:
    base = symbol.split("/")[0].upper()
    name = _COIN_NAMES.get(base)
    return f"{name} kripto" if name else f"{base} kripto"


def fetch_news(symbol: str, limit: int = 5) -> list[dict]:
    """Sembolle ilgili güncel haber başlıklarını döndürür. Hata durumunda boş liste döner."""
    query = _search_query(symbol)
    try:
        resp = requests.get(
            "https://news.google.com/rss/search",
            params={"q": query, "hl": "tr", "gl": "TR", "ceid": "TR:tr"},
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
    except Exception:
        return []

    items = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        link = (item.findtext("link") or "").strip()
        pub = (item.findtext("pubDate") or "").strip()
        source_el = item.find("source")
        source = (source_el.text or "").strip() if source_el is not None else ""
        items.append({"title": title, "link": link, "published": pub, "source": source})
    return items


def format_news_for_prompt(news_items: list[dict]) -> str:
    """Haberleri LLM'e verilecek kısa bir madde listesine çevirir."""
    if not news_items:
        return ""
    lines = []
    for n in news_items:
        src = f" ({n['source']})" if n.get("source") else ""
        lines.append(f"- {n['title']}{src}")
    return "\n".join(lines)
