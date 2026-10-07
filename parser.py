"""
parser.py — HTML parser for Movie Agent
Extracts movie metadata from HTML using OG tags, JSON-LD, and CSS selectors.
"""

import re
import json
import copy
from typing import Dict, Any, Optional
from urllib.parse import urljoin
from bs4 import BeautifulSoup
from logger import get_logger

logger = get_logger(__name__)


class MovieParser:
    """
    Parses raw HTML from movie pages to extract metadata.
    Uses multiple strategies: JSON-LD, Open Graph, CSS selectors.
    """

    # Precompiled regex (performance)
    YEAR_REGEX = re.compile(r'\b(19\d{2}|20\d{2})\b')
    RATING_REGEX = re.compile(r'(\d{1,2}(?:\.\d{1,2})?)')
    AD_KEYWORDS = ['ads', 'doubleclick', 'googleads', 'googlesyndication',
                   'analytics', 'adservice', 'adsystem', 'adserver']

    # Default placeholder values
    DEFAULT_DATA = {
        'title': 'Unknown Title',
        'poster_url': '',
        'description': 'No description available.',
        'year': '',
        'rating': 'N/A',
        'video_url': '',
        'cast': '',
        'category': ''
    }

    def __init__(self):
        pass

    # =========================================================
    # MAIN
    # =========================================================

    def parse_movie_page(self, html_content: str, base_url: str = '') -> Dict[str, Any]:
        """
        Parse HTML and extract movie metadata.
        Args:
            html_content: raw HTML string
            base_url: page URL (for absolute URL resolution)
        Returns: dict with movie data
        """
        if not html_content:
            logger.error("Empty HTML provided to parser.")
            return copy.deepcopy(self.DEFAULT_DATA)

        try:
            soup = BeautifulSoup(html_content, 'html.parser')
            movie_data = copy.deepcopy(self.DEFAULT_DATA)

            # Try JSON-LD first (most reliable)
            json_ld = self._extract_json_ld(soup)

            # Extract each field (JSON-LD → OG → CSS selectors)
            movie_data['title'] = self._extract_title(soup, json_ld)
            movie_data['poster_url'] = self._extract_poster(soup, json_ld, base_url)
            movie_data['description'] = self._extract_description(soup, json_ld)
            movie_data['year'] = self._extract_year(soup, movie_data['title'], json_ld)
            movie_data['rating'] = self._extract_rating(soup, json_ld)
            movie_data['video_url'] = self._extract_video_url(soup, base_url)
            movie_data['cast'] = self._extract_cast(soup)
            movie_data['category'] = self._extract_category(soup)

            logger.info(f"Parsed: {movie_data['title']} ({movie_data['year']})")
            return movie_data

        except Exception as e:
            logger.error(f"Critical parse error: {e}")
            return copy.deepcopy(self.DEFAULT_DATA)

    # =========================================================
    # JSON-LD (Structured Data)
    # =========================================================

    def _extract_json_ld(self, soup: BeautifulSoup) -> Dict:
        """Extract Movie data from JSON-LD structured data."""
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                if not script.string:
                    continue
                try:
                    data = json.loads(script.string)

                    # Handle list
                    if isinstance(data, list):
                        for item in data:
                            if isinstance(item, dict) and item.get('@type') in ('Movie', 'TVSeries', 'VideoObject'):
                                return item
                    # Handle dict
                    elif isinstance(data, dict):
                        if data.get('@type') in ('Movie', 'TVSeries', 'VideoObject'):
                            return data
                        # @graph
                        if '@graph' in data:
                            for item in data['@graph']:
                                if item.get('@type') in ('Movie', 'TVSeries', 'VideoObject'):
                                    return item
                except json.JSONDecodeError:
                    continue
        except Exception as e:
            logger.debug(f"JSON-LD extraction failed: {e}")
        return {}

    # =========================================================
    # TITLE
    # =========================================================

    def _extract_title(self, soup: BeautifulSoup, json_ld: Dict) -> str:
        """Extract title: JSON-LD → OG → Twitter → H1 → title tag."""
        # 1. JSON-LD
        if json_ld.get('name'):
            return str(json_ld['name']).strip()

        # 2. OG
        og = soup.find('meta', property='og:title')
        if og and og.get('content'):
            return og['content'].strip()

        # 3. Twitter
        tw = soup.find('meta', attrs={'name': 'twitter:title'})
        if tw and tw.get('content'):
            return tw['content'].strip()

        # 4. H1
        h1 = soup.find('h1')
        if h1:
            text = h1.get_text(strip=True)
            if text:
                return text

        # 5. Title tag
        if soup.title and soup.title.string:
            return soup.title.string.strip()

        return "Unknown Title"

    # =========================================================
    # POSTER
    # =========================================================

    def _extract_poster(self, soup: BeautifulSoup, json_ld: Dict, base_url: str) -> str:
        """Extract poster: JSON-LD → OG → Twitter → img tag."""
        # 1. JSON-LD
        if json_ld.get('image'):
            img = json_ld['image']
            if isinstance(img, list):
                img = img[0]
            if isinstance(img, dict):
                img = img.get('url', '')
            if img:
                return urljoin(base_url, str(img).strip())

        # 2. OG image
        og = soup.find('meta', property='og:image')
        if og and og.get('content'):
            return urljoin(base_url, og['content'].strip())

        # 3. Twitter image
        tw = soup.find('meta', attrs={'name': 'twitter:image'})
        if tw and tw.get('content'):
            return urljoin(base_url, tw['content'].strip())

        # 4. img tag with poster/thumb/cover class
        for pattern in ['poster', 'thumb', 'cover', 'movie']:
            img = soup.find('img', class_=re.compile(pattern, re.I))
            if img and img.get('src'):
                return urljoin(base_url, img['src'].strip())

        # 5. First large img
        for img in soup.find_all('img', src=True):
            src = img['src']
            if any(ext in src.lower() for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                return urljoin(base_url, src.strip())

        return ""

    # =========================================================
    # DESCRIPTION
    # =========================================================

    def _extract_description(self, soup: BeautifulSoup, json_ld: Dict) -> str:
        """Extract description: JSON-LD → OG → Twitter → div/p."""
        # 1. JSON-LD
        if json_ld.get('description'):
            return str(json_ld['description']).strip()

        # 2. OG
        og = soup.find('meta', property='og:description')
        if og and og.get('content'):
            return og['content'].strip()

        # 3. Twitter
        tw = soup.find('meta', attrs={'name': 'twitter:description'})
        if tw and tw.get('content'):
            return tw['content'].strip()

        # 4. Standard meta
        meta = soup.find('meta', attrs={'name': 'description'})
        if meta and meta.get('content'):
            return meta['content'].strip()

        # 5. div/p with desc/synopsis/plot class
        for pattern in ['desc', 'synopsis', 'plot', 'summary', 'storyline']:
            div = soup.find(['div', 'p', 'span'], class_=re.compile(pattern, re.I))
            if div:
                text = div.get_text(strip=True)
                if text and len(text) > 20:
                    return text

        return "No description available."

    # =========================================================
    # YEAR
    # =========================================================

    def _extract_year(self, soup: BeautifulSoup, title: str, json_ld: Dict) -> str:
        """Extract year: JSON-LD → title → class-based."""
        # 1. JSON-LD
        for key in ('datePublished', 'dateCreated', 'releaseDate'):
            if json_ld.get(key):
                match = self.YEAR_REGEX.search(str(json_ld[key]))
                if match:
                    return match.group(1)

        # 2. Title se (brackets mein)
        match = re.search(r'\((\d{4})\)', title)
        if match:
            return match.group(1)

        # 3. Title se (standalone 4-digit)
        match = self.YEAR_REGEX.search(title)
        if match:
            return match.group(1)

        # 4. Class-based (year/date/release)
        year_tag = soup.find(
            ['span', 'div', 'a'],
            class_=re.compile(r'year|date|release', re.I),
            string=self.YEAR_REGEX
        )
        if year_tag:
            match = self.YEAR_REGEX.search(year_tag.get_text())
            if match:
                return match.group(1)

        return ""

    # =========================================================
    # RATING
    # =========================================================

    def _extract_rating(self, soup: BeautifulSoup, json_ld: Dict) -> str:
        """Extract rating: JSON-LD → class-based."""
        # 1. JSON-LD aggregateRating
        if json_ld.get('aggregateRating'):
            ar = json_ld['aggregateRating']
            if isinstance(ar, dict):
                rating = ar.get('ratingValue')
                if rating:
                    return str(rating)

        # 2. JSON-LD ratingValue
        if json_ld.get('ratingValue'):
            return str(json_ld['ratingValue'])

        # 3. Class-based (rating/imdb/score)
        rating_tag = soup.find(['span', 'div'], class_=re.compile(r'rating|imdb|score', re.I))
        if rating_tag:
            match = self.RATING_REGEX.search(rating_tag.get_text())
            if match:
                return match.group(1)

        return "N/A"

    # =========================================================
    # VIDEO URL
    # =========================================================

    def _extract_video_url(self, soup: BeautifulSoup, base_url: str) -> str:
        """Extract video URL from iframe or video tag (skip ad iframes)."""
        # 1. video tag
        video = soup.find('video')
        if video:
            src = video.get('src')
            if src:
                return urljoin(base_url, src.strip())
            source = video.find('source')
            if source and source.get('src'):
                return urljoin(base_url, source['src'].strip())

        # 2. iframe (skip ads)
        for iframe in soup.find_all('iframe', src=True):
            src = iframe['src'].strip()
            if any(k in src.lower() for k in self.AD_KEYWORDS):
                continue
            # Video related
            if any(k in src.lower() for k in ['video', 'embed', 'player', 'stream', 'watch']):
                return urljoin(base_url, src)

        # 3. Any non-ad iframe
        for iframe in soup.find_all('iframe', src=True):
            src = iframe['src'].strip()
            if not any(k in src.lower() for k in self.AD_KEYWORDS):
                return urljoin(base_url, src)

        return ""

    # =========================================================
    # CAST & CATEGORY
    # =========================================================

    def _extract_cast(self, soup: BeautifulSoup) -> str:
        """Extract cast names."""
        try:
            for pattern in ['cast', 'actor', 'star']:
                div = soup.find(['div', 'span', 'p'], class_=re.compile(pattern, re.I))
                if div:
                    text = div.get_text(strip=True)
                    if text and len(text) < 300:
                        return text
        except Exception:
            pass
        return ""

    def _extract_category(self, soup: BeautifulSoup) -> str:
        """Extract category/genre."""
        try:
            for pattern in ['genre', 'category', 'tag']:
                div = soup.find(['div', 'span', 'a'], class_=re.compile(pattern, re.I))
                if div:
                    text = div.get_text(strip=True)
                    if text and len(text) < 100:
                        return text
        except Exception:
            pass
        return ""