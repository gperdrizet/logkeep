#!/usr/bin/env python3
"""Admin CLI for LogKeep database and user management."""
import os
import sys
import click
from datetime import datetime
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

# Add parent directory to path for imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))

from src.utils.database import SessionLocal, init_db, engine
from src.utils.encryption import encrypt_token, decrypt_token
from src.utils.auth import get_password_hash
from src.models.user import User
from src.models.invite import Invite
from src.models.link import Link
from src.models import LinkStatus
from src.services.github import test_github_connection


@click.group()
def cli():
    """LogKeep Admin CLI - Database and user management."""
    pass


@cli.command('init-db')
def init_db_cmd():
    """Initialize database tables."""
    try:
        init_db()
        click.echo("[OK] Database initialized successfully")
    except Exception as e:
        click.echo(f"[FAIL] Error initializing database: {str(e)}", err=True)
        sys.exit(1)


@cli.command('create-user')
@click.option('--username', prompt=True, help='Username')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password')
def create_user(username, password):
    """Create a new user."""
    db = SessionLocal()
    try:
        # Validate password length (bcrypt limit is 72 bytes)
        if len(password.encode('utf-8')) > 72:
            click.echo("[WARN] Warning: Password longer than 72 bytes will be truncated", err=True)
        
        # Check if username exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            click.echo(f"[FAIL] User '{username}' already exists", err=True)
            sys.exit(1)
        
        # Ask about GitHub integration
        github_enabled = click.confirm('Enable GitHub/Logseq integration?', default=False)
        
        encrypted_token = None
        repo_owner = None
        repo_name = None
        
        if github_enabled:
            github_token = click.prompt('GitHub Personal Access Token', hide_input=True)
            repo_owner = click.prompt('GitHub repository owner')
            repo_name = click.prompt('GitHub repository name')
            encrypted_token = encrypt_token(github_token)
        
        # Create user
        user = User(
            username=username,
            hashed_password=get_password_hash(password),
            github_enabled=github_enabled,
            encrypted_github_token=encrypted_token,
            repo_owner=repo_owner,
            repo_name=repo_name,
            tags=[],
            is_active=True
        )
        
        db.add(user)
        db.commit()
        db.refresh(user)
        
        click.echo(f"[OK] User created: {username} (ID: {user.id})")
        if github_enabled:
            click.echo(f"  Repository: {repo_owner}/{repo_name}")
        else:
            click.echo("  GitHub integration: Disabled")
        
    except Exception as e:
        click.echo(f"[FAIL] Error creating user: {str(e)}", err=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


@cli.command('create-invite')
@click.option('--count', default=1, help='Number of invite codes to generate')
def create_invite(count):
    """Generate invite codes."""
    db = SessionLocal()
    try:
        codes = []
        for _ in range(count):
            invite = Invite()
            db.add(invite)
            db.flush()
            codes.append(invite.code)
        
        db.commit()
        
        click.echo(f"[OK] Generated {count} invite code(s):")
        for code in codes:
            click.echo(f"  {code}")
        
    except Exception as e:
        click.echo(f"[FAIL] Error creating invites: {str(e)}", err=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


@cli.command('list-users')
def list_users():
    """List all users."""
    db = SessionLocal()
    try:
        users = db.query(User).all()
        
        if not users:
            click.echo("No users found")
            return
        
        click.echo(f"\nTotal users: {len(users)}\n")
        for user in users:
            status = "[OK] Active" if user.is_active else "[FAIL] Inactive"
            github_status = "[OK] Enabled" if user.github_enabled else "[FAIL] Disabled"
            click.echo(f"ID: {user.id}")
            click.echo(f"  Username: {user.username}")
            if user.github_enabled:
                click.echo(f"  Repository: {user.repo_owner}/{user.repo_name}")
            click.echo(f"  GitHub: {github_status}")
            click.echo(f"  Tags: {len(user.tags)}")
            click.echo(f"  Status: {status}")
            click.echo(f"  Created: {user.created_at.strftime('%Y-%m-%d %I:%M %p')}")
            click.echo()
        
    except Exception as e:
        click.echo(f"[FAIL] Error listing users: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command('list-invites')
@click.option('--unused', is_flag=True, help='Show only unused invites')
def list_invites(unused):
    """List invite codes."""
    db = SessionLocal()
    try:
        query = db.query(Invite)
        if unused:
            query = query.filter(Invite.used_by_user_id.is_(None))
        
        invites = query.all()
        
        if not invites:
            click.echo("No invites found")
            return
        
        click.echo(f"\nTotal invites: {len(invites)}\n")
        for invite in invites:
            status = "[OK] Unused" if not invite.is_used else "[FAIL] Used"
            click.echo(f"Code: {invite.code}")
            click.echo(f"  Status: {status}")
            click.echo(f"  Created: {invite.created_at.strftime('%Y-%m-%d %I:%M %p')}")
            if invite.is_used:
                user = db.query(User).filter(User.id == invite.used_by_user_id).first()
                click.echo(f"  Used by: {user.username if user else 'Unknown'}")
                click.echo(f"  Used at: {invite.used_at.strftime('%Y-%m-%d %I:%M %p')}")
            click.echo()
        
    except Exception as e:
        click.echo(f"[FAIL] Error listing invites: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command('deactivate-user')
@click.argument('username')
def deactivate_user(username):
    """Deactivate a user account."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        user.is_active = False
        db.commit()
        
        click.echo(f"[OK] User '{username}' deactivated")
        
    except Exception as e:
        click.echo(f"[FAIL] Error deactivating user: {str(e)}", err=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


@cli.command('activate-user')
@click.argument('username')
def activate_user(username):
    """Activate a user account."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        user.is_active = True
        db.commit()
        
        click.echo(f"[OK] User '{username}' activated")
        
    except Exception as e:
        click.echo(f"[FAIL] Error activating user: {str(e)}", err=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


@cli.command('delete-user')
@click.argument('username')
@click.option('--force', is_flag=True, help='Skip confirmation prompt')
def delete_user(username, force):
    """Delete a user account and all associated data."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        # Count associated data
        link_count = db.query(Link).filter(Link.user_id == user.id).count()
        
        # Confirm deletion
        if not force:
            click.echo(f"\n[WARN] Warning: This will permanently delete:")
            click.echo(f"  - User: {username}")
            click.echo(f"  - Links: {link_count}")
            click.echo(f"  - All associated tags and data")
            if not click.confirm('\nAre you sure you want to continue?'):
                click.echo("Deletion cancelled")
                sys.exit(0)
        
        # Delete user (cascade will handle related data)
        db.delete(user)
        db.commit()
        
        click.echo(f"[OK] User '{username}' and all associated data deleted")
        
    except Exception as e:
        click.echo(f"[FAIL] Error deleting user: {str(e)}", err=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


@cli.command('view-failed-links')
@click.option('--username', help='Filter by username')
@click.option('--limit', default=10, help='Maximum number of results')
def view_failed_links(username, limit):
    """View failed link submissions."""
    db = SessionLocal()
    try:
        query = db.query(Link).filter(Link.status == LinkStatus.FAILED)
        
        if username:
            user = db.query(User).filter(User.username == username).first()
            if not user:
                click.echo(f"[FAIL] User '{username}' not found", err=True)
                sys.exit(1)
            query = query.filter(Link.user_id == user.id)
        
        links = query.order_by(Link.submitted_at.desc()).limit(limit).all()
        
        if not links:
            click.echo("No failed links found")
            return
        
        click.echo(f"\nFailed links: {len(links)}\n")
        for link in links:
            user = db.query(User).filter(User.id == link.user_id).first()
            click.echo(f"ID: {link.id}")
            click.echo(f"  User: {user.username if user else 'Unknown'}")
            click.echo(f"  URL: {link.url}")
            click.echo(f"  Title: {link.title or 'N/A'}")
            click.echo(f"  Retries: {link.retry_count}")
            click.echo(f"  Error: {link.error_message}")
            click.echo(f"  Submitted: {link.submitted_at.strftime('%Y-%m-%d %I:%M %p')}")
            click.echo()
        
    except Exception as e:
        click.echo(f"[FAIL] Error viewing failed links: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command('retry-failed')
@click.argument('username')
def retry_failed(username):
    """Reset failed links to pending for retry."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        failed_links = db.query(Link).filter(
            Link.user_id == user.id,
            Link.status == LinkStatus.FAILED,
            Link.retry_count < 3
        ).all()
        
        if not failed_links:
            click.echo("No failed links eligible for retry")
            return
        
        for link in failed_links:
            link.status = LinkStatus.PENDING
            link.error_message = None
        
        db.commit()
        
        click.echo(f"[OK] Reset {len(failed_links)} failed link(s) to pending")
        
    except Exception as e:
        click.echo(f"[FAIL] Error retrying failed links: {str(e)}", err=True)
        db.rollback()
        sys.exit(1)
    finally:
        db.close()


@cli.command('test-github')
@click.argument('username')
def test_github(username):
    """Test GitHub connection for a user."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        if not user.github_enabled:
            click.echo(f"[FAIL] GitHub integration is not enabled for user '{username}'", err=True)
            sys.exit(1)
        
        click.echo(f"Testing GitHub connection for {username}...\n")
        
        success, message = test_github_connection(user)
        
        if success:
            click.echo("[OK] Connection successful!\n")
            click.echo(message)
        else:
            click.echo("[FAIL] Connection failed!\n", err=True)
            click.echo(message, err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(f"[FAIL] Error testing GitHub connection: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command('generate-key')
def generate_key():
    """Generate a new Fernet encryption key."""
    key = Fernet.generate_key()
    click.echo("New Fernet encryption key:")
    click.echo(key.decode())
    click.echo("\nAdd this to your .env file as ENCRYPTION_KEY")


@cli.command('import-tags')
@click.argument('username')
def import_tags(username):
    """Import tags from user's existing journal files."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        click.echo(f"Importing tags from {user.repo_owner}/{user.repo_name}...")
        
        from src.services.github import import_tags_from_journals
        count, error = import_tags_from_journals(user, db)
        
        if error:
            click.echo(f"[WARN] Warning: {error}")
        
        if count > 0:
            click.echo(f"[OK] Imported {count} tag(s)")
            click.echo("\nImported tags:")
            for tag in sorted(user.tags):
                click.echo(f"  #{tag}")
        else:
            click.echo("No new tags imported")
        
    except Exception as e:
        click.echo(f"[FAIL] Error importing tags: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command('backfill-summaries')
@click.argument('username')
def backfill_summaries(username):
    """Generate summaries for existing completed links."""
    from src.config import settings
    from src.services.processor import is_summarizable_url, extract_and_truncate_article
    from src.services.llm import get_llm_service
    from src.utils.logging import logger
    
    if not settings.llm_enabled:
        click.echo("[FAIL] LLM service is not enabled. Set LLM_ENABLED=true in .env", err=True)
        sys.exit(1)
    
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        # Query links that need summarization
        links_to_summarize = db.query(Link).filter(
            Link.user_id == user.id,
            Link.status == LinkStatus.COMPLETED,
            Link.summary.is_(None),
            Link.summary_error.is_(None),
            Link.summary_retry_count < settings.llm_max_retries
        ).all()
        
        total = len(links_to_summarize)
        if total == 0:
            click.echo("No links need summarization")
            return
        
        click.echo(f"Found {total} link(s) to summarize for user '{username}'")
        click.echo("Starting backfill (this may take a while)...\n")
        
        llm_service = get_llm_service()
        success_count = 0
        failed_count = 0
        
        for i, link in enumerate(links_to_summarize, 1):
            click.echo(f"[{i}/{total}] Processing: {link.title[:50] if link.title else link.url[:50]}...")
            
            try:
                # Check if summarizable
                is_summarizable, skip_reason = is_summarizable_url(link.url)
                if not is_summarizable:
                    link.summary_error = skip_reason
                    db.commit()
                    click.echo(f"  ⊘ Skipped: {skip_reason}")
                    failed_count += 1
                    continue
                
                # Extract content
                content, extractable, extract_error = extract_and_truncate_article(link.url)
                if not extractable or not content:
                    link.summary_error = extract_error or "Article content unavailable"
                    db.commit()
                    click.echo(f"  ⊘ Failed: {extract_error}")
                    failed_count += 1
                    continue
                
                # Generate summary
                success, summary, error = llm_service.summarize(content, link.title, link.url)
                if success and summary:
                    link.summary = summary
                    link.summarized_at = datetime.now()
                    link.llm_model = settings.llm_model_name
                    link.summary_error = None
                    db.commit()
                    click.echo(f"  [OK] Summary generated ({len(summary)} chars)")
                    success_count += 1
                else:
                    link.summary_retry_count += 1
                    link.summary_error = (error or "Summarization failed")[:500]
                    db.commit()
                    click.echo(f"  [FAIL] Failed: {error}")
                    failed_count += 1
                    logger.error(f"Backfill failed for link {link.id}: {error}")
                    
            except Exception as e:
                link.summary_retry_count += 1
                link.summary_error = "Summarization failed"[:500]
                db.commit()
                click.echo(f"  [FAIL] Error: {str(e)}")
                failed_count += 1
                logger.error(f"Backfill error for link {link.id}: {e}", exc_info=True)
        
        click.echo(f"\n[OK] Backfill complete: {success_count} summaries generated, {failed_count} failures")
        
    except Exception as e:
        click.echo(f"[FAIL] Error during backfill: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


@cli.command('reset-summary-retries')
@click.argument('username')
@click.option('--link-id', type=int, help='Reset specific link (optional, resets all if not specified)')
def reset_summary_retries(username, link_id):
    """Reset summary retry count for failed links."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            click.echo(f"[FAIL] User '{username}' not found", err=True)
            sys.exit(1)
        
        if link_id:
            # Reset specific link
            link = db.query(Link).filter(
                Link.id == link_id,
                Link.user_id == user.id
            ).first()
            
            if not link:
                click.echo(f"[FAIL] Link {link_id} not found for user '{username}'", err=True)
                sys.exit(1)
            
            link.summary_retry_count = 0
            link.summary_error = None
            db.commit()
            click.echo(f"[OK] Reset retry count for link {link_id}")
        else:
            # Reset all failed links for user
            links = db.query(Link).filter(
                Link.user_id == user.id,
                Link.summary_error.isnot(None)
            ).all()
            
            count = len(links)
            if count == 0:
                click.echo("No failed links found")
                return
            
            for link in links:
                link.summary_retry_count = 0
                link.summary_error = None
            
            db.commit()
            click.echo(f"[OK] Reset retry count for {count} link(s)")
        
    except Exception as e:
        click.echo(f"[FAIL] Error resetting retries: {str(e)}", err=True)
        sys.exit(1)
    finally:
        db.close()


if __name__ == '__main__':
    cli()
