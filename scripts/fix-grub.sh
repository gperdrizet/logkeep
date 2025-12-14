#!/bin/bash
# Fix GRUB package configuration issue on VPS

echo "Removing GRUB postinst scripts..."
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.preinst
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.prerm
sudo rm -f /var/lib/dpkg/info/grub-efi-amd64-signed.postrm

echo "Creating placeholder files..."
sudo touch /var/lib/dpkg/info/grub-efi-amd64-signed.list
sudo touch /var/lib/dpkg/info/grub-efi-amd64-signed.md5sums

echo "Configuring packages..."
sudo dpkg --configure -a

echo "Done! GRUB issue should be resolved."
echo "Now run: sudo bash setup-vps-skip-upgrade.sh"
