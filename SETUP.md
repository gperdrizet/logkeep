# LogKeep - Quick Setup Guide

## Installation Complete! 🎉

The LogKeep application has been fully implemented with all planned features. Here's what was built:

### ✅ Completed features

1. **Project structure**
   - Complete src/ directory with organized modules
   - Dockerfile and docker-compose.yml for deployment
   - .env.example with all configuration options
   - Comprehensive .gitignore

2. **Database layer**
   - SQLAlchemy models: User, Link, Invite
   - Fernet encryption for GitHub tokens
   - SQLite with proper constraints and indexes
   - Duplicate URL detection per user

3. **Authentication system**
   - JWT session-based authentication
   - Bcrypt password hashing
   - HTTP-only cookies for security
   - Invite-only registration

4. **Link processing**
   - Async background processing with FastAPI BackgroundTasks
   - Title extraction (trafilatura + BeautifulSoup fallback)
   - Manual title prompt on extraction failure
   - Retry logic (max 3 attempts)
   - Status tracking (pending/processing/needs_title/completed/failed)

5. **GitHub integration**
   - PyGithub API integration
   - Encrypted token storage
   - Auto-create journal files if missing
   - Standard Logseq format: `- [[Title]] [link](url) #links #tag1 #tag2`
   - Commit entries to journals/YYYY_MM_DD.md

6. **Tag management**
   - Per-user tag collections (max 100)
   - HTML5 datalist autocomplete for mobile
   - Add/remove tags via web UI
   - Tag validation on submission

7. **Web UI**
   - Mobile-first responsive design
   - Large tap targets (44px minimum)
   - Login/Register/Dashboard/Submit/Tags pages
   - Color-coded status badges
   - Inline title editing for needs_title links

8. **Admin CLI**
   - Database initialization
   - User creation and management
   - Invite code generation
   - Failed link retry
   - GitHub connection testing
   - Encryption key generation

9. **Deployment**
   - Multi-stage Dockerfile
   - Docker Compose with volumes
   - Health check endpoints
   - Startup recovery for stale tasks
   - Structured logging with rotation

10. **Documentation**
    - Comprehensive README.md
    - Detailed PLAN.md with architecture
    - Inline code documentation
    - Deployment guides (local, Docker, VPS)

## Next steps to get running

### 1. Install dependencies

```bash
cd /workspaces/logkeep
pip install -r requirements.txt
```

### 2. Configure environment

```bash
# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

# Generate session secret
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Edit .env
cp .env.example .env
nano .env
# Add the generated keys
```

### 3. Initialize database

```bash
python -m src.cli.admin init-db
```

### 4. Create first user

```bash
python -m src.cli.admin create-user
# Follow prompts for username, password, GitHub token, repo details
```

### 5. Generate invite codes

```bash
python -m src.cli.admin create-invite --count 3
```

### 6. Run application

```bash
# Development
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000

# Production (Docker)
docker-compose up -d
```

### 7. Test

Visit http://localhost:8000 and:
- Login with created user
- Submit a test link
- Check dashboard for status
- Verify entry in GitHub Logseq repo

## GitHub Personal Access Token setup

Your users (and you) will need a GitHub PAT:

1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Select scope: **repo** (full control)
4. Copy token (shown only once)
5. Use during registration

## Project file summary

```
logkeep/
├── src/
│   ├── api/              # REST API endpoints
│   │   ├── auth.py       # Login, register, logout
│   │   ├── links.py      # Link submission, history
│   │   ├── tags.py       # Tag CRUD operations
│   │   └── health.py     # Health check
│   ├── services/         # Business logic
│   │   ├── processor.py  # Link processing, title extraction
│   │   └── github.py     # GitHub API integration
│   ├── models/           # Database models
│   │   ├── user.py       # User with encrypted tokens
│   │   ├── link.py       # Link submissions
│   │   └── invite.py     # Invite codes
│   ├── utils/            # Utilities
│   │   ├── database.py   # DB session management
│   │   ├── encryption.py # Fernet token encryption
│   │   ├── auth.py       # JWT, password hashing
│   │   └── logging.py    # Structured logging
│   ├── cli/              # Admin CLI
│   │   └── admin.py      # User/system management
│   ├── templates/        # Jinja2 HTML templates
│   │   ├── base.html
│   │   ├── login.html
│   │   ├── register.html
│   │   ├── dashboard.html
│   │   ├── submit.html
│   │   └── tags.html
│   ├── static/           # CSS, JavaScript
│   │   └── css/style.css # Mobile-first styles
│   └── main.py           # FastAPI application
├── PLAN.md               # Detailed architecture doc
├── README.md             # User documentation
├── requirements.txt      # Python dependencies
├── Dockerfile            # Container build
├── docker-compose.yml    # Multi-container setup
└── .env.example          # Configuration template
```

## Key design decisions

1. **SQLite over PostgreSQL**: Simpler deployment, sufficient for <1000 users
2. **FastAPI BackgroundTasks**: No external queue needed (Redis/Celery)
3. **Datalist autocomplete**: Native HTML5, works on mobile without JS
4. **Fernet encryption**: Standard symmetric encryption, simple key management
5. **Session cookies**: More secure than localStorage, works without JavaScript
6. **Invite-only**: Controlled growth, spam prevention
7. **One user per repo**: Simplifies conflict resolution, clear ownership
8. **Bottom append**: Chronological order in Logseq journals
9. **3 retry limit**: Balance between recovery and infinite loops
10. **Mobile-first**: Primary use case drives design

## Testing checklist

- [ ] User registration with invite code
- [ ] Login/logout flow
- [ ] Submit link with automatic title extraction
- [ ] Submit link with manual title
- [ ] Handle duplicate URL submission
- [ ] Tag creation and deletion
- [ ] Tag selection with autocomplete
- [ ] GitHub commit verification in Logseq repo
- [ ] Status tracking on dashboard
- [ ] Error handling for failed links
- [ ] Title prompt for needs_title status
- [ ] Retry failed links via CLI
- [ ] Test GitHub connection via CLI
- [ ] Mobile UI responsiveness

## Common issues & solutions

### "ENCRYPTION_KEY environment variable not set"
- Run key generation command from README
- Add to .env file
- Restart application

### "No module named 'sqlalchemy'"
- Install dependencies: `pip install -r requirements.txt`

### "Database not initialized"
- Run: `python -m src.cli.admin init-db`

### "Invalid GitHub token"
- Verify PAT has 'repo' scope
- Test: `python -m src.cli.admin test-github USERNAME`
- Regenerate if needed

### Title extraction fails
- This is expected for some sites (paywalls, JavaScript-heavy)
- User will be prompted to provide title manually
- Status will show "needs_title"

## Performance notes

- SQLite handles ~1000 concurrent connections
- Title extraction timeout: 10 seconds
- Background processing: async, non-blocking
- GitHub API rate limit: 5000 requests/hour
- Session expiry: 7 days

## Security considerations

- All passwords bcrypt hashed (never plaintext)
- GitHub tokens Fernet encrypted at rest
- Session cookies HTTP-only, SameSite=Lax
- HTTPS required in production (via nginx)
- Database file permissions: 600
- No CORS (same-origin only)

## Maintenance

### Daily
- Check `logs/app.log` for errors
- Monitor failed link count

### Weekly
- Backup `data/logkeep.db`
- Review user activity

### Monthly
- Rotate logs (automatic with RotatingFileHandler)
- Check disk usage (database, logs)
- Update dependencies

## Future enhancements

See PLAN.md "Future enhancements" section for roadmap:
- AI summarization
- Automatic tag suggestions
- Browser extension
- RSS feed integration
- Mobile app
- Multi-repo support

## Support

- Issues: https://github.com/gperdrizet/logkeep/issues
- Documentation: README.md, PLAN.md
- Code documentation: Inline comments

---

**Status**: ✅ Implementation Complete - Ready for Testing

**Next action**: Install dependencies and test locally
