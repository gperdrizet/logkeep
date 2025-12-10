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
        click.echo("✓ Database initialized successfully")
    except Exception as e:
        click.echo(f"✗ Error initializing database: {str(e)}", err=True)
        sys.exit(1)


@cli.command('create-user')
@click.option('--username', prompt=True, help='Username')
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True, help='Password')
@click.option('--github-token', prompt=True, hide_input=True, help='GitHub Personal Access Token')
@click.option('--repo-owner', prompt=True, help='GitHub repository owner')
@click.option('--repo-name', prompt=True, help='GitHub repository name')
def create_user(username, password, github_token, repo_owner, repo_name):
    """Create a new user."""
    db = SessionLocal()
    try:
        # Validate password length (bcrypt limit is 72 bytes)
        if len(password.encode('utf-8')) > 72:
            click.echo("⚠ Warning: Password longer than 72 bytes will be truncated", err=True)
        
        # Check if username exists
        existing = db.query(User).filter(User.username == username).first()
        if existing:
            click.echo(f"✗ User '{username}' already exists", err=True)
            sys.exit(1)
        
        # Encrypt GitHub token
        encrypted_token = encrypt_token(github_token)
        
        # Create user
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
        db.commit()
        db.refresh(user)
        
        click.echo(f"✓ User created: {username} (ID: {user.id})")
        click.echo(f"  Repository: {repo_owner}/{repo_name}")
        
    except Exception as e:
        click.echo(f"✗ Error creating user: {str(e)}", err=True)
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
        
        click.echo(f"✓ Generated {count} invite code(s):")
        for code in codes:
            click.echo(f"  {code}")
        
    except Exception as e:
        click.echo(f"✗ Error creating invites: {str(e)}", err=True)
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
            status = "✓ Active" if user.is_active else "✗ Inactive"
            click.echo(f"ID: {user.id}")
            click.echo(f"  Username: {user.username}")
            click.echo(f"  Repository: {user.repo_owner}/{user.repo_name}")
            click.echo(f"  Tags: {len(user.tags)}")
            click.echo(f"  Status: {status}")
            click.echo(f"  Created: {user.created_at.strftime('%Y-%m-%d %I:%M %p')}")
            click.echo()
        
    except Exception as e:
        click.echo(f"✗ Error listing users: {str(e)}", err=True)
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
            status = "✓ Unused" if not invite.is_used else "✗ Used"
            click.echo(f"Code: {invite.code}")
            click.echo(f"  Status: {status}")
            click.echo(f"  Created: {invite.created_at.strftime('%Y-%m-%d %I:%M %p')}")
            if invite.is_used:
                user = db.query(User).filter(User.id == invite.used_by_user_id).first()
                click.echo(f"  Used by: {user.username if user else 'Unknown'}")
                click.echo(f"  Used at: {invite.used_at.strftime('%Y-%m-%d %I:%M %p')}")
            click.echo()
        
    except Exception as e:
        click.echo(f"✗ Error listing invites: {str(e)}", err=True)
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
            click.echo(f"✗ User '{username}' not found", err=True)
            sys.exit(1)
        
        user.is_active = False
        db.commit()
        
        click.echo(f"✓ User '{username}' deactivated")
        
    except Exception as e:
        click.echo(f"✗ Error deactivating user: {str(e)}", err=True)
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
            click.echo(f"✗ User '{username}' not found", err=True)
            sys.exit(1)
        
        user.is_active = True
        db.commit()
        
        click.echo(f"✓ User '{username}' activated")
        
    except Exception as e:
        click.echo(f"✗ Error activating user: {str(e)}", err=True)
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
                click.echo(f"✗ User '{username}' not found", err=True)
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
        click.echo(f"✗ Error viewing failed links: {str(e)}", err=True)
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
            click.echo(f"✗ User '{username}' not found", err=True)
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
        
        click.echo(f"✓ Reset {len(failed_links)} failed link(s) to pending")
        
    except Exception as e:
        click.echo(f"✗ Error retrying failed links: {str(e)}", err=True)
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
            click.echo(f"✗ User '{username}' not found", err=True)
            sys.exit(1)
        
        click.echo(f"Testing GitHub connection for {username}...\n")
        
        success, message = test_github_connection(user)
        
        if success:
            click.echo("✓ Connection successful!\n")
            click.echo(message)
        else:
            click.echo("✗ Connection failed!\n", err=True)
            click.echo(message, err=True)
            sys.exit(1)
        
    except Exception as e:
        click.echo(f"✗ Error testing GitHub connection: {str(e)}", err=True)
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


if __name__ == '__main__':
    cli()
