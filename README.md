# LogKeep

Curate content from links using Logseq & GitHub

## Overview

LogKeep is a self-hosted multi-user web service that helps you curate content from links and add them to your Logseq graph stored on GitHub. The primary interface is optimized for smartphone use with minimal typing required.

## Features

- **Mobile-first design** - Large tap targets, minimal typing, optimized for smartphone use
- **Invite-only system** - Controlled user registration with invite codes
- **Tag management** - Personal tag collections with autocomplete
- **Async processing** - Background link processing with automatic title extraction
- **Auto title extraction** - Automatic content extraction with manual fallback
- **Secure** - Encrypted GitHub token storage, session-based authentication
- **Retry logic** - Automatic retry on transient failures (up to 3 attempts)
- **Status tracking** - Real-time visibility into link processing status
- **Admin CLI** - Command-line tools for user and system management

## Quick start

### Prerequisites

- Python 3.12+
- GitHub Personal Access Token with `repo` scope
- Logseq graph in a GitHub repository

### Local development

```bash
# Clone repository
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep

# Create virtual environment
python3.12 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create .env file
cp .env.example .env

# Generate encryption key
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Add to .env as ENCRYPTION_KEY

# Generate session secret
python -c "import secrets; print(secrets.token_urlsafe(32))"
# Add to .env as SESSION_SECRET

# Initialize database
python -m src.cli.admin init-db

# Create first user
python -m src.cli.admin create-user

# Generate invite codes
python -m src.cli.admin create-invite --count 3

# Run development server
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

Visit `http://localhost:8000` in your browser.

### Docker deployment

```bash
# Create .env file with production values
cp .env.example .env
nano .env  # Edit with your configuration

# Build and start
docker-compose up -d

# Initialize database (first time only)
docker-compose exec app python -m src.cli.admin init-db

# Create admin user
docker-compose exec app python -m src.cli.admin create-user

# Generate invite codes
docker-compose exec app python -m src.cli.admin create-invite --count 5

# View logs
docker-compose logs -f app
```

## Configuration

### Environment variables

Create a `.env` file with:

```bash
# Session Security (required)
SESSION_SECRET=your-session-secret-min-32-chars

# Encryption Key (required)
ENCRYPTION_KEY=your-fernet-key-here

# Database
DATABASE_URL=sqlite:///data/logkeep.db

# Limits
MAX_TAGS_PER_USER=1000
MAX_RETRY_COUNT=3

# Logging
LOG_LEVEL=INFO
```

### GitHub setup

Users need a GitHub Personal Access Token:

1. Go to GitHub Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a description: "LogKeep - Logseq Graph Access"
4. Select scope: **repo** (Full control of private repositories)
5. Click "Generate token"
6. Copy token immediately (shown only once)
7. Provide during user registration or creation

## CLI commands

### Database management

```bash
# Initialize database
python -m src.cli.admin init-db

# Generate encryption key
python -m src.cli.admin generate-key
```

### User management

```bash
# Create user
python -m src.cli.admin create-user

# List all users
python -m src.cli.admin list-users

# Activate/deactivate user
python -m src.cli.admin activate-user USERNAME
python -m src.cli.admin deactivate-user USERNAME

# Test GitHub connection
python -m src.cli.admin test-github USERNAME
```

### Invite management

```bash
# Generate invite codes
python -m src.cli.admin create-invite --count 5

# List all invites
python -m src.cli.admin list-invites

# List unused invites only
python -m src.cli.admin list-invites --unused
```

### Tag management

```bash
# Import tags from user's existing journal files
python -m src.cli.admin import-tags USERNAME
```

### Debugging

```bash
# View failed links
python -m src.cli.admin view-failed-links --username alice --limit 10

# Retry failed links
python -m src.cli.admin retry-failed alice
```

## Production deployment (VPS)

### 1. Install Docker

```bash
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo apt install docker-compose
```

### 2. Setup application

```bash
# Clone repository
git clone https://github.com/gperdrizet/logkeep.git
cd logkeep

# Configure environment
cp .env.example .env
nano .env  # Add production secrets

# Start application
docker-compose up -d

# Initialize
docker-compose exec app python -m src.cli.admin init-db
docker-compose exec app python -m src.cli.admin create-user
docker-compose exec app python -m src.cli.admin create-invite --count 5
```

### 3. Nginx reverse proxy

Create `/etc/nginx/sites-available/logkeep`:

```nginx
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

Enable and reload:

```bash
sudo ln -s /etc/nginx/sites-available/logkeep /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. SSL with Certbot

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d logkeep.example.com
```

### 5. Backup setup

Create backup script `/usr/local/bin/backup-logkeep.sh`:

```bash
#!/bin/bash
BACKUP_DIR="/backups/logkeep"
mkdir -p $BACKUP_DIR
cp /path/to/logkeep/data/logkeep.db $BACKUP_DIR/logkeep-$(date +%Y%m%d-%H%M%S).db
find $BACKUP_DIR -name "logkeep-*.db" -mtime +7 -delete
```

Add cron job:

```bash
0 2 * * * /usr/local/bin/backup-logkeep.sh
```

## User workflow

### 1. Register

- Obtain invite code from admin
- Visit `/register`
- Enter username, password, invite code
- Enter GitHub PAT and repository details
- System creates account

### 2. Submit links

- Browse content, find interesting article
- Visit `/submit`
- Paste URL (autofocus for quick entry)
- System extracts title automatically
- Select tags from autocomplete
- Submit → processed asynchronously

### 3. Monitor status

- Dashboard shows recent 50 submissions
- Color-coded status: pending, processing, completed, failed
- View error details for failures
- Provide title manually if extraction fails

### 4. Manage tags

- Visit `/tags`
- View current collection
- Add new tags (up to 100)
- Remove unused tags

### 5. View in Logseq

- Open Logseq graph
- Navigate to today's journal
- See entries at bottom: `- [[Title]] [link](url) #links #tag1 #tag2`

## Logseq entry format

All entries follow this standardized format:

```markdown
- [[Article Title]] [link](https://example.com/article) #links #research #ai
```

- `[[Title]]` - Clickable page reference in Logseq
- `[link](url)` - Original article link
- `#links` - Required tag (always included)
- Additional tags from user's selection

Entries are appended to `journals/YYYY_MM_DD.md` in your GitHub repository.

## Architecture

```
┌─────────────┐
│  Smartphone │
│   Browser   │
└──────┬──────┘
       │ HTTPS
       ▼
┌─────────────┐
│   FastAPI   │
│   Web App   │
├─────────────┤
│  SQLite DB  │
└──────┬──────┘
       │
       ├─► Background Tasks
       │   (Title Extraction)
       │
       └─► GitHub API
           (Commit Entries)
```

## Security

- **Password Hashing**: Bcrypt with appropriate work factor
- **Token Encryption**: Fernet (AES-128-CBC) for GitHub PATs at rest
- **Session Management**: HTTP-only cookies with JWT
- **HTTPS**: Required in production via reverse proxy
- **Invite-Only**: Controlled user registration
- **Database Permissions**: 600 (owner read/write only)

## Troubleshooting

### Database issues

```bash
# Check database file
ls -la data/logkeep.db

# Reinitialize (CAUTION: destroys data)
rm data/logkeep.db
python -m src.cli.admin init-db
```

### GitHub connection issues

```bash
# Test connection
python -m src.cli.admin test-github USERNAME

# Common issues:
# - Invalid token: Regenerate PAT with 'repo' scope
# - Repository not found: Check owner/name spelling
# - No journals/ directory: Will be created on first link
```

### Processing failures

```bash
# View failed links
python -m src.cli.admin view-failed-links --username alice

# Retry failed
python -m src.cli.admin retry-failed alice

# Check logs
tail -f logs/app.log
```

## Development

### Project structure

```
logkeep/
├── src/
│   ├── api/          # API endpoints
│   ├── cli/          # Admin CLI
│   ├── models/       # Database models
│   ├── services/     # Business logic
│   ├── static/       # CSS, JS
│   ├── templates/    # HTML templates
│   ├── utils/        # Utilities
│   └── main.py       # Application entry
├── data/             # SQLite database
├── logs/             # Application logs
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

### Running tests

```bash
# TODO: Add test suite
pytest tests/
```

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - See LICENSE file for details.

## Support

- Issues: https://github.com/gperdrizet/logkeep/issues
- Documentation: See PLAN.md for detailed architecture

## Roadmap

- [ ] AI-powered summarization
- [ ] Automatic tag suggestions
- [ ] Browser extension
- [ ] RSS feed integration
- [ ] Mobile native app
- [ ] Multi-repository support
