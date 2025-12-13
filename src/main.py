"""Main FastAPI application."""
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from src.config import settings
from src.api import auth, links, tags, health
from src.services.analytics import AnalyticsService
from src.services.link_service import LinkService
from src.services.user_service import UserService
from src.services.tag_service import TagService
from src.models import LinkStatus
from src.models.user import User
from src.models.link import Link
from src.models.invite import Invite
from src.utils.database import get_db, SessionLocal
from src.utils.auth import get_current_user, get_current_user_optional, verify_password, create_access_token, get_password_hash
from src.utils.encryption import encrypt_token
from src.utils.logging import logger
from src.services.processor import process_link

load_dotenv()

# Create FastAPI app
app = FastAPI(
    title="LogKeep",
    description="Curate content from links using Logseq & GitHub",
    version="1.0.0"
)

# Mount static files
app.mount("/static", StaticFiles(directory="src/static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="src/templates")

# Add custom Jinja2 filter for cleaning URLs
def clean_url_display(url: str) -> str:
    """Remove common URL prefixes and trailing slashes for cleaner display."""
    prefixes = ['https://www.', 'http://www.', 'https://', 'http://']
    for prefix in prefixes:
        if url.startswith(prefix):
            url = url[len(prefix):]
            break
    return url.rstrip('/')

templates.env.filters['clean_url'] = clean_url_display

# Include API routers
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(tags.router)
app.include_router(health.router)


# Startup event - recover stale processing tasks
@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    logger.info("Starting LogKeep application...")
    
    # Reset stale processing tasks
    db = SessionLocal()
    try:
        link_service = LinkService(db)
        
        # Find links that have been processing for more than configured timeout
        stale_threshold = datetime.now() - timedelta(minutes=settings.processing_timeout_minutes)
        
        stale_links = link_service.get_stale_processing_links(stale_threshold, settings.max_retries)
        
        if stale_links:
            for link in stale_links:
                link.status = LinkStatus.PENDING
                logger.info(f"Reset stale link {link.id} to pending")
            
            db.commit()
            logger.info(f"Reset {len(stale_links)} stale processing task(s)")
        
        # Process any pending links
        pending_links = link_service.get_pending_links(settings.max_retries)
        
        if pending_links:
            logger.info(f"Found {len(pending_links)} pending link(s), queueing for processing")
            # We can't use BackgroundTasks during startup, so we'll process them directly
            # in a non-blocking way by importing the function
            import asyncio
            from concurrent.futures import ThreadPoolExecutor
            
            async def process_pending():
                with ThreadPoolExecutor(max_workers=3) as executor:
                    loop = asyncio.get_event_loop()
                    tasks = [
                        loop.run_in_executor(executor, process_link, link.id)
                        for link in pending_links
                    ]
                    await asyncio.gather(*tasks)
            
            # Schedule for processing
            asyncio.create_task(process_pending())
            logger.info(f"Scheduled {len(pending_links)} pending link(s) for background processing")
            
    except Exception as e:
        logger.error(f"Error during startup recovery: {str(e)}")
        db.rollback()
    finally:
        db.close()
    
    logger.info("LogKeep application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    logger.info("Shutting down LogKeep application...")


# Web routes

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    current_user: Optional[User] = Depends(get_current_user_optional)
):
    """Home page - redirect to dashboard if authenticated, otherwise login."""
    if current_user:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    """Login page."""
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle login form submission."""
    from src.exceptions import AuthenticationError
    
    try:
        user_service = UserService(db)
        user = user_service.authenticate_user(username, password)
        
        if not user.is_active:
            return templates.TemplateResponse(
                "login.html",
                {"request": request, "error": "Account is deactivated"},
                status_code=403
            )
        
        # Create session token
        access_token = create_access_token(data={"sub": str(user.id)})
        
        # Redirect to dashboard with cookie
        response = RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        response.set_cookie(
            key="session",
            value=access_token,
            httponly=True,
            max_age=settings.access_token_expire_minutes * 60,
            samesite="lax",
            secure=settings.is_production
        )
        
        logger.info(f"User logged in: {user.username}")
        return response
        
    except AuthenticationError:
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=400
        )


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    """Registration page."""
    return templates.TemplateResponse("register.html", {"request": request})


@app.post("/register")
async def register_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    invite_code: str = Form(...),
    github_token: str = Form(...),
    repo_owner: str = Form(...),
    repo_name: str = Form(...),
    db: Session = Depends(get_db)
):
    """Handle registration form submission."""
    from src.exceptions import ValidationError, DuplicateError, NotFoundError
    
    try:
        # Encrypt GitHub token
        encrypted_token = encrypt_token(github_token)
        
        # Create user using service
        user_service = UserService(db)
        user = user_service.register_user(
            username=username,
            password=password,
            invite_code=invite_code,
            repo_owner=repo_owner,
            repo_name=repo_name,
            github_token=encrypted_token
        )
        
        logger.info(f"New user registered: {username}")
        
        # Import tags from existing journals in background
        try:
            from src.services.github import import_tags_from_journals
            tag_count, tag_error = import_tags_from_journals(user, db)
            if tag_count > 0:
                logger.info(f"Auto-imported {tag_count} tags for new user {username}")
        except Exception as e:
            # Don't fail registration if tag import fails
            logger.warning(f"Failed to auto-import tags for {username}: {str(e)}")
        
        # Redirect to login
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
        
    except (ValidationError, DuplicateError, NotFoundError) as e:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": str(e)},
            status_code=400
        )
    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        db.rollback()
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Registration failed. Please try again."},
            status_code=500
        )


@app.post("/logout")
async def logout():
    """Logout and clear session."""
    response = RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)
    response.delete_cookie(key="session")
    return response


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    filter_tags: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User dashboard showing recent submissions."""
    # Get user links using service
    link_service = LinkService(db)
    all_links = link_service.get_user_links(current_user.id, limit=50)
    
    # Apply tag filter if specified
    filter_tag_list = []
    if filter_tags:
        filter_tag_list = [tag.strip() for tag in filter_tags.split(',') if tag.strip()]
        links = [link for link in all_links if all(tag in link.selected_tags for tag in filter_tag_list)]
    else:
        links = all_links
    
    # Calculate analytics using service
    analytics = AnalyticsService()
    score_histogram, max_score_count = analytics.calculate_score_histogram(links)
    tag_histogram, max_tag_count = analytics.calculate_tag_frequency_histogram(links)
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "links": links,
            "filter_tag_list": filter_tag_list,
            "score_histogram": score_histogram,
            "max_score_count": max_score_count,
            "tag_histogram": tag_histogram,
            "max_tag_count": max_tag_count
        }
    )


@app.get("/data", response_class=HTMLResponse)
async def data_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Data visualization page."""
    # Get user links using service
    link_service = LinkService(db)
    links = link_service.get_user_links(current_user.id, limit=50)
    
    # Calculate analytics using service
    analytics = AnalyticsService()
    score_histogram, max_score_count = analytics.calculate_score_histogram(links)
    
    # Use stored tag counts for tag histogram
    tag_counts = current_user.tag_counts if current_user.tag_counts else {}
    tag_histogram, max_tag_count = analytics.calculate_tag_collection_histogram(tag_counts)
    
    return templates.TemplateResponse(
        "data.html",
        {
            "request": request,
            "user": current_user,
            "score_histogram": score_histogram,
            "max_score_count": max_score_count,
            "tag_histogram": tag_histogram,
            "max_tag_count": max_tag_count
        }
    )


@app.get("/submit", response_class=HTMLResponse)
async def submit_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Link submission page."""
    return templates.TemplateResponse(
        "submit.html",
        {
            "request": request,
            "user": current_user,
            "user_tags": sorted(current_user.tags)
        }
    )


@app.post("/submit")
async def submit_link(
    request: Request,
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    title: Optional[str] = Form(None),
    tags_json: str = Form("[]"),
    score: Optional[float] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Handle link submission."""
    import json
    from src.services.processor import validate_url
    from src.exceptions import ValidationError, DuplicateError
    
    # Validate URL
    if not validate_url(url):
        return templates.TemplateResponse(
            "submit.html",
            {
                "request": request,
                "user": current_user,
                "user_tags": sorted(current_user.tags),
                "error": "Invalid URL format"
            },
            status_code=400
        )
    
    # Parse tags
    try:
        selected_tags = json.loads(tags_json)
    except (json.JSONDecodeError, ValueError, TypeError):
        selected_tags = []
    
    # Submit link using service
    try:
        link_service = LinkService(db)
        link = link_service.submit_link(
            user_id=current_user.id,
            url=url,
            score=score or 0.5,
            tags=selected_tags,
            manual_title=title if title else None
        )
        
        logger.info(f"Link submitted by {current_user.username}: {url} (ID: {link.id})")
        
        # Process in background
        background_tasks.add_task(process_link, link.id)
        
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        
    except DuplicateError:
        return templates.TemplateResponse(
            "submit.html",
            {
                "request": request,
                "user": current_user,
                "user_tags": sorted(current_user.tags),
                "error": "This URL has already been submitted. Check your dashboard."
            },
            status_code=409
        )
    except ValidationError as e:
        return templates.TemplateResponse(
            "submit.html",
            {
                "request": request,
                "user": current_user,
                "user_tags": sorted(current_user.tags),
                "error": str(e)
            },
            status_code=400
        )


@app.post("/links/{link_id}/title")
async def update_link_title(
    link_id: int,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update title for a link that needs manual title."""
    from src.exceptions import NotFoundError
    
    try:
        link_service = LinkService(db)
        link = link_service.get_link(link_id, current_user.id)
        
        if link.status != LinkStatus.NEEDS_TITLE:
            raise HTTPException(status_code=400, detail="Link does not need title")
        
        # Update link
        link = link_service.update_link(
            link_id=link_id,
            user_id=current_user.id,
            title=title
        )
        
        # Reset status to pending for reprocessing
        link_service.update_link_status(
            link_id=link_id,
            user_id=current_user.id,
            status=LinkStatus.PENDING
        )
        
        logger.info(f"Title updated for link {link_id}: {title}")
        
        # Queue for processing in background
        background_tasks.add_task(process_link, link.id)
        
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        
    except NotFoundError:
        raise HTTPException(status_code=404, detail="Link not found")


@app.post("/links/{link_id}/edit")
async def edit_link(
    link_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    tags_json: str = Form("[]"),
    score: Optional[float] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Edit an existing link's title, tags, and score."""
    import json
    from src.services.github import update_link_in_journal
    from src.exceptions import NotFoundError, ValidationError
    
    try:
        # Get link using service
        link_service = LinkService(db)
        link = link_service.get_link(link_id, current_user.id)
        
        # Only allow editing completed links
        if link.status != LinkStatus.COMPLETED:
            return RedirectResponse(
                url="/dashboard?error=Only completed links can be edited",
                status_code=status.HTTP_302_FOUND
            )
        
        # Parse tags
        try:
            selected_tags = json.loads(tags_json)
        except (json.JSONDecodeError, ValueError, TypeError):
            selected_tags = []
        
        # Validate tags exist in user's collection
        invalid_tags = [tag for tag in selected_tags if tag not in current_user.tags]
        if invalid_tags:
            return RedirectResponse(
                url=f"/dashboard?error=Invalid tags: {', '.join(invalid_tags)}",
                status_code=status.HTTP_302_FOUND
            )
        
        # Update link using service
        link = link_service.update_link(
            link_id=link_id,
            user_id=current_user.id,
            title=title.strip(),
            tags=selected_tags,
            score=score
        )
        
        logger.info(f"Link {link_id} edited by {current_user.username}: title='{title}', tags={selected_tags}, score={score}")
        
        # Update in GitHub
        success, error_msg = update_link_in_journal(link, db)
        
        if success:
            return RedirectResponse(
                url="/dashboard?success=Link updated successfully",
                status_code=status.HTTP_302_FOUND
            )
        else:
            # Rollback would be complex here, so just log and inform user
            logger.error(f"Failed to update link {link_id} in GitHub: {error_msg}")
            return RedirectResponse(
                url=f"/dashboard?error=Link updated in database but failed to update in GitHub: {error_msg}",
                status_code=status.HTTP_302_FOUND
            )
            
    except NotFoundError:
        return RedirectResponse(
            url="/dashboard?error=Link not found",
            status_code=status.HTTP_302_FOUND
        )
    except ValidationError as e:
        return RedirectResponse(
            url=f"/dashboard?error={str(e)}",
            status_code=status.HTTP_302_FOUND
        )


@app.get("/tags", response_class=HTMLResponse)
async def tags_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Tag management page."""
    return templates.TemplateResponse(
        "tags.html",
        {
            "request": request,
            "user": current_user,
            "tags": sorted(current_user.tags),
            "max_tags": settings.max_tags_per_user
        }
    )


@app.post("/tags/add")
async def add_tag(
    request: Request,
    tag: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Add a new tag."""
    from src.exceptions import ValidationError
    
    try:
        tag_service = TagService(db)
        updated_tags = tag_service.add_tag(current_user.id, tag)
        
        logger.info(f"Tag added by {current_user.username}: {tag}")
        
        return RedirectResponse(url="/tags", status_code=status.HTTP_302_FOUND)
        
    except ValidationError as e:
        # Refresh user to get current tags
        db.refresh(current_user)
        return templates.TemplateResponse(
            "tags.html",
            {
                "request": request,
                "user": current_user,
                "tags": sorted(current_user.tags),
                "max_tags": settings.max_tags_per_user,
                "error": str(e)
            },
            status_code=400
        )


@app.post("/tags/delete/{tag}")
async def delete_tag(
    tag: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a tag."""
    from src.exceptions import ValidationError
    
    try:
        tag_service = TagService(db)
        tag_service.delete_tag(current_user.id, tag.lower())
        logger.info(f"Tag deleted by {current_user.username}: {tag}")
    except ValidationError:
        # Tag not found, but we can silently ignore
        pass
    
    return RedirectResponse(url="/tags", status_code=status.HTTP_302_FOUND)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
