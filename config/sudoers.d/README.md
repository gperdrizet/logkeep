# Sudoers Configuration for LogKeep Deployment

This directory contains sudoers configuration used for controlled passwordless administrative commands on the VPS.

## Installation

Run on the VPS:

```bash
sudo cp /opt/logkeep/config/sudoers.d/logkeep-deploy /etc/sudoers.d/
sudo chmod 0440 /etc/sudoers.d/logkeep-deploy
sudo visudo -c
sudo -l
```

## Scope

The policy is limited to deployment-related nginx and file-management operations, such as:

- `nginx -t`
- `systemctl reload/restart/start/stop/status/is-active nginx`
- controlled `cp`, `ln -sf`, `readlink`, and `ls -l` operations used by deployment scripts

## Security Requirements

- file owner: `root:root`
- mode: `0440`
- no unrestricted shell commands

## Troubleshooting

If sudo still prompts for a password:

1. Confirm file path exists
2. Confirm mode is `0440`
3. Re-run `sudo visudo -c`
4. Confirm expected SSH user with `whoami`
