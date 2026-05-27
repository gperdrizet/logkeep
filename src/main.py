"""Main FastAPI application."""
import json
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.config import settings
from src.metrics import REQUEST_COUNT, REQUEST_DURATION, LINK_SUBMISSIONS, ACTIVE_USERS, PROCESSING_ERRORS, DB_CONNECTIONS
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
from src.utils.auth import get_current_user, get_current_user_optional, get_current_admin_user, verify_password, create_access_token, get_password_hash
from src.utils.encryption import encrypt_token
from src.utils.logging import logger
from src.services.processor import process_link
from src.services.retry_summarization import retry_summarizations

load_dotenv()

# Create scheduler for background tasks
scheduler = AsyncIOScheduler()

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

# Middleware for metrics
@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    """Middleware to track request metrics."""
    # Skip metrics endpoint itself
    if request.url.path == "/metrics":
        return await call_next(request)
    
    import time
    start_time = time.time()
    
    response = await call_next(request)
    
    duration = time.time() - start_time
    
    # Record metrics
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code
    ).inc()
    
    REQUEST_DURATION.labels(
        method=request.method,
        endpoint=request.url.path
    ).observe(duration)
    
    return response

# Include API routers
app.include_router(auth.router)
app.include_router(links.router)
app.include_router(tags.router)
app.include_router(health.router)


# Metrics endpoint
@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint."""
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


# Startup event - recover stale processing tasks
@app.on_event("startup")
async def startup_event():
    """Application startup tasks."""
    logger.info("Starting LogKeep application...")
    
        # Reset stale processing tasks
    db = SessionLocal()
    try:
        link_service = LinkService(db)
        
        # Initialize active users metric to 0 (will increment on login)
        ACTIVE_USERS.set(0)
        logger.info("Active users metric initialized to 0")
        
        # Find links that have been processing for more than configured timeout
        stale_threshold = datetime.now() - timedelta(minutes=settings.processing_timeout_minutes)
        
        stale_links = link_service.get_stale_processing_links(stale_threshold, settings.max_retries)
        
        if stale_links:
            for link in stale_links:
                link.status = LinkStatus.PENDING
                logger.info(f"Reset stale link {link.id} to pending")
            
            db.commit()
            logger.info(f"Reset {len(stale_links)} stale processing task(s)")
        
        # Check LLM service availability if enabled
        if settings.llm_enabled:
            import httpx
            try:
                headers = {}
                if settings.llm_api_key:
                    headers["Authorization"] = f"Bearer {settings.llm_api_key}"

                base_url = settings.llm_base_url.rstrip("/")
                models_url = f"{base_url}/models" if base_url.endswith("/v1") else f"{base_url}/v1/models"
                response = httpx.get(models_url, headers=headers, timeout=10)
                response.raise_for_status()
                logger.info("LLM service ready")
            except Exception as e:
                logger.warning(f"LLM service unavailable, summarization disabled: {e}")
        
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
    
    # Start scheduled tasks
    if settings.llm_enabled:
        # Schedule summarization retry task to run every 20 minutes
        scheduler.add_job(
            retry_summarizations,
            trigger=IntervalTrigger(minutes=20),
            id='retry_summarizations',
            name='Retry failed summarizations',
            replace_existing=True
        )
        logger.info("Scheduled summarization retry task (every 20 minutes)")
    
    scheduler.start()
    logger.info("LogKeep application started successfully")


@app.on_event("shutdown")
async def shutdown_event():
    """Application shutdown tasks."""
    scheduler.shutdown()
    logger.info("Scheduler shut down")


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
    """Home page - redirect to submit if authenticated, otherwise login."""
    if current_user:
        return RedirectResponse(url="/submit", status_code=status.HTTP_302_FOUND)
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
        
        # Redirect to submit page with cookie
        response = RedirectResponse(url="/submit", status_code=status.HTTP_302_FOUND)
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
    github_enabled: str | None = Form(None),
    github_token: str | None = Form(None),
    repo_owner: str | None = Form(None),
    repo_name: str | None = Form(None),
    db: Session = Depends(get_db)
):
    """Handle registration form submission."""
    from src.exceptions import ValidationError, DuplicateError, NotFoundError
    
    try:
        # Check if GitHub is enabled
        is_github_enabled = github_enabled == "true"
        
        # Validate GitHub fields if enabled
        if is_github_enabled:
            if not github_token or not repo_owner or not repo_name:
                return templates.TemplateResponse(
                    "register.html",
                    {"request": request, "error": "GitHub token, repository owner, and repository name are required when GitHub integration is enabled"},
                    status_code=400
                )
            encrypted_token = encrypt_token(github_token)
        else:
            encrypted_token = None
            repo_owner = None
            repo_name = None
        
        # Create user using service
        user_service = UserService(db)
        user = user_service.register_user(
            username=username,
            password=password,
            invite_code=invite_code,
            github_enabled=is_github_enabled,
            repo_owner=repo_owner,
            repo_name=repo_name,
            github_token=encrypted_token
        )
        
        logger.info(f"New user registered: {username} (GitHub enabled: {is_github_enabled})")
        
        # Import tags from existing journals in background (only if GitHub enabled)
        if is_github_enabled:
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
    all_links = db.query(Link).filter(
        Link.user_id == current_user.id
    ).order_by(Link.submitted_at.desc()).limit(50).all()
    
    # Apply tag filter if specified
    filter_tag_list = []
    if filter_tags:
        filter_tag_list = [tag.strip() for tag in filter_tags.split(',') if tag.strip()]
        # Filter links that have ALL the specified tags
        links = []
        for link in all_links:
            link_tag_names = [tag.name for tag in link.tags]
            if all(filter_tag in link_tag_names for filter_tag in filter_tag_list):
                links.append(link)
    else:
        links = all_links
    
    # Add tag_names attribute and check for pending summaries
    any_pending_summaries = False
    for link in links:
        link.tag_names = [tag.name for tag in link.tags]
        # Check if link has pending summary (completed but no summary/error yet)
        link.has_pending_summary = (
            link.status == LinkStatus.COMPLETED and 
            link.summary is None and 
            link.summary_error is None
        )
        if link.has_pending_summary:
            any_pending_summaries = True
    
    # Get user tags as list of names
    user_tag_names = [tag.name for tag in current_user.tags] if current_user.tags else []
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "any_pending_summaries": any_pending_summaries,
            "user_tags": user_tag_names,
            "links": links,
            "filter_tag_list": filter_tag_list
        }
    )


@app.get("/data", response_class=HTMLResponse)
async def data_page(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Data visualization page."""
    links = db.query(Link).filter(
        Link.user_id == current_user.id
    ).order_by(Link.submitted_at.desc()).limit(50).all()
    
    # Calculate histogram data for scores
    score_bins = {i: 0 for i in range(11)}  # 0.0, 0.1, 0.2, ..., 1.0
    for link in links:
        if link.score is not None:
            bin_index = round(link.score * 10)
            score_bins[bin_index] += 1
    
    # Calculate tag usage from links
    tag_usage_count = {}
    for link in links:
        if link.tags:
            for tag in link.tags:
                tag_name = tag.name
                tag_usage_count[tag_name] = tag_usage_count.get(tag_name, 0) + 1
    
    # Bin tags by their count in links
    frequency_bins = {
        "1": 0,
        "2-3": 0,
        "4-6": 0,
        "7-9": 0,
        "10+": 0
    }
    
    for count in tag_usage_count.values():
        if count == 1:
            frequency_bins["1"] += 1
        elif 2 <= count <= 3:
            frequency_bins["2-3"] += 1
        elif 4 <= count <= 6:
            frequency_bins["4-6"] += 1
        elif 7 <= count <= 9:
            frequency_bins["7-9"] += 1
        else:
            frequency_bins["10+"] += 1
    
    # Prepare data for templates
    score_histogram = [{"bin": i/10, "count": score_bins[i]} for i in range(11)]
    max_score_count = max(score_bins.values()) if score_bins.values() and max(score_bins.values()) > 0 else 1
    
    tag_histogram = [{"bin": k, "count": v} for k, v in frequency_bins.items()]
    max_tag_count = max(frequency_bins.values()) if frequency_bins.values() and max(frequency_bins.values()) > 0 else 1
    
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


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(
    request: Request,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Admin dashboard for user and invite management."""
    users = db.query(User).order_by(User.created_at.desc()).all()
    invites = db.query(Invite).filter(
        Invite.used_by_user_id.is_(None)
    ).order_by(Invite.created_at.desc()).limit(30).all()

    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "user": current_user,
            "users": users,
            "invites": invites,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
        }
    )


@app.post("/admin/invites")
async def admin_create_invites(
    count: int = Form(1),
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Generate invite codes as admin."""
    if count < 1 or count > 100:
        return RedirectResponse(
            url="/admin?error=Invite+count+must+be+between+1+and+100",
            status_code=status.HTTP_302_FOUND
        )

    for _ in range(count):
        db.add(Invite(created_by_user_id=current_user.id))
    db.commit()

    return RedirectResponse(
        url=f"/admin?success=Generated+{count}+invite+code(s)",
        status_code=status.HTTP_302_FOUND
    )


@app.post("/admin/users")
async def admin_create_user(
    username: str = Form(...),
    password: str = Form(...),
    _: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Create a user as admin (without invite code)."""
    username = username.strip()

    if len(username) < 3:
        return RedirectResponse(
            url="/admin?error=Username+must+be+at+least+3+characters",
            status_code=status.HTTP_302_FOUND
        )

    if len(password) < 8:
        return RedirectResponse(
            url="/admin?error=Password+must+be+at+least+8+characters",
            status_code=status.HTTP_302_FOUND
        )

    existing = db.query(User).filter(User.username == username).first()
    if existing:
        return RedirectResponse(
            url="/admin?error=Username+already+exists",
            status_code=status.HTTP_302_FOUND
        )

    user = User(
        username=username,
        hashed_password=get_password_hash(password),
        github_enabled=False,
        is_active=True,
    )
    db.add(user)
    db.commit()

    return RedirectResponse(
        url=f"/admin?success=User+{username}+created",
        status_code=status.HTTP_302_FOUND
    )


@app.post("/admin/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    current_user: User = Depends(get_current_admin_user),
    db: Session = Depends(get_db)
):
    """Delete a user account as admin."""
    if user_id == current_user.id:
        return RedirectResponse(
            url="/admin?error=Cannot+delete+your+own+account",
            status_code=status.HTTP_302_FOUND
        )

    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(
            url="/admin?error=User+not+found",
            status_code=status.HTTP_302_FOUND
        )

    username = user.username
    db.delete(user)
    db.commit()

    return RedirectResponse(
        url=f"/admin?success=User+{username}+deleted",
        status_code=status.HTTP_302_FOUND
    )


@app.post("/data/github-settings")
async def update_github_settings(
    request: Request,
    github_token: str | None = Form(None),
    repo_owner: str = Form(...),
    repo_name: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update GitHub integration settings for the current user."""
    if not repo_owner or not repo_name:
        return RedirectResponse("/data?github_error=Repository+owner+and+name+are+required", status_code=303)

    current_user.repo_owner = repo_owner
    current_user.repo_name = repo_name
    current_user.github_enabled = True

    if github_token and github_token.strip():
        current_user.encrypted_github_token = encrypt_token(github_token.strip())

    db.commit()
    return RedirectResponse("/data?github_ok=1", status_code=303)


@app.get("/submit", response_class=HTMLResponse)
async def submit_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Link submission page."""
    # Get user tags as list of names
    user_tags = [tag.name for tag in current_user.tags] if current_user.tags else []
    
    return templates.TemplateResponse(
        "submit.html",
        {
            "request": request,
            "user": current_user,
            "user_tags": sorted(user_tags)
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
        tag_names = json.loads(tags_json)
    except (json.JSONDecodeError, ValueError, TypeError):
        tag_names = []
    
    # Submit link using service
    try:
        tag_service = TagService(db)
        link_service = LinkService(db)
        
        # Get or create tag objects
        tag_objects = tag_service.get_or_create_tags(current_user.id, tag_names)
        
        link = link_service.submit_link(
            user_id=current_user.id,
            url=url,
            score=score or 0.5,
            tag_objects=tag_objects,
            manual_title=title if title else None
        )
        
        logger.info(f"Link submitted by {current_user.username}: {url} (ID: {link.id})")
        
        # Track successful submission
        LINK_SUBMISSIONS.labels(status='success').inc()
        
        # Process in background
        background_tasks.add_task(process_link, link.id)
        
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
        
    except DuplicateError:
        LINK_SUBMISSIONS.labels(status='duplicate').inc()
        return templates.TemplateResponse(
            "submit.html",
            {
                "request": request,
                "user": current_user,
                "user_tags": sorted([tag.name for tag in current_user.tags]),
                "error": "This URL has already been submitted. Check your dashboard."
            },
            status_code=409
        )
    except ValidationError as e:
        LINK_SUBMISSIONS.labels(status='failed').inc()
        return templates.TemplateResponse(
            "submit.html",
            {
                "request": request,
                "user": current_user,
                "user_tags": sorted([tag.name for tag in current_user.tags]),
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
            tag_names = json.loads(tags_json)
        except (json.JSONDecodeError, ValueError, TypeError):
            tag_names = []
        
        # Get or create Tag objects
        from src.models.tag import Tag
        tag_objects = []
        for tag_name in tag_names:
            tag_name = tag_name.strip().lower()
            if not tag_name:
                continue
            
            # Try to get existing tag
            existing_tag = db.query(Tag).filter(
                Tag.user_id == current_user.id,
                Tag.name == tag_name
            ).first()
            
            if existing_tag:
                tag_objects.append(existing_tag)
            else:
                # Create new tag
                new_tag = Tag(user_id=current_user.id, name=tag_name)
                db.add(new_tag)
                db.flush()  # Get the ID without committing
                tag_objects.append(new_tag)
                logger.info(f"Created new tag '{tag_name}' for user {current_user.username}")
        
        # Update link using service
        link = link_service.update_link(
            link_id=link_id,
            user_id=current_user.id,
            title=title.strip(),
            tag_objects=tag_objects,
            score=score
        )
        
        logger.info(f"Link {link_id} edited by {current_user.username}: title='{title}', tags={tag_names}, score={score}")
        
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


@app.post("/links/{link_id}/delete")
async def delete_link(
    link_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a link."""
    from src.services.github import delete_link_from_journal
    from src.exceptions import NotFoundError
    
    try:
        # Get link using service
        link_service = LinkService(db)
        link = link_service.get_link(link_id, current_user.id)
        
        # Delete from GitHub only if user has GitHub integration enabled
        if current_user.github_enabled and current_user.encrypted_github_token:
            success, error_msg = delete_link_from_journal(link, db)
            
            if not success:
                logger.error(f"Failed to delete link {link_id} from GitHub: {error_msg}")
                return RedirectResponse(
                    url=f"/dashboard?error=Failed to delete from GitHub: {error_msg}",
                    status_code=status.HTTP_302_FOUND
                )
        
        # Delete from database
        link_service.delete_link(link_id, current_user.id)
        
        logger.info(f"Link {link_id} deleted by {current_user.username}")
        
        return RedirectResponse(
            url="/dashboard?success=Link deleted successfully",
            status_code=status.HTTP_302_FOUND
        )
            
    except NotFoundError:
        return RedirectResponse(
            url="/dashboard?error=Link not found",
            status_code=status.HTTP_302_FOUND
        )
    except Exception as e:
        logger.error(f"Error deleting link {link_id}: {e}")
        return RedirectResponse(
            url=f"/dashboard?error=Failed to delete link: {str(e)}",
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
            "tags": sorted([tag.name for tag in current_user.tags]),
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
    from fastapi.responses import JSONResponse
    
    try:
        tag_service = TagService(db)
        tag_obj = tag_service.add_tag(current_user.id, tag)
        
        logger.info(f"Tag added by {current_user.username}: {tag}")
        
        # Check if this is an AJAX request
        if request.headers.get("accept") == "application/json" or request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse(content={"success": True, "tag": tag}, status_code=200)
        
        return RedirectResponse(url="/tags", status_code=status.HTTP_302_FOUND)
        
    except ValidationError as e:
        # Check if this is an AJAX request
        if request.headers.get("accept") == "application/json" or request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JSONResponse(content={"success": False, "error": str(e)}, status_code=400)
        
        # Refresh user to get current tags
        db.refresh(current_user)
        return templates.TemplateResponse(
            "tags.html",
            {
                "request": request,
                "user": current_user,
                "tags": sorted([tag.name for tag in current_user.tags]),
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
