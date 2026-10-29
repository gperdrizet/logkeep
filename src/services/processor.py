"""Content extraction and link processing service."""
from datetime import datetime
from typing import Optional, Tuple
import trafilatura
from bs4 import BeautifulSoup

# import requests
from curl_cffi import requests
from sqlalchemy.orm import Session
from src.config import settings
from src.models.link import Link
from src.models import LinkStatus
from src.utils.logging import logger


def fetch_page_html(url: str, timeout: int = None):
    """
    Fetch raw HTML for a URL, impersonating a real browser to get past bot
    detection (Cloudflare / Akamai / Incapsula style 403/402 blocks).

    Browsers' TLS fingerprint and HTTP/2 settings (not just the User-Agent
    string) are what many news sites gate on. ``curl_cffi`` with
    ``impersonate="chrome"`` reproduces those fingerprints, which a plain
    ``requests`` call or ``trafilatura``'s built-in downloader will not.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds (uses config default if None)

    Returns:
        Raw HTML body (bytes) on success, or None if the fetch failed.
    """
    if timeout is None:
        timeout = settings.request_timeout

    try:
        response = requests.get(url, timeout=timeout, impersonate="chrome")
        response.raise_for_status()
        return response.content
    except requests.exceptions.Timeout:
        logger.error(f"Timeout fetching page: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error fetching {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching {url}: {str(e)}")
        return None


def extract_title_from_url(url: str, timeout: int = None) -> Optional[str]:
    """
    Extract title from URL using trafilatura with BeautifulSoup fallback.

    Args:
        url: URL to extract title from
        timeout: Request timeout in seconds (uses config default if None)

    Returns:
        Extracted title or None if extraction fails
    """
    try:
        # Fetch the HTML with browser impersonation (see fetch_page_html)
        html_content = fetch_page_html(url)
        if not html_content:
            # fetch_page_html already logged the failure
            logger.warning(f"No HTML available for URL: {url}, cannot extract title")
            return None

        # Try trafilatura first
        logger.info(f'Trying trafilatura for URL: {url}')

        downloaded = trafilatura.extract(
            html_content,
            with_metadata=True,
            favor_recall="medium",
            no_fallback=False,
            include_comments=False,
            include_tables=False,
            include_images=False,
            deduplicate=False
        )

        if downloaded:
            metadata = trafilatura.extract_metadata(downloaded)
            if metadata and metadata.title:
                logger.info(f"Title extracted via trafilatura: {metadata.title}")
                return metadata.title.strip()
        
        # Fallback to BeautifulSoup
        logger.info(f'Trying BeautifulSoup fallback for URL: {url}')
        # response = requests.get(url, timeout=timeout, headers=headers)
        # response.raise_for_status()
        
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Try various title extraction methods
        title = None
        
        # 1. OpenGraph title
        og_title = soup.find('meta', property='og:title')
        if og_title and og_title.get('content'):
            title = og_title['content']
        
        # 2. Twitter title
        if not title:
            twitter_title = soup.find('meta', attrs={'name': 'twitter:title'})
            if twitter_title and twitter_title.get('content'):
                title = twitter_title['content']
        
        # 3. HTML title tag
        if not title:
            title_tag = soup.find('title')
            if title_tag and title_tag.string:
                title = title_tag.string
        
        # 4. First h1 tag
        if not title:
            h1 = soup.find('h1')
            if h1:
                title = h1.get_text()
        
        if title:
            title = title.strip()
            logger.info(f"Title extracted via BeautifulSoup: {title}")
            return title
        
        logger.warning(f"No title found for URL: {url}")
        return None
        
    except requests.exceptions.Timeout:
        logger.error(f"Timeout extracting title from: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error extracting title from {url}: {str(e)}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error extracting title from {url}: {str(e)}")
        return None


def is_summarizable_url(url: str) -> Tuple[bool, Optional[str]]:
    """
    Check if a URL points to content that can be summarized.
    
    Args:
        url: URL to check
        
    Returns:
        Tuple of (is_summarizable: bool, error_reason: Optional[str])
    """
    url_lower = url.lower()
    
    # Check for PDF documents
    if url_lower.endswith('.pdf'):
        return False, "PDF documents cannot be summarized"
    
    return True, None


def extract_and_truncate_article(url: str) -> Tuple[Optional[str], bool, Optional[str]]:
    """
    Extract full article content from URL and truncate to token limit.
    
    Args:
        url: URL to extract content from
        
    Returns:
        Tuple of (content: Optional[str], is_summarizable: bool, error_reason: Optional[str])
    """
    try:
        # Fetch the page with browser impersonation. Using curl_cffi here
        # (instead of trafilatura.fetch_url) is what lets us get past the
        # 403/402 bot-detection blocks on major news sites — trafilatura's
        # internal downloader does not mimic a real browser's TLS/HTTP2
        # fingerprint and gets rejected.
        downloaded = fetch_page_html(url)
        if not downloaded:
            logger.warning(f"Failed to fetch URL: {url}")
            return None, False, "Article content unavailable"

        # Extract full article content
        content = trafilatura.extract(
            downloaded,
            include_comments=False,
            include_tables=True,
            no_fallback=False
        )
        
        if not content or len(content.strip()) < 200:
            logger.warning(f"Insufficient content extracted from {url} ({len(content) if content else 0} chars)")
            return None, False, "Article content unavailable"
        
        # Truncate to token limit using word-based estimation
        words = content.split()
        estimated_tokens = len(words) / 0.75  # Rough approximation: 1 token ≈ 0.75 words
        
        if estimated_tokens > settings.llm_max_input_tokens:
            max_words = int(settings.llm_max_input_tokens * 0.75)
            content = ' '.join(words[:max_words])
            logger.info(f"Truncated article from {len(words)} to {max_words} words (est. {settings.llm_max_input_tokens} tokens)")
        
        logger.info(f"Extracted {len(content)} chars from {url}")
        return content, True, None
        
    except Exception as e:
        logger.error(f"Error extracting content from {url}: {str(e)}")
        return None, False, "Article content unavailable"


def validate_url(url: str) -> bool:
    """
    Validate URL format.
    
    Args:
        url: URL to validate
        
    Returns:
        True if valid, False otherwise
    """
    if not url:
        return False
    
    url = url.strip()
    
    # Basic validation
    if not url.startswith(('http://', 'https://')):
        return False
    
    if len(url) < 10:
        return False
    
    return True


def check_duplicate_url(db: Session, user_id: int, url: str) -> bool:
    """
    Check if URL already exists for user.
    
    Args:
        db: Database session
        user_id: User ID
        url: URL to check
        
    Returns:
        True if duplicate, False otherwise
    """
    existing = db.query(Link).filter(
        Link.user_id == user_id,
        Link.url == url
    ).first()
    
    return existing is not None


def process_link(link_id: int) -> None:
    """
    Process a link: extract title and update status.
    
    This function is called by background tasks to process submitted links.
    It updates the link status in the database based on extraction results.
    
    Args:
        link_id: Link ID to process
    """
    from src.utils.database import SessionLocal
    
    db = SessionLocal()
    try:
        # Get link
        link = db.query(Link).filter(Link.id == link_id).first()
        if not link:
            logger.error(f"Link {link_id} not found")
            return
        
        # Update status to processing
        link.status = LinkStatus.PROCESSING
        db.commit()
        
        logger.info(f"Processing link {link_id}: {link.url}")
        
        # Extract title if not provided
        if not link.title:
            title = extract_title_from_url(link.url)
            
            if title:
                link.title = title[:500]  # Truncate to max length
                logger.info(f"Title extracted for link {link_id}: {title}")
            else:
                # Title extraction failed - mark as needs_title
                link.status = LinkStatus.NEEDS_TITLE
                link.error_message = "Could not extract title automatically. Please provide title manually."
                db.commit()
                logger.warning(f"Link {link_id} needs manual title")
                return
        
        # Title is available (either extracted or provided), proceed to GitHub commit if enabled
        if link.user.github_enabled:
            from src.services.github import commit_link_to_github
            
            success, error = commit_link_to_github(link, db)
            
            if success:
                link.status = LinkStatus.COMPLETED
                link.processed_at = datetime.now()
                link.error_message = None
                db.commit()
                logger.info(f"Link {link_id} committed to GitHub successfully")
            else:
                # GitHub commit failed - retry logic
                link.retry_count += 1
                
                if link.retry_count < settings.max_retries:
                    link.status = LinkStatus.PENDING
                    link.error_message = f"Retry {link.retry_count}/{settings.max_retries}: {error}"
                    logger.warning(f"Link {link_id} failed, will retry ({link.retry_count}/{settings.max_retries}): {error}")
                else:
                    link.status = LinkStatus.FAILED
                    link.error_message = f"Failed after {settings.max_retries} retries: {error}"
                    logger.error(f"Link {link_id} failed permanently: {error}")
                
                db.commit()
        else:
            # GitHub not enabled - mark as completed without commit
            link.status = LinkStatus.COMPLETED
            link.processed_at = datetime.now()
            link.error_message = None
            db.commit()
            logger.info(f"Link {link_id} processed successfully (GitHub disabled)")
        
        # Summarization is handled entirely by the scheduled task
        # (services/retry_summarization.py), which makes the FIRST attempt within
        # ~1 minute of completion and owns every subsequent retry. While a link is
        # waiting it is COMPLETED with summary=None, which the dashboard renders as
        # a calm "Summarizing..." state (no reload, no flicker). There is no inline
        # LLM call here, so there is exactly one code path that talks to the LLM.
        #
        # Exception: non-summarizable types (e.g. PDFs) can never produce a summary.
        # We mark them terminal NOW (retry count at the cap) so they are not left
        # "pending" forever; the retry task already skips any link whose retry count
        # has reached the cap, so this is consistent with the derived lifecycle.
        if (
            link.status == LinkStatus.COMPLETED
            and settings.llm_enabled
            and settings.summarize_on_submit
        ):
            is_summarizable, skip_reason = is_summarizable_url(link.url)
            if not is_summarizable:
                link.summary_error = skip_reason
                link.summary_retry_count = settings.llm_max_retries
                db.commit()
                logger.info(f"Link {link_id} skipped summarization (terminal): {skip_reason}")
        
    except Exception as e:
        logger.error(f"Unexpected error processing link {link_id}: {str(e)}", exc_info=True)
        
        # Update link status
        try:
            link = db.query(Link).filter(Link.id == link_id).first()
            if link:
                link.retry_count += 1
                if link.retry_count < settings.max_retries:
                    link.status = LinkStatus.PENDING
                else:
                    link.status = LinkStatus.FAILED
                link.error_message = f"Processing error: {str(e)}"
                db.commit()
        except Exception as update_error:
            logger.error(f"Failed to update link status after error: {str(update_error)}")
    finally:
        db.close()
