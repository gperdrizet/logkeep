"""Main FastAPI application."""
import os
from datetime import datetime, timedelta
from typing import Optional
from fastapi import FastAPI, Request, Depends, Form, HTTPException, status, BackgroundTasks
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from dotenv import load_dotenv

from src.api import auth, links, tags, health
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
        # Find links that have been processing for more than 5 minutes
        stale_threshold = datetime.now() - timedelta(minutes=5)
        
        stale_links = db.query(Link).filter(
            Link.status == LinkStatus.PROCESSING,
            Link.submitted_at < stale_threshold,
            Link.retry_count < 3
        ).all()
        
        if stale_links:
            for link in stale_links:
                link.status = LinkStatus.PENDING
                logger.info(f"Reset stale link {link.id} to pending")
            
            db.commit()
            logger.info(f"Reset {len(stale_links)} stale processing task(s)")
        
        # Process any pending links
        pending_links = db.query(Link).filter(
            Link.status == LinkStatus.PENDING,
            Link.retry_count < 3
        ).all()
        
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
    user = db.query(User).filter(User.username == username).first()
    
    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "Invalid username or password"},
            status_code=400
        )
    
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
        max_age=60 * 60 * 24 * 7,  # 7 days
        samesite="lax",
        secure=False  # Set to True in production with HTTPS
    )
    
    logger.info(f"User logged in: {user.username}")
    return response


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
    # Validate username
    if db.query(User).filter(User.username == username).first():
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Username already exists"},
            status_code=400
        )
    
    # Validate invite code
    invite = db.query(Invite).filter(Invite.code == invite_code).first()
    if not invite or invite.is_used:
        return templates.TemplateResponse(
            "register.html",
            {"request": request, "error": "Invalid or used invite code"},
            status_code=400
        )
    
    # Create user
    try:
        encrypted_token = encrypt_token(github_token)
        
        user = User(
            username=username,
            hashed_password=get_password_hash(password),
            encrypted_github_token=encrypted_token,
            repo_owner=repo_owner,
            repo_name=repo_name,
            tags=[],
            is_active=True
        )
        
        db.add(user)
        db.flush()
        
        # Mark invite as used
        invite.used_by_user_id = user.id
        invite.used_at = datetime.now()
        
        db.commit()
        
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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """User dashboard showing recent submissions."""
    links = db.query(Link).filter(
        Link.user_id == current_user.id
    ).order_by(Link.submitted_at.desc()).limit(50).all()
    
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "user": current_user,
            "links": links
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
    from src.services.processor import validate_url, check_duplicate_url
    
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
    
    # Check duplicate
    if check_duplicate_url(db, current_user.id, url):
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
    
    # Parse tags
    try:
        selected_tags = json.loads(tags_json)
    except:
        selected_tags = []
    
    # Create link
    link = Link(
        user_id=current_user.id,
        url=url,
        title=title if title else None,
        selected_tags=selected_tags,
        score=score,
        status=LinkStatus.PENDING,
        retry_count=0
    )
    
    db.add(link)
    db.commit()
    db.refresh(link)
    
    logger.info(f"Link submitted by {current_user.username}: {url} (ID: {link.id})")
    
    # Process in background
    background_tasks.add_task(process_link, link.id)
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@app.post("/links/{link_id}/title")
async def update_link_title(
    link_id: int,
    background_tasks: BackgroundTasks,
    title: str = Form(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update title for a link that needs manual title."""
    link = db.query(Link).filter(
        Link.id == link_id,
        Link.user_id == current_user.id
    ).first()
    
    if not link:
        raise HTTPException(status_code=404, detail="Link not found")
    
    if link.status != LinkStatus.NEEDS_TITLE:
        raise HTTPException(status_code=400, detail="Link does not need title")
    
    link.title = title
    link.status = LinkStatus.PENDING
    link.error_message = None
    db.commit()
    
    logger.info(f"Title updated for link {link_id}: {title}")
    
    # Queue for processing in background
    background_tasks.add_task(process_link, link.id)
    
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@app.get("/tags", response_class=HTMLResponse)
async def tags_page(
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Tag management page."""
    max_tags = int(os.getenv("MAX_TAGS_PER_USER", "100"))
    return templates.TemplateResponse(
        "tags.html",
        {
            "request": request,
            "user": current_user,
            "tags": sorted(current_user.tags),
            "max_tags": max_tags
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
    max_tags = int(os.getenv("MAX_TAGS_PER_USER", "100"))
    tag = tag.lower().strip()
    
    if tag in current_user.tags:
        return templates.TemplateResponse(
            "tags.html",
            {
                "request": request,
                "user": current_user,
                "tags": sorted(current_user.tags),
                "max_tags": max_tags,
                "error": f"Tag '{tag}' already exists"
            },
            status_code=409
        )
    
    if len(current_user.tags) >= max_tags:
        return templates.TemplateResponse(
            "tags.html",
            {
                "request": request,
                "user": current_user,
                "tags": sorted(current_user.tags),
                "max_tags": max_tags,
                "error": f"Maximum tag limit ({max_tags}) reached"
            },
            status_code=400
        )
    
    current_user.tags.append(tag)
    # Mark the attribute as modified for SQLAlchemy to detect the change
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(current_user, "tags")
    db.commit()
    
    logger.info(f"Tag added by {current_user.username}: {tag}")
    
    return RedirectResponse(url="/tags", status_code=status.HTTP_302_FOUND)


@app.post("/tags/delete/{tag}")
async def delete_tag(
    tag: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a tag."""
    tag = tag.lower()
    
    if tag in current_user.tags:
        current_user.tags.remove(tag)
        # Mark the attribute as modified for SQLAlchemy to detect the change
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(current_user, "tags")
        db.commit()
        logger.info(f"Tag deleted by {current_user.username}: {tag}")
    
    return RedirectResponse(url="/tags", status_code=status.HTTP_302_FOUND)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
