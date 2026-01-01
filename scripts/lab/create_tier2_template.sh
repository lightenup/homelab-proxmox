#!/bin/bash
set -e

# Configuration
PROXMOX_HOST="192.168.1.112"
SSH_USER="root"
VMID=9002
TEMPLATE_NAME="lab-tpl-debian-13-tier2"
IMAGE_URL="https://cloud.debian.org/images/cloud/trixie/daily/latest/debian-13-generic-amd64-daily.qcow2"
STORAGE="local-lvm" # Adjust if using ZFS (e.g., local-zfs)
BRIDGE="vmbr99"
SSH_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIO4xtULNL2RD45yGIFiOWsRmWDkza6LZsCURRoJJiY04 jacobsen.andreas@gmail.com"

# Colors
GREEN='\033[0;32m'
NC='\033[0m'

log() { echo -e "${GREEN}[INFO]${NC} $1"; }

# Helper to run commands on host
pve_exec() {
    ssh -o BatchMode=yes -o ConnectTimeout=10 "$SSH_USER@$PROXMOX_HOST" "$@"
}

log "Checking if VM $VMID exists..."
if pve_exec "qm status $VMID" >/dev/null 2>&1; then
    echo "VM $VMID already exists. Please remove it manually if you want to recreate it."
    exit 1
fi

log "Uploading SSH Key..."
pve_exec "echo '$SSH_KEY' > /tmp/lab.pub"

log "Downloading Debian 13 Cloud Image..."
pve_exec "wget -qO /tmp/debian-13.qcow2 $IMAGE_URL"

log "Creating VM $VMID..."
pve_exec "qm create $VMID --name $TEMPLATE_NAME --memory 2048 --cores 2 --net0 virtio,bridge=$BRIDGE"

log "Importing Disk..."
pve_exec "qm importdisk $VMID /tmp/debian-13.qcow2 $STORAGE"

log "Configuring VM Hardware..."
pve_exec "qm set $VMID --scsihw virtio-scsi-pci --scsi0 $STORAGE:vm-$VMID-disk-0"

log "Resizing Disk..."
pve_exec "qm resize $VMID scsi0 32G"
pve_exec "qm set $VMID --ide2 $STORAGE:cloudinit"
pve_exec "qm set $VMID --boot c --bootdisk scsi0"
pve_exec "qm set $VMID --serial0 socket --vga serial0"
pve_exec "qm set $VMID --agent enabled=1"

# Configure Cloud-Init User and Key
pve_exec "qm set $VMID --ciuser ansible --sshkeys /tmp/lab.pub"

# Add ManagedBy tag for safety (in description)
pve_exec "qm set $VMID --description 'ManagedBy=019a'"

log "Converting to Template..."
pve_exec "qm template $VMID"

log "Cleaning up..."
pve_exec "rm /tmp/debian-13.qcow2 /tmp/lab.pub"

log "Done! Template $VMID created."
