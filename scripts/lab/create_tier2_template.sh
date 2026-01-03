#!/bin/bash
set -e

# Configuration
PROXMOX_HOST="${PROXMOX_HOST:-pve}"
SSH_USER="${SSH_USER:-ci}"
SSH_OPTS="${SSH_OPTS:--o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o CheckHostIP=no -o UserKnownHostsFile=/dev/null -o GlobalKnownHostsFile=/dev/null}"
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

# Helpers to run commands on host; run local if targeting this host
pve_exec_user() {
    local target="$PROXMOX_HOST"
    local self_host self_fqdn
    self_host="$(hostname -s)"
    self_fqdn="$(hostname -f 2>/dev/null || true)"
    local path_prefix="PATH=/usr/sbin:/sbin:/usr/bin:/bin:$PATH"

    if [ "$target" = "localhost" ] || [ "$target" = "127.0.0.1" ] || [ "$target" = "$self_host" ] || { [ -n "$self_fqdn" ] && [ "$target" = "$self_fqdn" ]; }; then
        env $path_prefix bash -lc "$*"
    else
        ssh $SSH_OPTS "$SSH_USER@$target" "env $path_prefix bash -lc '$*'"
    fi
}

pve_exec_root() {
    local target="$PROXMOX_HOST"
    local self_host self_fqdn
    self_host="$(hostname -s)"
    self_fqdn="$(hostname -f 2>/dev/null || true)"
    local sudo_path="PATH=/usr/sbin:/sbin:/usr/bin:/bin:$PATH"

    if [ "$target" = "localhost" ] || [ "$target" = "127.0.0.1" ] || [ "$target" = "$self_host" ] || { [ -n "$self_fqdn" ] && [ "$target" = "$self_fqdn" ]; }; then
        sudo -n env $sudo_path "$@"
    else
        ssh $SSH_OPTS "$SSH_USER@$target" "sudo -n env $sudo_path $*"
    fi
}

log "Checking if VM $VMID exists..."
if pve_exec_root qm status "$VMID" >/dev/null 2>&1; then
    log "VM $VMID exists; destroying it for fresh template build..."
    pve_exec_root qm stop "$VMID" --skiplock >/dev/null 2>&1 || true
    if ! pve_exec_root qm destroy "$VMID" --purge >/dev/null 2>&1; then
        echo "Failed to destroy existing VM $VMID; manual cleanup required."
        exit 1
    fi
fi

log "Uploading SSH Key..."
pve_exec_user "printf '%s\\n' \"$SSH_KEY\" > /tmp/lab.pub"

log "Downloading Debian 13 Cloud Image..."
pve_exec_user "wget -qO /tmp/debian-13.qcow2 \"$IMAGE_URL\""

log "Creating VM $VMID..."
pve_exec_root qm create "$VMID" --name "$TEMPLATE_NAME" --memory 2048 --cores 2 --net0 virtio,bridge="$BRIDGE"

log "Importing Disk..."
pve_exec_root qm importdisk "$VMID" /tmp/debian-13.qcow2 "$STORAGE"

log "Configuring VM Hardware..."
pve_exec_root qm set "$VMID" --scsihw virtio-scsi-pci --scsi0 "$STORAGE:vm-$VMID-disk-0"

log "Resizing Disk..."
pve_exec_root qm resize "$VMID" scsi0 32G
pve_exec_root qm set "$VMID" --ide2 "$STORAGE:cloudinit"
pve_exec_root qm set "$VMID" --boot c --bootdisk scsi0
pve_exec_root qm set "$VMID" --serial0 socket --vga serial0
pve_exec_root qm set "$VMID" --agent enabled=1

# Configure Cloud-Init User and Key
pve_exec_root qm set "$VMID" --ciuser ansible --sshkeys /tmp/lab.pub

# Add ManagedBy tag for safety (in description)
pve_exec_root qm set "$VMID" --description 'ManagedBy=019a'

log "Converting to Template..."
pve_exec_root qm template "$VMID"

log "Cleaning up..."
pve_exec_user "rm -f /tmp/debian-13.qcow2 /tmp/lab.pub"

log "Done! Template $VMID created."
