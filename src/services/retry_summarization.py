"""Scheduled task for retrying failed LLM summarizations.

This service runs periodically to retry summarization for links where:
- Content extraction succeeded (status=COMPLETED)
- Summarization failed due to LLM unavailability
- Retry limit not exceeded
- Sufficient time elapsed since last retry
"""

from datetime import datetime, timedelta
from typing import List
from sqlalchemy import and_, or_
from src.utils.database import SessionLocal
from src.utils.logging import logger
from src.models.link import Link
from src.models import LinkStatus
from src.config import settings
from src.services.processor import extract_and_truncate_article


def get_links_needing_retry() -> List[Link]:
    """
    Query for links that need summarization retry.
    
    Returns links where:
    - Link processing completed (content extracted)
    - No summary exists yet
    - Summary error indicates LLM failure (not content failure)
    - Retry count below limit
    - Enough time passed since last retry
    """
    db = SessionLocal()
    try:
        now = datetime.now()
        
        # Calculate minimum time between retries based on retry count
        # Progressive backoff: 15min, 30min, 1hr, 2hr, 4hr
        retry_intervals = [
            timedelta(minutes=15),   # First retry after 15 min
            timedelta(minutes=30),   # Second retry after 30 min
            timedelta(hours=1),      # Third retry after 1 hour
            timedelta(hours=2),      # Fourth retry after 2 hours
            timedelta(hours=4),      # Fifth+ retry after 4 hours
        ]
        
        # Build query conditions for each retry level
        conditions = []
        
        for retry_count in range(settings.llm_max_retries):
            interval = retry_intervals[min(retry_count, len(retry_intervals) - 1)]
            retry_time_threshold = now - interval
            
            conditions.append(
                and_(
                    Link.summary_retry_count == retry_count,
                    or_(
                        Link.summary_last_retry_at.is_(None),
                        Link.summary_last_retry_at <= retry_time_threshold
                    )
                )
            )
        
        # Main query
        links = db.query(Link).filter(
            Link.status == LinkStatus.COMPLETED,  # Content extraction succeeded
            Link.summary.is_(None),  # No summary yet
            Link.summary_error.isnot(None),  # Previous attempt failed
            # Only retry LLM failures, not content extraction failures
            or_(
                Link.summary_error.contains("unavailable"),
                Link.summary_error.contains("timeout"),
                Link.summary_error.contains("Timeout"),
                Link.summary_error.contains("service")
            ),
            Link.summary_retry_count < settings.llm_max_retries,  # Haven't exceeded retries
            or_(*conditions)  # Time-based retry conditions
        ).limit(50).all()  # Process max 50 per run
        
        return links
    finally:
        db.close()


def retry_summarizations() -> None:
    """
    Main retry task - attempt summarization for eligible links.
    
    This function:
    1. Queries for links needing retry
    2. Attempts summarization for each
    3. Updates retry counts and timestamps
    4. Logs results
    """
    if not settings.llm_enabled:
        logger.debug("LLM disabled, skipping summarization retry task")
        return
    
    links = get_links_needing_retry()
    
    if not links:
        logger.debug("No links need summarization retry")
        return
    
    logger.info(f"Found {len(links)} link(s) needing summarization retry")
    
    from src.services.llm import get_llm_service
    llm_service = get_llm_service()
    
    success_count = 0
    failed_count = 0
    
    db = SessionLocal()
    try:
        for link in links:
            logger.info(f"Retrying summarization for link {link.id} (attempt {link.summary_retry_count + 1}/{settings.llm_max_retries})")
            
            try:
                # Re-extract content (it might have changed)
                content, extractable, extract_error = extract_and_truncate_article(link.url)
                
                if not extractable or not content:
                    # Content extraction now fails - mark permanently
                    link.summary_error = extract_error or "Article content unavailable"
                    db.commit()
                    logger.warning(f"Link {link.id} content extraction now fails: {extract_error}")
                    failed_count += 1
                    continue
                
                # Attempt summarization
                success, summary, error = llm_service.summarize(content, link.title, link.url)
                
                if success and summary:
                    # Success!
                    link.summary = summary
                    link.summarized_at = datetime.now()
                    link.llm_model = settings.llm_model_name
                    link.summary_error = None
                    link.summary_last_retry_at = datetime.now()
                    db.commit()
                    logger.info(f"Link {link.id} summarized successfully on retry")
                    success_count += 1
                else:
                    # Still failing
                    link.summary_retry_count += 1
                    link.summary_last_retry_at = datetime.now()
                    
                    if link.summary_retry_count >= settings.llm_max_retries:
                        link.summary_error = f"Failed after {settings.llm_max_retries} retries: {error}"
                        logger.error(f"Link {link.id} summarization failed permanently after {settings.llm_max_retries} retries")
                    else:
                        link.summary_error = (error or "Summarization failed")[:500]
                        logger.warning(f"Link {link.id} summarization still failing (retry {link.summary_retry_count}/{settings.llm_max_retries}): {error}")
                    
                    db.commit()
                    failed_count += 1
                    
            except Exception as e:
                logger.error(f"Error retrying link {link.id}: {str(e)}", exc_info=True)
                link.summary_retry_count += 1
                link.summary_last_retry_at = datetime.now()
                link.summary_error = f"Retry error: {str(e)[:450]}"
                db.commit()
                failed_count += 1
        
        logger.info(f"Summarization retry task completed: {success_count} succeeded, {failed_count} failed")
        
    finally:
        db.close()
