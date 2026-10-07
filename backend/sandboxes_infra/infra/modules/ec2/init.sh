#!/usr/bin/env bash

sudo apt update && sudo apt upgrade -y
sudo apt install -y zstd

# install-firecracker.sh
# Downloads the latest Firecracker release and installs `firecracker` + `jailer`
# into /usr/local/bin. Works on Linux x86_64 and aarch64.
#
# Usage:
#   chmod +x install-firecracker.sh
#   ./install-firecracker.sh                 # latest stable
#   ./install-firecracker.sh v1.15.1         # pin a version

set -euo pipefail

# --- resolve version ----------------------------------------------------------
if [[ $# -ge 1 ]]; then
  VERSION="$1"
else
  # follow the /releases/latest redirect to learn the tag, no jq needed
  VERSION=$(basename "$(curl -fsSLI -o /dev/null -w '%{url_effective}' \
    https://github.com/firecracker-microvm/firecracker/releases/latest)")
fi

ARCH="$(uname -m)"
case "$ARCH" in
  x86_64|aarch64) ;;
  *) echo "unsupported arch: $ARCH (need x86_64 or aarch64)" >&2; exit 1 ;;
esac

TARBALL="firecracker-${VERSION}-${ARCH}.tgz"
URL="https://github.com/firecracker-microvm/firecracker/releases/download/${VERSION}/${TARBALL}"

echo ">> installing Firecracker ${VERSION} for ${ARCH}"
echo ">> source: ${URL}"

# --- download into a tempdir --------------------------------------------------
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

curl -fsSL -o "${TMP}/${TARBALL}" "${URL}"
tar -xzf "${TMP}/${TARBALL}" -C "${TMP}"

EXTRACTED="${TMP}/release-${VERSION}-${ARCH}"
[[ -d "$EXTRACTED" ]] || { echo "extraction failed: ${EXTRACTED} not found" >&2; exit 1; }

# --- install binaries ---------------------------------------------------------
SUDO=""
[[ $EUID -ne 0 ]] && SUDO="sudo"

$SUDO install -m 0755 "${EXTRACTED}/firecracker-${VERSION}-${ARCH}" /usr/local/bin/firecracker
$SUDO install -m 0755 "${EXTRACTED}/jailer-${VERSION}-${ARCH}"      /usr/local/bin/jailer

echo
echo ">> installed:"
firecracker --version
jailer --version

# --- KVM access setup ---------------------------------------------------------
echo
TARGET_USER="ubuntu"

if [[ ! -e /dev/kvm ]]; then
  echo ">> warning: /dev/kvm does not exist — KVM module not loaded or no virt support"
  echo "   check: lsmod | grep kvm  &&  egrep -c '(vmx|svm)' /proc/cpuinfo"
else
  echo ">> configuring /dev/kvm access for ${TARGET_USER}"

  $SUDO groupadd -f kvm
  $SUDO chgrp kvm /dev/kvm
  $SUDO chmod 0660 /dev/kvm

  if id -u "$TARGET_USER" >/dev/null 2>&1; then
    $SUDO usermod -aG kvm "$TARGET_USER"
    echo "   added ${TARGET_USER} to the kvm group"
  else
    echo "   warning: user ${TARGET_USER} does not exist yet"
  fi

  $SUDO install -m 0644 /dev/stdin /etc/udev/rules.d/60-kvm.rules <<'EOF'
KERNEL=="kvm", GROUP="kvm", MODE="0660"
EOF
  $SUDO udevadm control --reload-rules || true
  $SUDO udevadm trigger --subsystem-match=misc --sysname-match=kvm || true

  echo ">> /dev/kvm permissions:"
  ls -l /dev/kvm
  echo ">> restart the VM manager after this script so ${TARGET_USER}'s kvm group membership is active"
fi