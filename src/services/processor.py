"""Content extraction and link processing service."""
from datetime import datetime
from typing import Optional, Tuple
import trafilatura
from bs4 import BeautifulSoup
import requests
from sqlalchemy.orm import Session
from src.models.link import Link
from src.models import LinkStatus
from src.utils.logging import logger


def extract_title_from_url(url: str, timeout: int = 10) -> Optional[str]:
    """
    Extract title from URL using trafilatura with BeautifulSoup fallback.
    
    Args:
        url: URL to extract title from
        timeout: Request timeout in seconds
        
    Returns:
        Extracted title or None if extraction fails
    """
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
        
        # Title is available (either extracted or provided), proceed to GitHub commit
        # This will be called from the GitHub service
        from src.services.github import commit_link_to_github
        
        success, error = commit_link_to_github(link, db)
        
        if success:
            link.status = LinkStatus.COMPLETED
            link.processed_at = datetime.now()
            link.error_message = None
            db.commit()
            logger.info(f"Link {link_id} processed successfully")
        else:
            # GitHub commit failed - retry logic
            link.retry_count += 1
            max_retries = 3
            
            if link.retry_count < max_retries:
                link.status = LinkStatus.PENDING
                link.error_message = f"Retry {link.retry_count}/{max_retries}: {error}"
                logger.warning(f"Link {link_id} failed, will retry ({link.retry_count}/{max_retries}): {error}")
            else:
                link.status = LinkStatus.FAILED
                link.error_message = f"Failed after {max_retries} retries: {error}"
                logger.error(f"Link {link_id} failed permanently: {error}")
            
            db.commit()
        
    except Exception as e:
        logger.error(f"Unexpected error processing link {link_id}: {str(e)}", exc_info=True)
        
        # Update link status
        try:
            link = db.query(Link).filter(Link.id == link_id).first()
            if link:
                link.retry_count += 1
                if link.retry_count < 3:
                    link.status = LinkStatus.PENDING
                else:
                    link.status = LinkStatus.FAILED
                link.error_message = f"Processing error: {str(e)}"
                db.commit()
        except:
            pass
    finally:
        db.close()
