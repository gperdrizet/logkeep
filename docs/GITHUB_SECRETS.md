# GitHub Secrets Configuration

The GitHub Actions workflows require these secrets to be configured in your repository settings.

## Required Secrets

Go to: **Repository Settings → Secrets and variables → Actions → New repository secret**

### 1. Docker Hub Credentials

**`DOCKER_USERNAME`**
- Your Docker Hub username
- Example: `gperdrizet`

**`DOCKER_PASSWORD`**
- Docker Hub access token (not your password!)
- Generate at: https://hub.docker.com/settings/security
- Click "New Access Token"
- Give it a name like "GitHub Actions LogKeep"
- Copy the token and save it as this secret

### 2. VPS Access

**`VPS_HOST`**
- Your VPS hostname or IP address
- Example: `vps123.ionos.com` or `192.168.1.100`

**`VPS_USER`**
- SSH username for your VPS
- Example: `root` or `ubuntu` or your custom user

**`VPS_SSH_PRIVATE_KEY`**
- Your SSH private key for accessing the VPS
- Generate if needed:
  ```bash
  # On your local machine
  ssh-keygen -t ed25519 -C "github-actions-logkeep" -f ~/.ssh/logkeep-deploy
  
  # Copy public key to VPS
  ssh-copy-id -i ~/.ssh/logkeep-deploy.pub -p 44441 user@vps-host
  
  # Copy private key content for GitHub secret
  cat ~/.ssh/logkeep-deploy
  ```
- Paste the **entire private key** including:
  ```
  -----BEGIN OPENSSH PRIVATE KEY-----
  ...content...
  -----END OPENSSH PRIVATE KEY-----
  ```

## Verification

After adding secrets, test by:

1. **Manual workflow dispatch:**
   - Go to Actions → Deploy to Production → Run workflow

2. **Check the build step:**
   - Should successfully login to Docker Hub
   - Should build and push image

3. **Check the deploy step:**
   - Should SSH to VPS successfully
   - Should pull updated code
   - Should run deployment script

## Troubleshooting

### Build fails with "unauthorized: authentication required"
- Check `DOCKER_USERNAME` and `DOCKER_PASSWORD`
- Verify Docker Hub token is valid
- Ensure token has write permissions

### Deploy fails with "Permission denied (publickey)"
- Check `VPS_SSH_PRIVATE_KEY` is complete (including header/footer)
- Verify public key is in VPS `~/.ssh/authorized_keys`
- Test SSH manually: `ssh -i ~/.ssh/logkeep-deploy -p 44441 user@vps`

### Deploy fails with "git: command not found" or similar
- SSH to VPS and verify git is installed
- Ensure /opt/logkeep directory exists and is a git repository
- Check VPS user has permissions to /opt/logkeep

## Current Workflow Status

After fixing the workflow, it will:

1. ✅ **Build** - Build Docker image with new code
2. ✅ **Push** - Push to Docker Hub
3. ✅ **Sync** - Update code on VPS
4. ✅ **Deploy** - Run blue/green deployment
5. ✅ **Verify** - Check health endpoint
6. ✅ **Rollback** - Auto-rollback on failure

## Environment Setup

The workflows use GitHub Environments for additional controls:

- **production** - Requires approval before deployment (optional)
- **staging** - Auto-deploys from dev branch

To configure environments:
1. Go to **Repository Settings → Environments**
2. Add "production" environment
3. (Optional) Enable "Required reviewers" for production deploys
