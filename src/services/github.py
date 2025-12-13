"""GitHub repository integration service."""
import os
import re
import tempfile
import shutil
from datetime import datetime
from typing import Tuple, Optional
from github import Github, GithubException
from sqlalchemy.orm import Session
from src.config import settings
from src.models.link import Link
from src.models.user import User
from src.utils.encryption import decrypt_token
from src.utils.logging import logger


def commit_link_to_github(link: Link, db: Session) -> Tuple[bool, Optional[str]]:
    """
    Commit link entry to user's Logseq GitHub repository.
    
    Creates the journal file if it doesn't exist and appends the formatted
    entry to the bottom of the file.
    
    Args:
        link: Link object to commit
        db: Database session
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    try:
        # Get user
        user = db.query(User).filter(User.id == link.user_id).first()
        if not user:
            return False, "User not found"
        
        # Decrypt GitHub token
        try:
            github_token = decrypt_token(user.encrypted_github_token)
        except Exception as e:
            logger.error(f"Failed to decrypt GitHub token for user {user.username}: {str(e)}")
            return False, "Failed to decrypt GitHub token"
        
        # Initialize GitHub client
        try:
            g = Github(github_token)
            repo = g.get_repo(f"{user.repo_owner}/{user.repo_name}")
        except GithubException as e:
            if e.status == 401:
                return False, "GitHub authentication failed - invalid token"
            elif e.status == 404:
                return False, f"Repository {user.repo_owner}/{user.repo_name} not found"
            else:
                return False, f"GitHub API error: {e.data.get('message', str(e))}"
        
        # Get today's journal file path
        today = datetime.now()
        journal_filename = today.strftime("%Y_%m_%d.md")
        journal_path = f"journals/{journal_filename}"
        
        logger.info(f"Committing link {link.id} to {user.repo_owner}/{user.repo_name}:{journal_path}")
        
        # Format the entry
        # Format: - [[Title]] [link](url) #links #tag1 #tag2 score
        tags_str = " ".join([f"#{tag.name}" for tag in link.tags])
        score_str = f" {link.score}" if link.score is not None else ""
        entry = f"- [[{link.title}]] [link]({link.url}) #links {tags_str}{score_str}\n"
        
        # Try to get existing file
        try:
            file = repo.get_contents(journal_path)
            # File exists - append to it
            existing_content = file.decoded_content.decode('utf-8')
            new_content = existing_content + entry
            
            # Update file
            commit_message = f"Add link: {link.title}"
            repo.update_file(
                path=journal_path,
                message=commit_message,
                content=new_content,
                sha=file.sha
            )
            logger.info(f"Updated existing journal file: {journal_path}")
            
        except GithubException as e:
            if e.status == 404:
                # File doesn't exist - create it
                # First, ensure journals/ directory exists by creating the file
                commit_message = f"Add link: {link.title}"
                repo.create_file(
                    path=journal_path,
                    message=commit_message,
                    content=entry
                )
                logger.info(f"Created new journal file: {journal_path}")
            else:
                raise
        
        return True, None
        
    except GithubException as e:
        error_msg = f"GitHub error: {e.data.get('message', str(e)) if hasattr(e, 'data') else str(e)}"
        logger.error(f"Failed to commit link {link.id}: {error_msg}")
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Failed to commit link {link.id}: {error_msg}", exc_info=True)
        return False, error_msg


def test_github_connection(user: User) -> Tuple[bool, str]:
    """
    Test GitHub connection and repository access for a user.
    
    Args:
        user: User object
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    try:
        # Decrypt token
        github_token = decrypt_token(user.encrypted_github_token)
        
        # Initialize GitHub client
        g = Github(github_token)
        
        # Test authentication
        auth_user = g.get_user()
        
        # Test repository access
        repo = g.get_repo(f"{user.repo_owner}/{user.repo_name}")
        
        # Check if journals/ directory exists
        try:
            repo.get_contents("journals")
            journals_exists = True
        except GithubException:
            journals_exists = False
        
        message = f"✓ Connected as {auth_user.login}\n"
        message += f"✓ Repository {user.repo_owner}/{user.repo_name} accessible\n"
        message += f"✓ journals/ directory: {'exists' if journals_exists else 'will be created on first link'}"
        
        return True, message
        
    except GithubException as e:
        if e.status == 401:
            return False, "Authentication failed - invalid GitHub token"
        elif e.status == 404:
            return False, f"Repository {user.repo_owner}/{user.repo_name} not found or not accessible"
        else:
            return False, f"GitHub error: {e.data.get('message', str(e)) if hasattr(e, 'data') else str(e)}"
    except Exception as e:
        return False, f"Error: {str(e)}"


def update_link_in_journal(link: Link, db: Session) -> Tuple[bool, Optional[str]]:
    """
    Update an existing link entry in the user's Logseq GitHub repository.
    
    Finds the specific link entry in the journal file and updates it in place.
    
    Args:
        link: Link object with updated data
        db: Database session
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    import re
    
    try:
        # Get user
        user = db.query(User).filter(User.id == link.user_id).first()
        if not user:
            return False, "User not found"
        
        # Decrypt GitHub token
        try:
            github_token = decrypt_token(user.encrypted_github_token)
        except Exception as e:
            logger.error(f"Failed to decrypt GitHub token for user {user.username}: {str(e)}")
            return False, "Failed to decrypt GitHub token"
        
        # Initialize GitHub client
        try:
            g = Github(github_token)
            repo = g.get_repo(f"{user.repo_owner}/{user.repo_name}")
        except GithubException as e:
            if e.status == 401:
                return False, "GitHub authentication failed - invalid token"
            elif e.status == 404:
                return False, f"Repository {user.repo_owner}/{user.repo_name} not found"
            else:
                return False, f"GitHub API error: {e.data.get('message', str(e))}"
        
        # Get the journal file path for the link's submission date
        journal_date = link.submitted_at
        journal_filename = journal_date.strftime("%Y_%m_%d.md")
        journal_path = f"journals/{journal_filename}"
        
        logger.info(f"Updating link {link.id} in {user.repo_owner}/{user.repo_name}:{journal_path}")
        
        # Try to get existing file
        try:
            file = repo.get_contents(journal_path)
            existing_content = file.decoded_content.decode('utf-8')
        except GithubException as e:
            if e.status == 404:
                return False, f"Journal file {journal_path} not found - cannot update link"
            raise
        
        # Build the new entry format
        tags_str = " ".join([f"#{tag.name}" for tag in link.tags])
        score_str = f" {link.score}" if link.score is not None else ""
        new_entry = f"- [[{link.title}]] [link]({link.url}) #links {tags_str}{score_str}"
        
        # Find and replace the old entry
        # Pattern to match the link entry: - [[...]] [link](url) ...
        # We'll use the URL as the unique identifier since it shouldn't change
        escaped_url = re.escape(link.url)
        pattern = rf'^- \[\[.*?\]\] \[link\]\({escaped_url}\).*?$'
        
        lines = existing_content.split('\n')
        found = False
        updated_lines = []
        
        for line in lines:
            if re.match(pattern, line):
                updated_lines.append(new_entry)
                found = True
                logger.info(f"Found and updating line: {line[:100]}...")
            else:
                updated_lines.append(line)
        
        if not found:
            return False, f"Could not find link entry in journal file - URL may have changed or entry is malformed"
        
        new_content = '\n'.join(updated_lines)
        
        # Update file in GitHub
        commit_message = f"Update link: {link.title}"
        repo.update_file(
            path=journal_path,
            message=commit_message,
            content=new_content,
            sha=file.sha
        )
        
        logger.info(f"Successfully updated link {link.id} in journal file")
        return True, None
        
    except GithubException as e:
        error_msg = f"GitHub error: {e.data.get('message', str(e)) if hasattr(e, 'data') else str(e)}"
        logger.error(f"Failed to update link {link.id}: {error_msg}")
        return False, error_msg
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Failed to update link {link.id}: {error_msg}", exc_info=True)
        return False, error_msg


def import_tags_from_journals(user: User, db: Session) -> Tuple[int, Optional[str]]:
    """
    Import tags from user's existing journal files in GitHub repository.
    
    Reads all markdown files in journals/ directory and extracts hashtags.
    Filters out common system tags and adds unique tags to user's collection.
    
    Args:
        user: User object
        db: Database session
        
    Returns:
        Tuple of (tags_imported_count: int, error_message: Optional[str])
    """
    
    try:
        # Decrypt GitHub token
        github_token = decrypt_token(user.encrypted_github_token)
        
        # Initialize GitHub client
        g = Github(github_token)
        repo = g.get_repo(f"{user.repo_owner}/{user.repo_name}")
        
        logger.info(f"Importing tags from {user.repo_owner}/{user.repo_name} for user {user.username}")
        
        # Try to get journals directory
        try:
            contents = repo.get_contents("journals")
        except GithubException as e:
            if e.status == 404:
                logger.info(f"No journals/ directory found for user {user.username}")
                return 0, None
            raise
        
        # Collect all tags from journal files with counts
        tag_counts = {}
        file_count = 0
        
        # Filter for markdown files
        journal_files = [f for f in contents if f.name.endswith('.md')]
        
        for file in journal_files:
            try:
                content = file.decoded_content.decode('utf-8')
                # Extract hashtags using regex
                # Matches #word, #word-with-dashes, #word_with_underscores
                tags = re.findall(r'#([\w-]+)', content)
                for tag in tags:
                    tag_lower = tag.lower()
                    tag_counts[tag_lower] = tag_counts.get(tag_lower, 0) + 1
                file_count += 1
            except Exception as e:
                logger.warning(f"Error reading journal file {file.name}: {str(e)}")
                continue
        
        # Filter out system tags and tags that don't match our validation
        excluded_tags = {'links', 'link', 'todo', 'done', 'later', 'now', 'doing', 'waiting'}
        valid_tags = {
            tag for tag in tag_counts.keys()
            if tag not in excluded_tags
            and len(tag) <= 50
            and re.match(r'^[a-zA-Z0-9_-]+$', tag)
        }
        
        # Add new tags to user's collection and update counts
        new_tags = [tag for tag in valid_tags if tag not in user.tags]
        
        # Update tag counts for all valid tags (new and existing)
        if not user.tag_counts:
            user.tag_counts = {}
        
        for tag in valid_tags:
            user.tag_counts[tag] = tag_counts[tag]
        
        if new_tags:
            max_tags = int(os.getenv("MAX_TAGS_PER_USER", "1000"))
            available_slots = settings.max_tags_per_user - len(user.tags)
            
            if available_slots > 0:
                tags_to_add = sorted(new_tags)[:available_slots]
                user.tags.extend(tags_to_add)
                
                # Mark as modified for SQLAlchemy
                from sqlalchemy.orm.attributes import flag_modified
                flag_modified(user, "tags")
                flag_modified(user, "tag_counts")
                db.commit()
                
                logger.info(f"Imported {len(tags_to_add)} tags from {file_count} journal files for user {user.username}")
                return len(tags_to_add), None
            else:
                logger.warning(f"User {user.username} already has maximum tags ({settings.max_tags_per_user})")
                return 0, f"Tag collection already at maximum ({settings.max_tags_per_user})"
        else:
            # Even if no new tags, update counts for existing tags
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(user, "tag_counts")
            db.commit()
            logger.info(f"No new tags found in journals for user {user.username}, updated counts for existing tags")
            return 0, None
        
    except GithubException as e:
        error_msg = f"GitHub error: {e.data.get('message', str(e)) if hasattr(e, 'data') else str(e)}"
        logger.error(f"Failed to import tags for user {user.username}: {error_msg}")
        return 0, error_msg
        
    except Exception as e:
        error_msg = f"Unexpected error: {str(e)}"
        logger.error(f"Failed to import tags for user {user.username}: {error_msg}", exc_info=True)
        return 0, error_msg
