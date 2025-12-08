# LogKeep - Project Plan

## Overview

LogKeep is a self-hosted multi-user web service that allows users to curate content from links using their personal Logseq graphs stored on GitHub. The primary interface is optimized for smartphone use with minimal typing required.

## Core Workflow

1. User browses RSS feeds on smartphone and finds interesting links
2. User submits link URL via mobile-optimized web interface
3. System extracts title and metadata asynchronously
4. If extraction fails, user is prompted to provide title manually
5. User selects tags from personal collection using autocomplete
6. Background worker commits formatted entry to user's Logseq GitHub repository
7. Entry appears in Logseq graph for later consumption

## Architecture

### Technology Stack

- **Backend**: FastAPI (Python 3.12)
- **Database**: SQLite with SQLAlchemy ORM
- **Authentication**: JWT session cookies with bcrypt password hashing
- **Encryption**: Fernet (symmetric) for GitHub token storage
- **Content Extraction**: trafilatura with beautifulsoup4 fallback
- **GitHub Integration**: PyGithub library
- **Background Processing**: FastAPI BackgroundTasks
- **Templates**: Jinja2 with mobile-first responsive CSS
- **Admin Interface**: Click CLI framework
- **Deployment**: Docker with docker-compose

### Project Structure

```
logkeep/
├── src/
│   ├── api/
│   │   ├── __init__.py
│   │   ├── auth.py          # Login, logout, registration endpoints
│   │   ├── links.py         # Link submission, history, title update
│   │   ├── tags.py          # Tag management endpoints
│   │   └── health.py        # Health check endpoint
│   ├── services/
│   │   ├── __init__.py
│   │   ├── processor.py     # Link processing logic (extraction, validation)
│   │   └── github.py        # GitHub repository operations
│   ├── models/
│   │   ├── __init__.py
│   │   ├── user.py          # User model with encrypted tokens
│   │   ├── link.py          # Link submission tracking
│   │   └── invite.py        # Invite code system
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── database.py      # Database initialization and session
│   │   ├── encryption.py    # Fernet encrypt/decrypt functions
│   │   ├── auth.py          # Authentication middleware and helpers
│   │   └── logging.py       # Logging configuration
│   ├── cli/
│   │   ├── __init__.py
│   │   └── admin.py         # Admin CLI commands
│   ├── templates/
│   │   ├── base.html        # Base template with mobile CSS
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html   # Submission history and status
│   │   ├── submit.html      # Link submission form
│   │   └── tags.html        # Tag management interface
│   ├── static/
│   │   └── css/
│   │       └── style.css    # Mobile-first responsive styles
│   └── main.py              # FastAPI application entry point
├── data/                    # SQLite database storage (gitignored)
├── logs/                    # Application logs (gitignored)
├── .devcontainer/
│   ├── devcontainer.json
│   └── install-gh.sh        # GitHub CLI installation script
├── .env.example             # Environment variable template
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── README.md
├── LICENSE
└── PLAN.md                  # This file
```

## Data Models

### User Model
```python
- id: Integer (primary key)
- username: String (unique, indexed)
- hashed_password: String
- encrypted_github_token: String (Fernet encrypted)
- repo_owner: String (GitHub username/org)
- repo_name: String (repository name)
- tags: JSON Array (user's personal tag collection)
- is_active: Boolean (default True)
- created_at: DateTime
```

### Link Model
```python
- id: Integer (primary key)
- user_id: Integer (foreign key to User)
- url: String (unique per user via composite constraint)
- title: String (nullable until extracted/provided)
- selected_tags: JSON Array
- status: Enum [pending, processing, needs_title, completed, failed]
- retry_count: Integer (default 0, max 3)
- error_message: Text (nullable)
- submitted_at: DateTime
- processed_at: DateTime (nullable)
```

### Invite Model
```python
- id: Integer (primary key)
- code: String (UUID, unique)
- created_by_user_id: Integer (nullable, for tracking)
- used_by_user_id: Integer (nullable, foreign key to User)
- created_at: DateTime
- used_at: DateTime (nullable)
```

## Key Features

### 1. Authentication & Authorization
- **Invite-only registration**: Users need valid invite code to register
- **Session-based auth**: JWT tokens stored in HTTP-only cookies
- **Password security**: Bcrypt hashing with appropriate work factor
- **Token encryption**: GitHub PATs encrypted at rest using Fernet

### 2. Link Submission & Processing
- **Duplicate detection**: Check user's existing links before queuing
- **Async processing**: BackgroundTasks for non-blocking operations
- **Title extraction**: Automatic via trafilatura/beautifulsoup4
- **Title prompting**: UI flow for manual title when extraction fails
- **Retry logic**: Up to 3 automatic retries on transient failures
- **Status tracking**: Real-time status updates visible in dashboard

### 3. Tag Management
- **Per-user collections**: Each user maintains personal tag set
- **Autocomplete**: HTML5 datalist for mobile-friendly tag selection
- **Tag limits**: Max 100 tags per user to prevent bloat
- **CRUD operations**: Add/remove tags via dedicated interface

### 4. GitHub Integration
- **Repository operations**: Clone, append, commit, push workflow
- **Journal file management**: Auto-create `journals/YYYY_MM_DD.md`
- **Format compliance**: `- [[Title]] [link](url) #links #tag1 #tag2`
- **Append strategy**: Add entries to bottom of journal file
- **Conflict resolution**: Last-push-wins (one user per repo)
- **Error handling**: Comprehensive logging of auth, network, conflict errors

### 5. Mobile-Optimized UI
- **Responsive design**: Mobile-first CSS with large tap targets (44px+)
- **Minimal typing**: Autocomplete, pre-filled fields, checkboxes
- **Dashboard**: Recent 50 submissions with color-coded status
- **Inline actions**: Provide title directly from dashboard
- **Fast submission**: Autofocus on URL input for quick entry

### 6. Admin CLI
- **Database management**: Initialize, backup, user management
- **Invite system**: Generate and track invite codes
- **User operations**: Create, activate, deactivate users
- **Debugging tools**: View failed links, retry processing, test GitHub
- **Key generation**: Helper for Fernet encryption keys

### 7. Operational Features
- **Health checks**: `/health` endpoint for monitoring
- **Startup recovery**: Reset stale processing tasks on boot
- **Structured logging**: Console + rotating file logs
- **Docker deployment**: Compose with volume persistence
- **Environment config**: `.env` for secrets and configuration

## Logseq Entry Format

All entries follow this standardized single-line format:

```markdown
- [[Title]] [link](https://example.com/article) #links #tag1 #tag2 #tag3
```

**Components**:
- `- ` - Logseq bullet point
- `[[Title]]` - Page reference link (clickable in Logseq)
- `[link](url)` - Markdown hyperlink to original content
- `#links` - Required tag for all entries
- `#tag1 #tag2` - User-selected tags from personal collection

**Placement**: Entries are appended to the bottom of `journals/YYYY_MM_DD.md`

**File creation**: If journal file doesn't exist, create as blank file (no headers)

## Environment Variables

### Required
- `SESSION_SECRET`: Random string for JWT signing (min 32 chars)
- `ENCRYPTION_KEY`: Fernet key for GitHub token encryption (base64)
- `DATABASE_URL`: SQLite connection string (e.g., `sqlite:///data/logkeep.db`)

### Optional
- `MAX_TAGS_PER_USER`: Maximum tags per user (default: 100)
- `LOG_LEVEL`: Logging verbosity (default: INFO)
- `MAX_RETRY_COUNT`: Link processing retries (default: 3)

### Generation Commands
```bash
# Generate Fernet encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate session secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

## API Endpoints

### Authentication
- `POST /api/auth/register` - Register with invite code
- `POST /api/auth/login` - Login with username/password
- `POST /api/auth/logout` - Clear session cookie
- `GET /api/auth/me` - Get current user info

### Links
- `POST /api/links/submit` - Submit new link (returns duplicate warning if exists)
- `GET /api/links` - Get user's link history (paginated)
- `GET /api/links/{id}` - Get specific link details
- `PATCH /api/links/{id}/title` - Update title (only for needs_title status)

### Tags
- `GET /api/tags` - Get user's tag collection
- `POST /api/tags` - Add new tag (validates against limit)
- `DELETE /api/tags/{tag}` - Remove tag from collection

### Health
- `GET /health` - Health check (database connectivity)

## CLI Commands

### Database
```bash
python -m src.cli.admin init-db              # Initialize database tables
```

### User Management
```bash
python -m src.cli.admin create-user \
  --username alice \
  --password secret123 \
  --github-token ghp_xxxxx \
  --repo-owner alice \
  --repo-name my-logseq

python -m src.cli.admin list-users           # List all users
python -m src.cli.admin deactivate-user alice
python -m src.cli.admin activate-user alice
```

### Invite Management
```bash
python -m src.cli.admin create-invite --count 5  # Generate 5 invite codes
python -m src.cli.admin list-invites --unused    # Show unused invites
```

### Debugging & Maintenance
```bash
python -m src.cli.admin view-failed-links --username alice --limit 10
python -m src.cli.admin retry-failed --username alice
python -m src.cli.admin test-github alice    # Validate GitHub access
python -m src.cli.admin generate-key         # Generate Fernet key
```

## Deployment Guide

### Local Development
```bash
# 1. Clone repository
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep

# 2. Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create environment file
cp .env.example .env
# Edit .env with generated keys

# 5. Initialize database
python -m src.cli.admin init-db

# 6. Create admin user and invites
python -m src.cli.admin create-user \
  --username admin \
  --password changeme \
  --github-token ghp_xxxxx \
  --repo-owner yourusername \
  --repo-name your-logseq-graph

python -m src.cli.admin create-invite --count 3

# 7. Run development server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

### Docker Deployment
```bash
# 1. Create .env file
cp .env.example .env
# Edit .env with production values

# 2. Build and start services
docker-compose up -d

# 3. Initialize database (first time only)
docker-compose exec app python -m src.cli.admin init-db

# 4. Create users via CLI
docker-compose exec app python -m src.cli.admin create-user ...

# 5. View logs
docker-compose logs -f app
```

### VPS Production Deployment

**Prerequisites**: VPS with Docker, domain name, ports 80/443 open

**1. Install Docker & Docker Compose**
```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt install docker-compose
```

**2. Clone and Configure**
```bash
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep
cp .env.example .env
nano .env  # Add production secrets
```

**3. Nginx Reverse Proxy with SSL**
```nginx
# /etc/nginx/sites-available/logkeep
server {
    listen 80;
    server_name logkeep.example.com;
    
    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

**4. SSL with Certbot**
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d logkeep.example.com
```

**5. Start Application**
```bash
docker-compose up -d
docker-compose exec app python -m src.cli.admin init-db
```

**6. Systemd Service (Alternative to Docker)**
```ini
# /etc/systemd/system/logkeep.service
[Unit]
Description=LogKeep Link Curation Service
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/var/www/logkeep
Environment="PATH=/var/www/logkeep/.venv/bin"
ExecStart=/var/www/logkeep/.venv/bin/uvicorn src.main:app --host 127.0.0.1 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

## GitHub Personal Access Token Setup

Users need a GitHub PAT with `repo` scope:

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Set description: "LogKeep - Logseq Graph Access"
4. Set expiration: No expiration (or 1 year, require renewal)
5. Select scopes: **repo** (Full control of private repositories)
6. Click "Generate token"
7. Copy token immediately (shown only once)
8. Provide to LogKeep during registration or user creation

**Note**: Token must have access to the target Logseq repository (private or public).

## User Workflow

### 1. Registration
- Obtain invite code from admin
- Visit `/register` on smartphone
- Enter username, password, invite code
- Enter GitHub PAT and repository details (owner/name)
- System encrypts token and creates account

### 2. Submit Links
- Browse RSS feeds, find interesting article
- Visit LogKeep `/submit` page
- Paste URL (autofocus, minimal typing)
- System extracts title automatically
- Select tags from autocomplete list
- Submit → Returns to dashboard

### 3. Handle Title Extraction Failures
- Dashboard shows "needs_title" status
- Click "Provide Title" button
- Enter title manually
- Resubmit → Processing continues

### 4. Monitor Status
- Dashboard shows recent 50 submissions
- Color-coded status: pending (blue), processing (yellow), completed (green), failed (red)
- Click for error details on failures

### 5. Manage Tags
- Visit `/tags` page
- View current tag collection
- Add new tags (up to 100 total)
- Remove unused tags

### 6. View in Logseq
- Open Logseq graph repository
- Navigate to today's journal page
- See new entries at bottom of page
- Click `[[Title]]` to create/view page reference
- Click `[link](url)` to open original article

## Error Handling & Retry Logic

### Processing States
- **pending**: Queued for processing
- **processing**: Currently being processed
- **needs_title**: Title extraction failed, awaiting user input
- **completed**: Successfully committed to GitHub
- **failed**: Exceeded retry limit or permanent error

### Retry Logic
- Transient failures (network, GitHub API rate limit): Auto-retry up to 3 times
- Permanent failures (auth error, repo not found): Fail immediately, no retry
- Stale processing tasks: Reset to pending on app startup (if retry_count < 3)
- Failed links: Admin can manually retry via CLI

### Error Logging
- All errors logged to `logs/app.log` with full traceback
- Link model stores last error message for user visibility
- GitHub operation errors include API response details
- Authentication errors (invalid token) marked as permanent failure

## Security Considerations

### Token Encryption
- GitHub PATs encrypted at rest using Fernet (AES-128-CBC)
- Encryption key stored in environment variable (never in code/database)
- Decryption only happens in-memory during GitHub operations
- Tokens never exposed in API responses or logs

### Password Security
- Bcrypt hashing with appropriate work factor (default: 12 rounds)
- Passwords never stored in plaintext
- Session cookies HTTP-only, secure flag in production
- JWT tokens signed with secret key

### Database Security
- SQLite file permissions: 600 (owner read/write only)
- No SQL injection: SQLAlchemy ORM parameterization
- Unique constraints prevent duplicate invites/users
- Soft deletes via is_active flag (preserve audit trail)

### Input Validation
- URL validation before processing
- Title length limits (prevent database bloat)
- Tag count limits per user
- Username/password complexity requirements

### Network Security
- HTTPS required in production (via reverse proxy)
- CORS disabled (same-origin only)
- Rate limiting recommended (via nginx)
- Health check endpoint requires no auth (for monitoring)

## Performance Considerations

### Database
- SQLite sufficient for <1000 users
- Indexes on: user.username, link.user_id, link.status, invite.code
- Composite unique index on (user_id, url) for duplicate detection
- Connection pooling via SQLAlchemy

### Background Processing
- FastAPI BackgroundTasks for simple async (no external dependencies)
- Tasks don't block HTTP responses
- Startup recovery prevents lost jobs
- Consider Redis + Celery if scaling beyond single server

### Content Extraction
- Trafilatura timeout: 10 seconds
- Beautifulsoup4 fallback for failures
- No caching (content changes over time)
- Retries on network timeouts

### GitHub Operations
- Pull before append to reduce conflicts
- Batch operations if multiple links in queue (future optimization)
- PyGithub caching of API responses
- Token reuse across requests (single session)

## Monitoring & Maintenance

### Health Checks
- `/health` endpoint checks database connectivity
- Docker healthcheck every 30 seconds
- Returns JSON: `{"status": "healthy", "database": "connected"}`
- Non-200 response triggers container restart

### Logging
- Structured logging with timestamps
- Rotating file handler: 10MB max, 5 backups
- Log levels: DEBUG (dev), INFO (production)
- Separate log files possible: access.log, error.log

### Backups
- SQLite database: Copy `data/logkeep.db` periodically
- Backup script via cron:
  ```bash
  0 2 * * * cp /var/www/logkeep/data/logkeep.db /backups/logkeep-$(date +\%Y\%m\%d).db
  ```
- Encrypt backups (contain encrypted tokens, hashed passwords)
- Test restore procedure regularly

### Monitoring
- Track failed link count per user
- Monitor disk usage (logs, database)
- GitHub API rate limits (5000/hour authenticated)
- Alert on repeated processing failures

## Future Enhancements

### Phase 2 (Post-MVP)
- [ ] AI-powered summarization (OpenAI/Anthropic integration)
- [ ] Automatic tag suggestions based on content
- [ ] Browser extension for one-click submission
- [ ] RSS feed integration (auto-submit from subscriptions)
- [ ] Multi-repository support per user
- [ ] Collaborative graphs (multiple users, same repo)

### Phase 3 (Advanced)
- [ ] Full-text search across submitted links
- [ ] Analytics dashboard (submission trends, popular tags)
- [ ] Export/import tag collections
- [ ] Webhook support for custom integrations
- [ ] Mobile native app (React Native/Flutter)
- [ ] Self-service user registration (waitlist)

## Testing Strategy

### Unit Tests
- Models: CRUD operations, validation, constraints
- Encryption: Encrypt/decrypt roundtrip
- Authentication: Password hashing, JWT validation
- GitHub service: Mock PyGithub responses

### Integration Tests
- API endpoints: Full request/response cycle
- Background tasks: Processing workflow end-to-end
- Database: Transactions, rollbacks, concurrency
- CLI commands: User creation, invite generation

### Manual Testing
- Mobile UI: Test on actual smartphone devices
- Browser compatibility: Safari iOS, Chrome Android
- Network failures: Simulate GitHub API errors
- Edge cases: Empty tags, very long titles, malformed URLs

## Known Limitations

1. **Single server**: FastAPI BackgroundTasks not distributed (use Celery for multi-server)
2. **One user per repository**: No conflict resolution for concurrent edits
3. **No link editing**: Cannot modify URL/title/tags after completion (delete and resubmit)
4. **No pagination**: Dashboard shows recent 50 (add pagination for power users)
5. **No bulk operations**: Cannot submit/delete multiple links at once
6. **SQLite concurrency**: Write locks under high load (migrate to PostgreSQL if needed)
7. **No email notifications**: No alerts for failed processing (add SMTP integration)
8. **Invite-only**: No public registration or waitlist (feature flag for future)

## Success Metrics

### MVP Launch Criteria
- [ ] User can register with invite code
- [ ] User can submit link and see it in Logseq within 1 minute
- [ ] Title extraction works for 90%+ of common sites
- [ ] Mobile UI usable on iPhone/Android without zoom
- [ ] No data loss on server restart (persistent queue)
- [ ] Admin can manage users via CLI
- [ ] Deployment documented and tested on VPS

### Post-Launch Metrics
- Average time from submission to Logseq commit
- Title extraction success rate
- Processing failure rate and common errors
- User retention (daily/weekly active)
- Tags per user (gauge feature usage)
- Links per user per day (engagement)

## License

MIT License - See LICENSE file for details.

---

**Project Status**: Planning Complete → Ready for Implementation

**Next Steps**:
1. Create project structure
2. Implement database models
3. Build authentication layer
4. Create core processing services
5. Develop API endpoints
6. Design mobile UI
7. Implement admin CLI
8. Create deployment configs
9. Write documentation
10. Test end-to-end workflow
