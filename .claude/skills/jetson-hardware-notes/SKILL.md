---
name: jetson-hardware-notes
description: Use when working on Jetson Orin Nano hardware for this repo (autonomous-fleet-testbed) — flashing/provisioning, power modes, SSH/mDNS, HIL setup, or any Jetson-specific gotcha. Migrated from the root CLAUDE.md by /doctor on 2026-07-27.
---

# Jetson Orin Nano Gotchas (Session 14+)

Full step-by-step runbook: `docs/runbooks/JetsonInstallSession14.md`. **Parts 1–9 done as
of 2026-07-13** — Part 9's NVMe FRESH INSTALL executed: headless SDK Manager recovery
flash to NVMe (~12 min), re-provisioned end-to-end from the runbook (Part 9 step 11
inlines all of it), NVMe-at-25W baselines recorded (Part 7 table: colcon 5.312s ≈ SD tie;
docker pull 1m40s = 2.5× vs SD; cold arm64 CI build 568s ≈ SD 585s), runner re-registered
and **proven by a full 8-job-green CI cycle (run 29301726080)**. **Session 14 is COMPLETE
(2026-07-14):** step 14's closeout + `Mike@`→`mike@` doc sweep done, and step 13c — the
manual HIL run on the NVMe install — **passed first-attempt 2026-07-14** (multicast DDS
across the link, mission PASS, photo + `hil_jetson` telemetry row on the Jetson; results
in the runbook at 13c). **Session 16 SIGNED OFF 2026-07-19** (`stage-4-hil` live, Mission 2
merged, GUI day + clean CI run 29697469463) — next: Session 17 scoping (see Release1Todo).
Confirmed-for-this-board state, not guesses: username **`mike`** (lowercase, matches the
workstation — the SD era's capital-M `Mike` is gone; old docs saying `Mike@` predate
2026-07-13), hostname **`jetson`** — **`ssh mike@jetson.local` works via mDNS** (needed
the post-hostname reboot; fresh installs also ship NO `127.0.1.1` line in `/etc/hosts` —
one was added; don't put a static entry on the workstation, the DHCP lease moves). IP
still `10.42.0.217` (lease — re-check with `ip neigh show dev enp6s0`), rootfs on NVMe
`/dev/nvme0n1p1` (456G, 421G free), GUI off (`multi-user.target`, idle RAM 433 MB), CUDA
still intentionally absent (OS-only flash). The microSD rollback was released 2026-07-15
(stage-4-hil 3×-green condition met). GHCR pulls on the Jetson need
`gh auth refresh -s read:packages` then `gh auth token | docker login ghcr.io -u sdfinn
--password-stdin` (the image is private; gh's default scopes lack packages).
- **Power mode: pinned to 25W (`sudo nvpmodel -m 1`) on 2026-07-12.** Orin Nano Super modes:
  0=15W (the out-of-box state we found), 1=25W, 2=MAXN_SUPER. `sudo nvpmodel -q` to query,
  `-p --verbose` to list, `-m <id>` to set; the chosen mode **persists across reboots** via
  `/var/lib/nvpmodel/status`. The SD-era build baselines predate the pin (mode unrecorded
  — flagged historical in the Part 7 table); **NVMe-at-25W is the go-forward reference,
  recorded 2026-07-13**. The pin was re-applied on the NVMe install (Part 9 step 10 ✅).
  `sudo jetson_clocks` additionally locks clocks at the mode's max but does NOT persist —
  suitable as a per-job CI step, not a set-and-forget.
- **JetPack 7.2 removed the microSD card image.** The old "flash an SD image with Etcher and
  boot it" workflow no longer exists. Flash via **SDK Manager** over USB-C in recovery mode
  (what we used), or the Jetson-ISO-on-USB installer as a fallback (needs a monitor+keyboard).
- **NVIDIA SDK Manager's "Download for Ubuntu" button is a login-gated browser redirect with
  no stable URL** — not curl/wget-able directly. Use the apt network-install method instead:
  ```bash
  wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
  sudo dpkg -i cuda-keyring_1.1-1_all.deb
  sudo apt-get update && sudo apt-get -y install sdkmanager
  ```
- **Recovery mode:** short `FC REC`↔`GND` on the J14 header while applying DC power, hold ~2–3s
  after power comes on, then release. Verify from the host with `lsusb | grep -i nvidia` →
  expect `0955:7523 NVIDIA Corp. APX`. A charge-only USB-C cable (no data lines) is the #1
  cause of recovery mode not being detected.
- **SDK Manager's OEM pre-config screen isn't guaranteed to ask for all three fields.** It
  prompted for username/password but silently skipped hostname on this flash — don't assume
  "it asked for some fields" means "it asked for all of them"; check `hostname` after first
  boot before relying on `<hostname>.local` mDNS (it won't resolve if hostname wasn't set).
- **`ssh-copy-id` requires an existing local SSH keypair** — `ssh-keygen -t ed25519` first if
  `~/.ssh/*.pub` doesn't exist, or it fails with `ERROR: No identities found`.
- **`ping` failing after the shared-Ethernet setup doesn't necessarily mean NAT is broken.**
  Confirmed on this network: `ping nvidia.com` gets 100% packet loss even with `ip_forward=1`,
  `ufw` inactive, and a correct `MASQUERADE` rule with live, incrementing packet counters
  (`sudo iptables -t nat -L POSTROUTING -n -v`). The network silently drops outbound ICMP;
  `curl -I http://nvidia.com` or `curl -s ifconfig.me` from the Jetson is the real test.
- **Target Components (CUDA/cuDNN/TensorRT) are worth skipping on the first flash.** Uncheck
  them in SDK Manager for a clean OS-only flash, confirm boot, then add later with
  `sudo apt install nvidia-jetpack` if on-device GPU inference is ever needed (L4T apt sources
  are already present post-flash — no re-flash required). `nvcc: command not found` and empty
  `dpkg-query --show nvidia-jetpack` are expected in this state, not a problem.
