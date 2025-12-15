# Sudoers Configuration for LogKeep Deployment

This directory contains sudoers configuration files that grant passwordless sudo access for specific deployment commands.

## Installation

**On the VPS (as root or with sudo):**

```bash
# Copy the sudoers file
sudo cp /opt/logkeep/config/sudoers.d/logkeep-deploy /etc/sudoers.d/

# Set correct permissions (required by sudo)
sudo chmod 0440 /etc/sudoers.d/logkeep-deploy

# Validate syntax (important!)
sudo visudo -c

# Test it works
sudo -l  # Should show the commands you can run without password
```

## What This Enables

The configuration allows the `siderealyear` user to run the following commands without a password:

- **Nginx management:**
  - `nginx -t` (test configuration)
  - `systemctl reload/restart/start/stop/status/is-active nginx`

- **Deployment operations:**
  - `ln -sf` (create symlinks for config switching)
  - `readlink` (read symlink targets)
  - `ls -l` (verify symlinks)
  - `cp` (copy nginx configs)

## Security Notes

- Commands are restricted to specific paths and patterns
- No shell access or arbitrary command execution
- Only operations needed for blue/green deployment
- File should be owned by root with mode 0440

## Troubleshooting

If you get "sudo: a password is required":
1. Check file exists: `ls -l /etc/sudoers.d/logkeep-deploy`
2. Check permissions: Should be `-r--r----- root root`
3. Validate syntax: `sudo visudo -c`
4. Check username matches: `whoami` should show `siderealyear`

## Removal

To remove passwordless sudo access:
```bash
sudo rm /etc/sudoers.d/logkeep-deploy
```
