"""Content extraction and link processing service."""
from datetime import datetime
from typing import Optional, Tuple
import trafilatura
from bs4 import BeautifulSoup
import requests
from sqlalchemy.orm import Session
from src.config import settings
from src.models.link import Link
from src.models import LinkStatus
from src.utils.logging import logger


def extract_title_from_url(url: str, timeout: int = None) -> Optional[str]:
    """
    Extract title from URL using trafilatura with BeautifulSoup fallback.
    
    Args:
        url: URL to extract title from
        timeout: Request timeout in seconds (uses config default if None)
        
    Returns:
        Extracted title or None if extraction fails
    """
    if timeout is None:
        timeout = settings.request_timeout
    
    try:
        # Try trafilatura first
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            metadata = trafilatura.extract_metadata(downloaded)
            if metadata and metadata.title:
                logger.info(f"Title extracted via trafilatura: {metadata.title}")
                return metadata.title.strip()
        
        # Fallback to BeautifulSoup
        response = requests.get(url, timeout=timeout, headers={
            'User-Agent': 'Mozilla/5.0 (compatible; LogKeep/1.0; +https://github.com/gperdrizet/logkeep)'
        })
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'lxml')
        
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
        
    except requests.Timeout:
        logger.error(f"Timeout extracting title from: {url}")
        return None
    except requests.RequestException as e:
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
        # Fetch the page
        downloaded = trafilatura.fetch_url(url)
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
        
        # Only proceed with summarization if link processing succeeded
        if link.status == LinkStatus.COMPLETED:
            # Attempt summarization if enabled
            # NOTE: This is sequential processing. For concurrent processing:
            # 1. Remove time.sleep delays below
            # 2. Add asyncio.Semaphore for GPU access control
            # 3. Use async/await pattern
            # 4. Increase ThreadPoolExecutor max_workers
            if settings.llm_enabled and settings.summarize_on_submit:
                logger.info(f"Attempting to summarize link {link_id}")
                
                # Check if URL is summarizable
                is_summarizable, skip_reason = is_summarizable_url(link.url)
                if not is_summarizable:
                    link.summary_error = skip_reason
                    db.commit()
                    logger.info(f"Link {link_id} skipped summarization: {skip_reason}")
                else:
                    # Extract article content
                    content, extractable, extract_error = extract_and_truncate_article(link.url)
                    
                    if not extractable or not content:
                        link.summary_error = extract_error or "Article content unavailable"
                        db.commit()
                        logger.warning(f"Link {link_id} content extraction failed: {extract_error}")
                    else:
                        # Try to generate summary with retry logic
                        from src.services.llm import get_llm_service
                        import time
                        
                        llm_service = get_llm_service()
                        
                        for attempt in range(settings.llm_max_retries):
                            success_summary, summary, error_summary = llm_service.summarize(
                                content, link.title, link.url
                            )
                            
                            if success_summary and summary:
                                # Summary generated successfully
                                link.summary = summary
                                link.summarized_at = datetime.now()
                                link.llm_model = settings.llm_model_name
                                link.summary_error = None
                                db.commit()
                                logger.info(f"Link {link_id} summarized successfully")
                                break
                            else:
                                # Summarization failed
                                link.summary_retry_count += 1
                                db.commit()
                                
                                if attempt < settings.llm_max_retries - 1:
                                    # Wait before retry with exponential backoff
                                    delay = settings.llm_retry_delays[attempt]
                                    logger.warning(f"Link {link_id} summarization failed (attempt {attempt + 1}/{settings.llm_max_retries}), retrying in {delay}s: {error_summary}")
                                    time.sleep(delay)
                                else:
                                    # Final failure
                                    link.summary_error = (error_summary or "Summarization failed")[:500]
                                    db.commit()
                                    logger.error(f"Link {link_id} summarization failed after {settings.llm_max_retries} attempts: {error_summary}")
                logger.error(f"Link {link_id} failed permanently: {error}")
            
            db.commit()
        
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
