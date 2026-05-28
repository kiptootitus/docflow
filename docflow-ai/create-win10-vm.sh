#!/bin/bash
# ================================================
# VirtualBox Windows 10 Auto Setup (FIXED)
# ================================================

VM_NAME="win10"
RAM="8192"
CPUS="4"
DISK_SIZE="80000"   # 80GB in MB

ISO_PATH="$HOME/Documents/Win10_22H2_English_x64v1.iso"
VIRTIO_ISO="$HOME/VMs/virtio-win.iso"

VM_DIR="$HOME/VirtualBox VMs/$VM_NAME"
DISK_PATH="$VM_DIR/${VM_NAME}.vdi"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}=== VirtualBox Windows 10 VM Setup ===${NC}"

mkdir -p "$VM_DIR"

# Check VirtualBox
if ! command -v VBoxManage &> /dev/null; then
    echo -e "${RED}VirtualBox not installed!${NC}"
    exit 1
fi

# Validate ISO
if [[ ! -f "$ISO_PATH" ]]; then
    echo -e "${RED}Windows ISO not found at:${NC} $ISO_PATH"
    exit 1
fi

echo -e "${GREEN}Using ISO:${NC} $ISO_PATH"

# Remove old VM if exists
VBoxManage unregistervm "$VM_NAME" --delete 2>/dev/null || true

# Create VM
VBoxManage createvm \
  --name "$VM_NAME" \
  --ostype "Windows10_64" \
  --register

# Configure VM
VBoxManage modifyvm "$VM_NAME" \
  --memory "$RAM" \
  --cpus "$CPUS" \
  --vram 128 \
  --graphicscontroller vmsvga \
  --boot1 dvd \
  --boot2 disk \
  --boot3 none \
  --boot4 none \
  --firmware efi \
  --ioapic on \
  --nic1 nat \
  --mouse usbtablet

# Create disk if missing
if [[ ! -f "$DISK_PATH" ]]; then
    echo -e "${YELLOW}Creating disk...${NC}"
    VBoxManage createhd --filename "$DISK_PATH" --size "$DISK_SIZE"
fi

# Storage controller
VBoxManage storagectl "$VM_NAME" \
  --name "SATA Controller" \
  --add sata \
  --controller IntelAhci

# Attach disk
VBoxManage storageattach "$VM_NAME" \
  --storagectl "SATA Controller" \
  --port 0 \
  --device 0 \
  --type hdd \
  --medium "$DISK_PATH"

# Attach Windows ISO
VBoxManage storageattach "$VM_NAME" \
  --storagectl "SATA Controller" \
  --port 1 \
  --device 0 \
  --type dvddrive \
  --medium "$ISO_PATH"

# Optional VirtIO ISO
if [[ -f "$VIRTIO_ISO" ]]; then
    VBoxManage storageattach "$VM_NAME" \
      --storagectl "SATA Controller" \
      --port 2 \
      --device 0 \
      --type dvddrive \
      --medium "$VIRTIO_ISO"
    echo -e "${GREEN}VirtIO attached${NC}"
fi

echo -e "${GREEN}Starting VM...${NC}"

VBoxManage startvm "$VM_NAME" --type gui