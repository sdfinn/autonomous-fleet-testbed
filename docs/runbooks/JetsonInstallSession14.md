# Jetson Orin Nano Super — Install & CI Runbook (Session 14)

> **What this is:** a do-it-yourself, end-to-end runbook to take the Jetson Orin Nano Super
> Developer Kit from a sealed box to a fully working ROS2 Jazzy node that is also a
> self-hosted CI runner for this repo. Written to be followed step by step on flash day.
>
> **Decisions baked in (confirmed 2026-07-08):**
> - **OS/JetPack:** Ubuntu 24.04 + **JetPack 7.2** (Jetson Linux **L4T r39.2**). One distro
>   end to end — x86 workstation (24.04/Jazzy), stage-2 Docker (`ros:jazzy`), Jetson
>   (24.04/Jazzy). **No Humble anywhere.**
> - **Flash method:** **NVIDIA SDK Manager** from your Ubuntu 24.04 x86 workstation, over
>   USB-C, Jetson in recovery mode. (JetPack 7.2 **removed the microSD card image** — the old
>   "burn an image with Etcher and boot it" workflow no longer exists. See box below.)
> - **Kit:** Orin Nano **Super** Developer Kit (module P3767-0005 + carrier P3768-0000).
> - **First boot:** **headless-first** — SDK Manager pre-sets your username/password/hostname
>   so the board comes up with SSH ready and no OEM wizard. Monitor + keyboard kept as a
>   fallback for troubleshooting only.
> - **Networking:** **direct Ethernet from Jetson → workstation.** Your workstation is on
>   **Wi-Fi** for its own internet, and its Ethernet port is free — so we share the Wi-Fi
>   uplink to the Jetson over Ethernet with NetworkManager (`ipv4.method=shared`).
> - **Storage:** **microSD first** (record a baseline), **then migrate to NVMe SSD** and
>   re-record the same numbers.

> ### ⚠️ Why there is no SD-card image anymore
> Every older Orin Nano tutorial says "download the SD-card image, flash it with Balena
> Etcher, boot it." **That path was removed in JetPack 7.2.** NVIDIA now ships either (a) a
> unified **Jetson ISO** you boot from a USB stick, or (b) **SDK Manager**, which streams the
> OS to the board over USB-C while it sits in recovery mode. We use **SDK Manager** because
> you already have an Ubuntu 24.04 x86 host, it updates the board firmware for you, and it can
> pre-seed the login account so first boot is genuinely headless. If you ever hit a wall with
> SDK Manager, the ISO-on-USB method is the documented fallback (needs a monitor+keyboard on
> the Jetson) — see Part 3, "If SDK Manager won't cooperate."

---

## Table of contents
- [Part 0 — Before you start](#part-0--before-you-start)
- [Part 1 — Unpack & inspect the hardware](#part-1--unpack--inspect-the-hardware)
- [Part 2 — Prepare the x86 workstation (host)](#part-2--prepare-the-x86-workstation-host)
- [Part 3 — Flash JetPack 7.2 to microSD (SDK Manager)](#part-3--flash-jetpack-72-to-microsd-sdk-manager)
- [Part 4 — Network & headless remote session](#part-4--network--headless-remote-session)
- [Part 5 — Smoke tests](#part-5--smoke-tests)
- [Part 6 — Install ROS2 Jazzy](#part-6--install-ros2-jazzy)
- [Part 7 — Native build + record the microSD baseline](#part-7--native-build--record-the-microsd-baseline)
- [Part 8 — Add the Jetson as a self-hosted CI runner](#part-8--add-the-jetson-as-a-self-hosted-ci-runner)
- [Part 9 — Migrate microSD → NVMe SSD](#part-9--migrate-microsd--nvme-ssd)
- [Part 10 — Close out Session 14](#part-10--close-out-session-14)

---

## Part 0 — Before you start

### Vocabulary (so the rest of the doc reads cleanly)
- **Host / workstation** — your Ubuntu 24.04 x86 desktop (the RTX 5080 box). Runs SDK Manager.
- **Target** — the Jetson.
- **Recovery mode (APX / "Force Recovery")** — a boot mode where the Jetson presents itself
  to the host over USB-C as a flashable device instead of booting an OS. This is how SDK
  Manager writes to it. You enter it by holding down the **FC REC** (force recovery) condition
  while powering on.
- **L4T (Linux for Tegra) / Jetson Linux** — NVIDIA's Ubuntu-based OS for Jetson. JetPack =
  L4T + CUDA/cuDNN/TensorRT + tools. JetPack 7.2 == L4T r39.2 == Ubuntu 24.04.
- **QSPI / UEFI firmware** — the board's bootloader firmware, stored on the module itself
  (not on your microSD/NVMe). SDK Manager updates this as part of flashing.

### Bill of materials — check you have all of this
- [x] Jetson Orin Nano Super Developer Kit (module + carrier board)
- [x] Included DC power supply (**use the real supply, not a random USB-C charger** — sustained
      loads want the full wattage)
- [x] **USB-C cable that carries data** (many cables are charge-only — a charge-only cable is
      the #1 cause of "recovery mode not detected"). Connects Jetson ⇄ workstation.
- [x] microSD card, **64 GB or larger**, decent brand (Session 7 baseline lives here)
- [ ] NVMe M.2 2280 SSD (for Part 9 — the Super kit usually ships with the M.2 slot empty)
- [ ] Ethernet cable (Jetson → workstation directly)
- [ ] Jumper wire / female-female jumper OR a paperclip (to short the recovery header)
- [ ] (Fallback only) Monitor with DisplayPort input + DP cable + USB keyboard
- [ ] An **NVIDIA Developer account** (free) — SDK Manager makes you log in.

### Read the printed Quick Start card in the box
The box includes a printed quick-start card with a **diagram of the carrier board**. Keep it
next to you — you'll use it in Part 1 and Part 3 to confirm the exact location and pin
numbering of the recovery header, because silk-screen numbering has shifted between carrier
revisions and shorting the *wrong* pins is the one genuinely risky step in this whole process.

---

## Part 1 — Unpack & inspect the hardware

**Why first:** you want to physically locate five things before any cable goes in, so that
every later "plug X into Y" step is muscle memory, not a hunt.

- [x] Unpack the kit. Set the carrier board on something non-conductive (the antistatic bag or
      the cardboard tray — **not** bare metal or carpet).
- [x ] Locate and mentally label, using the printed card:
  1. **DC barrel jack** — power in.
  2. **USB-C port** — this is the port used for recovery-mode flashing to the host.
     (On the carrier this is the dedicated device-mode USB-C. Confirm on the card which
     USB-C is the "flashing" port if there is more than one.)
  3. **microSD slot** — usually on the **underside of the module**, not the carrier. Slide the
     card in now (it can live there through flashing; SDK Manager writes to it).
  4. **M.2 Key-M (2280) slot** — for the NVMe SSD (Part 9). Leave empty for now.
  5. **Recovery / button header (J14)** and any physical **FC REC** button. On the Super
     carrier there is a small header near the DC jack. **On the printed card, find the pin
     labeled `FC REC` (force recovery) and the adjacent `GND`.** These are the two you'll short
     in Part 3. Write down their pin numbers now.
- [x] Optional visual firmware clue: a brand-new **Super** kit ships with recent firmware, so
      the SDK-Manager path should work directly. We'll verify the firmware is new enough
      implicitly — if SDK Manager flashes JetPack 7.2 without complaint, the firmware was fine.
      (If it refuses, see Part 3's firmware note.)

> **Explain — why the microSD is on the module:** the Orin Nano *module* (the SODIMM-like card)
> carries the microSD slot; the *carrier* carries the connectors. This trips people up because
> they look on the carrier edge and don't find it.

---

## Part 2 — Prepare the x86 workstation (host)

**Why:** SDK Manager is host software. Everything in this part happens on your desktop, before
the Jetson is even powered.

- [x] Confirm the host OS is 24.04 (it is — this is your dev box):
  ```bash
  cat /etc/os-release   # expect: VERSION="24.04..."
  ```
- [ ] Install **SDK Manager** via NVIDIA's apt repo (the page's "Download for Ubuntu" button is
      a login-gated browser redirect with no stable URL — this network-install method is the
      copy-paste-able alternative and needs no login):
  ```bash
  wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2404/x86_64/cuda-keyring_1.1-1_all.deb
  sudo dpkg -i cuda-keyring_1.1-1_all.deb
  sudo apt-get update
  sudo apt-get -y install sdkmanager
  ```
- [x] Launch it once to confirm it opens and log in with your NVIDIA Developer account:
  ```bash
  sdkmanager
  ```
- [ ] Verify you have a **data-capable USB-C cable**. Easiest test: later, in recovery mode,
      `lsusb` must show the NVIDIA APX device (Part 3). If it doesn't, suspect the cable first.
- [ ] Identify your workstation's **free Ethernet interface name** — you'll need it in Part 4:
  ```bash
  ip -br link        # list interfaces; the wired one is usually enpXsY / enoX, state DOWN
  nmcli device status
  ```
  Note the Ethernet device name (e.g. `enp5s0`). Your Wi-Fi (e.g. `wlp...`) stays as-is and
  keeps the workstation online; we only touch the Ethernet port.

  IT IS enp6s0  

---

## Part 3 — Flash JetPack 7.2 to microSD (SDK Manager)

> **This is the one part with a physically risky step (shorting header pins). Go slowly and
> confirm pin numbers against the printed card.**

### 3.1 Put the Jetson into recovery mode
- [x] Make sure the Jetson is **fully powered off and unplugged** from DC. Wait ~10 s for
      capacitors to discharge.
- [x] Insert the **microSD** into the module slot (if not already in from Part 1).
- [x] Connect the **USB-C cable** from the Jetson's device-mode USB-C port to a USB port on the
      workstation.
- [x] **Short the recovery pins:** using a jumper/paperclip, bridge **`FC REC` to `GND`** on the
      J14 header (the two pins you noted in Part 1). Hold the short.
- [x] **While holding the short**, plug the **DC power** back in. Keep the short for ~2–3 s
      after power comes on, then remove the jumper.
  > Some Super carriers have a labeled **FC REC push-button** instead — if so, the sequence is:
  > hold FC REC, apply power, keep holding 2–3 s, release. Same idea, no jumper.
- [x] Verify from the **workstation** that the board enumerated in recovery mode:
  ```bash
  lsusb | grep -i nvidia
  # expect a line like: ID 0955:7523 NVIDIA Corp. APX
  ```
  If you see `0955:7523`, you're in recovery mode. If nothing shows: unplug, wait, re-seat the
  USB-C cable (try a known-good data cable), and retry the short-then-power sequence.

### 3.2 Flash with SDK Manager
- [x] In SDK Manager (already logged in):
  - **Step 1 — Product category / Target:** it should auto-detect the connected board. Select
    **Jetson Orin Nano [8GB Developer Kit]**. Confirm module **P3767-0005** / carrier
    **P3768-0000** if it asks.
  - **SDK version:** choose **JetPack 7.2**. If 7.2 isn't offered, update SDK Manager itself
    (older SDK Manager builds don't list new JetPack releases) — close it, `sudo apt update &&
    sudo apt install --only-upgrade sdkmanager`, relaunch.
  - **Uncheck "Host Components"** (you don't need CUDA on the x86 host for this).
  - **Target Components:** for the first flash, do **OS image only** — uncheck the SDK
    components (CUDA/TensorRT/etc). Flash the OS, confirm it boots, *then* add components.
    This keeps the first flash fast and isolates "did the OS flash work?" from "did the SDK
    packages install?"
- [x] **Storage device** (critical): select **microSD** as the target runtime device — **not**
      NVMe, not eMMC, for this first pass. (You migrate to NVMe in Part 9.)
  > **If microSD is *not* offered as a target device** in your SDK Manager build: SDK Manager
  > on some releases only targets NVMe/USB. In that case, either (a) use the **Jetson ISO on
  > USB** fallback below to install to microSD, or (b) accept flashing straight to **NVMe now**
  > and treat NVMe as your baseline (you were going there anyway — you'd just lose the
  > microSD-vs-NVMe comparison). Decide based on how much you care about the SD baseline number.
- [x] **Pre-configure the OS account (this is what makes first boot headless):** SDK Manager
      will offer a **"Pre-Config" / manual OEM setup** option before flashing. Fill in:
  - Username (e.g. `mike`)
  - Password
  - **Hostname** — set something memorable, e.g. `jetson-orin` (you'll use `jetson-orin.local`)
  - Timezone / locale / keyboard
  > Skipping this leaves the board waiting at the interactive **OEM setup wizard** on first
  > boot, which needs a monitor+keyboard. Filling it in = the board boots straight to a
  > login-ready, SSH-able system.
- [x] Start the flash. **OS-only flash to microSD ≈ 20–30 min.** Do not disturb the USB-C
      cable or power during this.
- [x] When SDK Manager reports success: **disconnect the USB-C cable.**

### 3.3 First boot
- [x] Power-cycle the Jetson **without** the recovery short: unplug DC, wait 10 s, plug DC back
      in. (No jumper this time.)
- [x] Give it ~60 s to boot. Proceed to Part 4 to reach it over the network.
- [x] *(Fallback)* If anything looks wrong, attach the monitor (DisplayPort) + USB keyboard now
      to watch the boot and log in locally.

> **Firmware note (only if the flash *refuses* or the board won't boot 7.2):** the JetPack 7.2
> installer expects **JetPack 6.x-generation UEFI/QSPI firmware** already on the module. A
> brand-new Super kit has this. If yours somehow has older factory firmware, SDK Manager can
> update the firmware first (it will prompt), or you run the JetPack 6.x firmware-update path
> once and then re-run the 7.2 flash. This should not happen on a current Super kit.

> ### If SDK Manager won't cooperate — Jetson ISO on USB (fallback)
> 1. On any computer (Win/Mac/Linux) download the **Jetson ISO** for JetPack 7.2 from
>    <https://developer.nvidia.com/embedded/jetpack/downloads>.
> 2. Write it to a **USB flash drive** (not the microSD): `sudo dd if=jetson.iso of=/dev/sdX
>    bs=4M status=progress conv=fsync` (replace `/dev/sdX` — double-check with `lsblk`!), or use
>    Balena Etcher.
> 3. Attach **monitor + keyboard** to the Jetson, plug in the USB stick, power on, and pick the
>    USB drive in the boot menu.
> 4. The installer lets you choose the **install target — microSD or NVMe** — and runs the
>    Ubuntu setup on-screen. This path *requires* the monitor because there's no pre-config.

---

## Part 4 — Network & headless remote session

**Goal:** reach the Jetson over SSH from the workstation, and give the Jetson internet (needed
for `apt` in Parts 5–6) — all over a single direct Ethernet cable, using your workstation's
Wi-Fi as the uplink.

**How it works:** NetworkManager's **"shared" IPv4 mode** turns your workstation's Ethernet
port into a tiny DHCP server + NAT router. The Jetson gets an address in `10.42.0.0/24`
(NetworkManager's default shared subnet), and its internet is NAT'd out through your Wi-Fi.

- [x] Cable the Jetson's Ethernet port directly to the workstation's Ethernet port.
- [x] On the **workstation**, create a shared connection on the Ethernet interface (confirmed
      `enp6s0` in Part 2):
  ```bash
  nmcli connection add type ethernet ifname enp6s0 con-name jetson-share ipv4.method shared
  nmcli connection up jetson-share
  ```
  This assigns the workstation `10.42.0.1` and starts handing out DHCP + NAT on that port.
  Your Wi-Fi connection is untouched and remains the internet source.
- [x] Find the Jetson's IP (it will be something like `10.42.0.x`):
  ```bash
  # Option A — mDNS by the hostname you set in SDK Manager:
  ping jetson-orin.local

  # Option B — scan the shared subnet:
  ip neigh show dev enp6s0            # shows learned neighbors
  # or, if nmap is installed:
  nmap -sn 10.42.0.0/24
  ```
  > `10.42.0.217` is a DHCP lease from the shared connection, not a static assignment — it'll
  > likely persist across reboots (same MAC → same lease) but re-check with `ip neigh` /
  > `nmap` if SSH ever stops connecting.
- [x] SSH in. **Confirmed for this board:** username is `Mike` (capital M — set during SDK
      Manager's OEM pre-config), IP is `10.42.0.217`. Hostname pre-config was skipped, so the
      Jetson is still `localhost.localdomain` — `.local` mDNS will **not** resolve; use the IP:
  ```bash
  ssh Mike@10.42.0.217
  ```
- [x] Once in, confirm the Jetson has **internet through the shared link**:
  ```bash
  ping -c 3 nvidia.com
  ```
  If ping fails but SSH worked, the NAT/DNS side of sharing isn't up — see troubleshooting.
- [x] **(Recommended) set up passwordless SSH** so later steps and the CI runner are smooth:
  ```bash
  # on the workstation:
  ssh-copy-id Mike@10.42.0.217
  ```

<details>
<summary>Troubleshooting the direct-Ethernet link</summary>

- **No `10.42.0.x` neighbor appears:** the Jetson's wired connection may not be set to DHCP, or
  the cable/port is down. Attach the monitor and check `nmcli device status` on the Jetson;
  ensure its Ethernet is "connected". Confirm the workstation side: `nmcli -f NAME,DEVICE,STATE
  connection show --active` should list `jetson-share` active on your Ethernet device.
- **SSH works, internet (`ping nvidia.com`) fails:** sharing's NAT depends on IP forwarding and
  the firewall. Check `cat /proc/sys/net/ipv4/ip_forward` is `1` on the workstation
  (NetworkManager sets this for shared connections). If you run a restrictive `ufw`/nftables
  setup, it may block the forward — temporarily `sudo ufw disable` to test, or add a forward
  rule.
- **mDNS (`jetson-orin.local`) doesn't resolve:** install/enable avahi on both ends, or just use
  the numeric `10.42.0.x` address from `nmap`/`ip neigh`.
- **Tear-down when done:** `nmcli connection down jetson-share` (or `nmcli connection delete
  jetson-share`) restores the Ethernet port.

</details>

---

## Part 5 — Smoke tests

**Why:** confirm the OS, GPU stack, thermals, and storage are healthy *before* piling ROS2 and
CI on top. Cheap now, expensive to untangle later. Run all of these over SSH on the Jetson.

- [x] **OS is what we expect:**
  ```bash
  cat /etc/os-release          # VERSION="24.04..."; UBUNTU_CODENAME=noble
  uname -a                     # aarch64
  ```
- [x] **JetPack / L4T version:**
  ```bash
  cat /etc/nv_tegra_release    # expect R39 (revision 2...) == L4T r39.2 == JetPack 7.2
  # If installed: dpkg-query --show nvidia-jetpack
  ```
- [x] **GPU / SoC live stats (Jetson's equivalent of nvidia-smi):**
  ```bash
  sudo tegrastats            # live CPU/GPU/EMC/thermal; Ctrl-C to stop
  # nicer TUI if you install it:
  sudo pip3 install jetson-stats && sudo reboot   # then run: jtop
  ```
- [x] **Power mode / clocks** (Super kit supports a higher "MAXN SUPER" mode):
  ```bash
  sudo nvpmodel -q            # show current power model
  sudo nvpmodel -m 0          # max performance (confirm mode number via -q list)
  sudo jetson_clocks          # pin clocks to max (optional, for benchmarking Part 7)
  ```
- [x] **CUDA present (only if you added SDK components):**
  ```bash
  nvcc --version              # or: ls /usr/local/cuda*/bin
  ```
  > Expected to say `command not found` on this board — Target Components (CUDA/cuDNN/TensorRT)
  > were intentionally skipped in Part 3.2 for a clean OS-only first flash. Not needed for
  > Parts 6–9. Revisit when GPU-accelerated inference is needed — see Part 10 follow-ups.
- [x **Thermals sane at idle:** in `tegrastats`/`jtop`, confirm temps are reasonable (tens of
      °C idle, not thermal-throttling).
- [x] **Storage — confirm you're actually on the microSD** and note free space:
  ```bash
  lsblk                       # rootfs should be on mmcblk* (microSD), not nvme*
  df -h /                     # note total/free
  ```
- [x] **Networking basics:** `hostname`, `ip -br addr`, `ping -c3 8.8.8.8`.

Record anything odd here before continuing.

### Logging off / de-powering safely (end of session)
- [x] On the **Jetson** (over SSH), shut the OS down cleanly — don't just pull power:
  ```bash
  sudo shutdown now
  ```
- [x] Wait for the SSH session to drop and give it ~15–20s past that for the filesystem to
      finish unmounting (microSD is more corruption-prone than NVMe on a hard power cut).
- [x] Unplug the **DC power** from the Jetson. Leave the microSD and USB-C cable connected/
      inserted — nothing needs to come apart between sessions.
- [x] On the **workstation**, the `jetson-share` connection can be left as-is (it'll just sit
      idle with no link partner) or torn down if you want the Ethernet port back:
      `nmcli connection down jetson-share`. Not required — recreating it next time is one
      command (Part 4) if you do tear it down.
- [x] Nothing else to clean up — you stopped at the end of Part 5, before Part 6 touched
      anything, so there's no partial ROS2 install or build state to worry about.

---

## Part 6 — Install ROS2 Jazzy

> **Resuming here after a break?** Power back up in this order:
> 1. Plug the Jetson's **DC power** back in (no recovery-mode short this time — just a normal
>    boot). Give it ~60s.
> 2. On the **workstation**, bring the shared Ethernet connection back up (skip if you never
>    tore it down): `nmcli connection up jetson-share`.
> 3. Re-cable Jetson Ethernet → workstation Ethernet if it got disconnected.
> 4. Confirm you can still reach it: `ping -c3 10.42.0.217` (DHCP lease from Part 4 — re-check
>    with `ip neigh show dev enp6s0` if that IP doesn't answer after some elapsed time/reboots).
> 5. SSH in: `ssh Mike@10.42.0.217` (capital `M` — see Part 4). Passwordless if `ssh-copy-id`
>    was completed; password prompt otherwise.
> 6. You're back where Part 5 left off — hostname is still `localhost.localdomain`, CUDA is
>    still intentionally not installed (see Part 5 note and Part 10 follow-ups). Proceed below.

**Why Jazzy:** matches the workstation and the stage-2 Docker image exactly — one distro across
sim, CI, and hardware. Run on the Jetson over SSH.

- [x] Enable the `universe` repo and prerequisites:
  ```bash
  sudo apt update && sudo apt install -y software-properties-common curl
  sudo add-apt-repository universe -y
  ```
- [x] Add the ROS2 apt source (current `ros-apt-source` package method):
  ```bash
  export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
    | grep -F "tag_name" | awk -F\" '{print $4}')
  curl -L -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb"
  sudo apt install -y /tmp/ros2-apt-source.deb
  sudo apt update
  ```
- [x] Install ROS2 Jazzy base + dev tools + CycloneDDS (matching this project's RMW):
  ```bash
  sudo apt install -y ros-jazzy-ros-base ros-dev-tools ros-jazzy-rmw-cyclonedds-cpp
  ```
  > `ros-base` (not `desktop`) — the Jetson is headless; we don't want RViz/Gazebo GUI stacks
  > on it. It's a runtime/build target and a CI runner, not a visualization host.
- [x] Wire the environment to match the workstation's `.bashrc` conventions:
  ```bash
  echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc
  echo 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' >> ~/.bashrc
  source ~/.bashrc
  ```
- [x] Sanity check:
  ```bash
  ros2 --help
  printenv ROS_DISTRO            # jazzy
  printenv RMW_IMPLEMENTATION    # rmw_cyclonedds_cpp
  # quick talker/listener in two SSH sessions:
  ros2 run demo_nodes_cpp talker      # (needs ros-jazzy-demo-nodes-cpp; apt install if desired)
  ```

---

## Part 7 — Native build + record the microSD baseline

**Why:** this is the payoff of Session 14 — proving the arm64 build works *natively* on
hardware, and capturing the "microSD" numbers that BLUEPRINT compares against QEMU (and, in
Part 9, against NVMe). **If this build is not clean, stop and debug here — do not move on to
the CI runner swap (Part 8) on a shaky build.**

- [x] **Authenticate git for this private repo.** Plain `git clone` over HTTPS will prompt for a
      username/password and **fail** — GitHub dropped password auth for git operations in 2021,
      and this repo is private so an anonymous/unauthenticated clone isn't an option either. Use
      the GitHub CLI's device-code flow instead (same tool used for `gh auth login` on the
      workstation in Session 03) — no browser needed *on the Jetson*, just any other device:
  ```bash
  sudo apt install -y gh
  gh auth login
  # Choose: GitHub.com -> HTTPS -> Yes (authenticate Git) -> "Login with a web browser"
  # It prints a one-time code + a URL (github.com/login/device). Open that URL on your
  # workstation or phone, log in, paste the code. The Jetson terminal reports success once
  # that's done — it just sets up a git credential helper, nothing runs a browser locally.
  ```
- [x] Get the repo onto the Jetson and install build deps:
  ```bash
  sudo apt install -y python3-colcon-common-extensions python3-pip
  gh repo clone sdfinn/autonomous-fleet-testbed ~/autonomous-fleet-testbed
  cd ~/autonomous-fleet-testbed
  # If the package has rosdep-managed deps:
  sudo apt install -y python3-rosdep && sudo rosdep init 2>/dev/null; rosdep update
  rosdep install --from-paths src --ignore-src -r -y || true
  ```
  > If `rosdep install` errors with `XML or text declaration not at start of entity` on
  > `package.xml`: that was a real bug in the repo (leading whitespace before `<?xml ...?>`
  > from a Session 04 heredoc), fixed 2026-07-10 — `git pull` to pick up the fix if you cloned
  > before then.
- [x] **Timed native colcon build** (this is a recorded number):
  ```bash
  cd ~/autonomous-fleet-testbed
  time colcon build --symlink-install
  source install/setup.bash
  ```
  Record the `real` time. This is the number that retires QEMU: compare it to the
  "Stage 2 arm64 build time (QEMU)" line CI currently prints (~24–29 min emulated).
  **Result (2026-07-10, microSD): `real 0m4.759s`** — vs. ~24–29 min QEMU. This is the
  headline speedup number.
- [x] **Timed first `docker pull` of the stage-2 arm64 image** (proves the Jetson can pull and
      run the CI image natively):
  ```bash
  sudo apt install -y docker.io && sudo usermod -aG docker $USER   # then re-login (SSH out/in)
  time docker pull ghcr.io/sdfinn/autonomous-fleet-testbed:latest
  ```
  > At the time this was first run, `stage-2-arm64` only tagged images by commit SHA — no
  > `:latest` existed yet (fixed 2026-07-10, `ci.yml` now also pushes `:latest`; see
  > BLUEPRINT.md decision log). The measurement below used the explicit SHA tag
  > (`ghcr.io/sdfinn/autonomous-fleet-testbed:cee03807079e47e41f65b29d4a3552eea0deb5a8`) as a
  > workaround — re-run against `:latest` next time to confirm it still matches.
  **Result (2026-07-10, microSD): `real 4m15.202s`.**
- [x] Run the Python unit tests natively (same command the x86 loop uses):
  ```bash
  python3 -m pytest tests/ -v \
    --ignore=tests/test_ros2_contracts.py --ignore=tests/test_navigation.py
  ```
  > Both `test_ros2_contracts.py` and `test_navigation.py` import `rclpy` / need a live
  > Gazebo+Nav2 stack — same `--ignore` treatment as the x86 dev loop (see CLAUDE.md).
- [ ] **Log the baseline numbers.** Create a small record so Part 9 can compare apples to
      apples. Suggested table to fill in (paste into your session notes or a scratch file):

  | Metric | microSD (Part 7) | NVMe (Part 9) |
  |---|---|---|
  | `apt install ros-jazzy-ros-base` wall time | (not recorded) | |
  | `colcon build --symlink-install` (`real`) | 4.759s | |
  | first `docker pull` of stage-2 image | 4m15.202s | |
  | `df -h /` free space | | |

---

## Part 8 — Add the Jetson as a self-hosted CI runner

> **Only start this if Part 7's native build was clean.** The point is to replace the slow
> emulated `stage-2-arm64` (QEMU on `ubuntu-latest`) with a *native* arm64 build on the Jetson.

**Current state (for reference):** `stage-2-arm64` in `.github/workflows/ci.yml` runs on
`ubuntu-latest` and cross-builds for `linux/arm64` via `docker/setup-qemu-action` — that's the
~24–29 min emulated build we're retiring.

### 8.1 Register the runner (on the Jetson)
- [x] In a browser: repo → **Settings → Actions → Runners → New self-hosted runner** → pick
      **Linux / ARM64**. GitHub shows a download + `config.sh` snippet with a **registration
      token** (tokens expire — generate it right before you use it).
- [x] On the Jetson, follow that snippet, but set **labels** so CI can target it precisely:
  ```bash
  mkdir -p ~/actions-runner && cd ~/actions-runner
  # curl the runner tarball URL from the GitHub page, then:
  tar xzf actions-runner-linux-arm64-*.tar.gz
  ./config.sh --url https://github.com/sdfinn/autonomous-fleet-testbed \
    --token <TOKEN_FROM_GITHUB> \
    --labels self-hosted,arm64,jetson,orin-nano \
    --name jetson-orin
  ```
  > Runner group prompt: accepted the `Default` group (org/enterprise-level access control,
  > not relevant for a single personal repo).
- [x] Install it as a service so it survives reboots (mirrors the x86 runner setup):
  ```bash
  sudo ./svc.sh install
  sudo ./svc.sh start
  sudo ./svc.sh status
  ```
  **Result (2026-07-10): service `actions.runner.sdfinn-autonomous-fleet-testbed.jetson-orin`
  active (running)** via systemd, runs as user `Mike`.
- [x] Confirm it shows **Idle** under Settings → Actions → Runners. **Confirmed 2026-07-10.**

### 8.2 Point `stage-2-arm64` at the Jetson (native, no QEMU)
- [x] Edit `.github/workflows/ci.yml`, `stage-2-arm64` job:
  - Change `runs-on: ubuntu-latest` → `runs-on: [self-hosted, arm64, jetson]`
  - **Remove the QEMU step** (native arm64 doesn't need emulation):
    ```yaml
    # DELETE these two lines — native arm64 build needs no emulation:
    # - name: Set up QEMU
    #   uses: docker/setup-qemu-action@v3
    ```
  - Keep buildx, GHCR login, and the build-push step. `platforms: linux/arm64` is now native.
  - Update the timing echo text from "(QEMU)" to "(native Jetson)" so the summary reads true.
- [x] Commit on a branch and push; watch the run:
  ```bash
  git checkout -b session-14-jetson-runner
  git add .github/workflows/ci.yml
  git commit -m "ci(session-14): build stage-2-arm64 natively on Jetson runner, retire QEMU"
  git push -u origin session-14-jetson-runner
  gh run watch
  ```
  > Opened as PR #1 instead of pushing straight to `main`, since `ci.yml` only triggers on
  > `push`/`pull_request` targeting `main` — a bare feature-branch push doesn't run CI at all.
  > Two real bugs surfaced and were fixed along the way (both now on this branch):
  > 1. `changes` job (`dorny/paths-filter@v3`) failed with `Resource not accessible by
  >    integration` on the `pull_request` trigger — needed an explicit `permissions:
  >    pull-requests: read`, since `pull_request`-triggered PR-file-listing needs a scope a
  >    plain push never required.
  > 2. That fix alone then broke `actions/checkout` ("repository not found") — adding a
  >    job-level `permissions:` block replaces ALL default scopes, not just the one added, so
  >    `pull-requests: read` alone implicitly zeroed `contents` too. Same class of bug as the
  >    Session 08 `packages: write` incident already in CLAUDE.md's Gotchas. Fixed by listing
  >    both `contents: read` and `pull-requests: read` explicitly.
- [x] Confirm `stage-2-arm64` ran **on the Jetson** and the native build time roughly matches
      your Part 7 `colcon`/`docker` numbers (and beats the old QEMU time). If it's flaky, revert
      the `runs-on` change and keep QEMU until the hardware path is solid — don't leave CI red.
  **Result (2026-07-10, PR #1, run 29134826190): all 7 jobs green, `stage-2-arm64` confirmed
  running on `runner_name: jetson-orin`.** Job step echoed `Stage 2 arm64 build time (native
  Jetson): 15s` — but that's a warm-cache number (`cache-from/cache-to: type=gha` reused
  layers from the prior `cb1f14c` build since the Dockerfile/deps hadn't changed), not a cold
  build comparable to the ~24–29 min QEMU baseline.

  **Re-measured non-cached (2026-07-10, direct push to `main`, run 29135219100):** added a
  comment line to `requirements-ci.txt` — it's `COPY`ed into the image ahead of `pip install`
  and `colcon build`, so any change to it invalidates both of those layers and forces a real
  rebuild (only the base `ros:jazzy-ros-base` OS layer stayed cached, same as any real build
  would reuse). Result: **585s (9m45s) build+push**, ~10m22s total job wall time. vs. the
  23m43s–24m31s QEMU baseline, that's **~2.4x faster** — real and credible, but nowhere near
  the originally-projected 3–5 min (see BLUEPRINT.md's decision log for why the estimate
  undershot: still on microSD, and QEMU's cost isn't *only* emulation tax). Logged in
  BLUEPRINT.md's Tiered development loop table and Session 08 decision entry.

---

## Part 9 — Migrate microSD → NVMe SSD

### Decisions & background (settled 2026-07-12 — read once, then execute the checklist)

**What this Part does:** replaces the microSD rootfs with a **fresh, headless JetPack 7.2
install on the NVMe SSD**, re-provisions everything from this runbook, records the
NVMe-at-25W baseline, and ends with a proven HIL run. It happens **before Session 16** so
Session 16's CI/HIL benchmarks and reproducibility records land once, on the final
configuration (BLUEPRINT.md's 2026-07-12 entries). When the checklist is done: Part 10
closeout, then Session 16.

**Why now:** the module is a bare board on the desk — storage work is trivial now and a
pain later (Session 16 puts it in the robot chassis). The dev kit's M.2 Key-M slot is
**PCIe Gen3 x4** — far below a Gen4 SSD's ceiling but a large jump over microSD, especially
for random I/O (builds, apt, DDS discovery caches). The SSD is already seated: `lsblk` on
the board shows `nvme0n1` (465.8 G, blank — verified 2026-07-12).

**How boot works here (learning note):** on Orin-generation Jetsons the early boot chain
(UEFI) lives in **QSPI flash on the module itself**, not on the storage device — that's why
a board with no SD card inserted can still enter recovery mode for a flash (or show a UEFI
menu and boot an installer USB, in the fallback path). The installed system then boots
UEFI → `/boot/extlinux/extlinux.conf` on the NVMe — the same chain the SD uses today.

Decisions baked into the steps (full rationale: BLUEPRINT.md decision log, 2026-07-12):

- **Fresh install, not clone.** The JetsonHacks `migrate-jetson-to-ssd` clone was retired
  unattempted after its own compatibility gate: the repo is "only tested on JetPack 6"
  (last commit Jan 2025, open post-migration boot-hang issues #12/#13, zero r39 reports),
  while live inspection of this board showed r39.2 boots UEFI →
  `/boot/extlinux/extlinux.conf` with `root=PARTUUID=...` plus a separate `/boot/efi` ESP
  (`mmcblk0p10`) in a 15-partition layout the UUID-era scripts predate — the boot-config
  rewrite, the scripts' most critical step, is exactly the unverified part. The re-provision
  is also the point, not a cost: running Parts 4–8 again purely from this doc live-tests
  that the runbook is complete and reusable (its future: a general robot-setup manual,
  candidate name `RobotSetup.md`). Retired-path record at the end of this Part.
- **Headless SDK Manager flash is the primary method** — recovery mode over USB-C, the
  exact Part 3 process that flashed the SD, pointed at NVMe this time. No monitor, no
  keyboard, no USB stick. NVIDIA's officially recommended Jetson ISO installer is the
  **fallback** (it needs a DisplayPort monitor + USB keyboard — see the fallback section).
- **No GUI on the Jetson.** The stock rootfs ships the Ubuntu desktop; we leave it
  installed but stop booting into it (`systemctl set-default multi-user.target`). A
  headless CI runner + Nav2 never need it, and on an 8 GB board the idle desktop costs
  real memory. Reversible with one command if a screen is ever attached.
- **Identity: username `mike` (lowercase), hostname `jetson`.** Lowercase `mike` matches
  the workstation username, so plain `ssh <ip>` needs no `user@`; `jetson` enables
  `ssh mike@jetson.local` (mDNS) and ends the DHCP-lease chasing. The old
  `Mike`/`localhost.localdomain` were SDK-Manager pre-config accidents, not choices —
  and expect to set the hostname manually post-boot (the pre-config screen silently
  skipped that field on the SD flash).
- **Benchmarks: NVMe-at-25W becomes the go-forward record.** The planned 25W SD
  re-baseline was dropped with the clone — fresh bits aren't an A/B against the old
  install anyway. Flag the original SD numbers "unrecorded power mode, historical" in the
  Part 7 table. The 25W pin lives on the SD's rootfs (`/var/lib/nvpmodel/status`), so it
  must be re-applied on the new install.
- **The microSD is the rollback.** It comes out of the board before flashing and is never
  written again; store it untouched until Session 16's `stage-4-hil` has gone green 3×
  consecutively. If anything below fails: SD back in, boot, you're exactly where you
  started.

### The migration — start to finish

- [ ] **1. Targeted backup off the SD (minutes — Jetson still up on the SD).** No full
      `dd` image needed: the SD itself is the backup, since it's never written again.
      Copy off the only things that exist nowhere else (inventoried over SSH 2026-07-12:
      `git status` on the Jetson repo shows nothing untracked except `reports/photos/`;
      ROS2 is stock apt at `/opt/ros/jazzy`; no separate venv; the runner registration
      can't be transplanted anyway):

  ```bash
  # From the workstation (last run with the capital-M username):
  mkdir -p ~/jetson-backup-2026-07
  scp Mike@10.42.0.217:autonomous-fleet-testbed/reports/fleet_runs.db ~/jetson-backup-2026-07/
  scp -r Mike@10.42.0.217:autonomous-fleet-testbed/reports/photos     ~/jetson-backup-2026-07/
  scp Mike@10.42.0.217:.bashrc                                        ~/jetson-backup-2026-07/jetson.bashrc
  ```

  `fleet_runs.db` = the Jetson-side telemetry rows (16 K); `photos/` = Mission 1 HIL
  evidence; the `.bashrc` is a reference for env tweaks worth re-applying by hand (don't
  restore it wholesale over the fresh one).
- [x] **2. SSD installed.** ✅ Done — seated and verified 2026-07-12: `nvme0n1`, 465.8 G,
      no partitions. (For future boards: the **M.2 Key-M 2280** slot is on the underside
      of the carrier board; the short 2230 Key-E slot next to it is for wifi cards. Power
      off and unplug before seating; secure with the standoff screw.)
- [ ] **3. Power off and pull the microSD.** `sudo shutdown -h now` over SSH, unplug DC
      power, eject the microSD and set it aside. Out of the machine it physically cannot
      be touched by the flash — it stays a complete, bootable, known-good system.
- [ ] **4. Recovery mode.** Short `FC REC`↔`GND` on the J14 header while applying DC
      power, hold ~2–3 s after power comes on, release. Connect USB-C to the workstation
      (a **data** cable — charge-only cables are the #1 cause of no detection). Verify:

  ```bash
  lsusb | grep -i nvidia    # expect: 0955:7523 NVIDIA Corp. APX
  ```

  Full pin-numbering detail and photos: **Part 3.1**.
- [ ] **5. Flash with SDK Manager — target = NVMe.** Launch `sdkmanager` on the
      workstation (installed in Part 2) and follow **Part 3.2** with three differences:
      - **Storage device: NVMe** — the critical dropdown (SD card was chosen last time).
      - **OEM pre-config:** username **`mike`** (lowercase), password, runtime setup. If a
        hostname field appears, enter **`jetson`** — but don't count on it appearing (it
        silently didn't on the SD flash); step 7 verifies either way.
      - **Target Components (CUDA/cuDNN/TensorRT): skip**, same as the SD flash —
        OS-only. Add later with `sudo apt install nvidia-jetpack` if ever needed.

      ~20 min; the board reboots itself into first boot when the flash completes.
- [ ] **6. First contact over SSH.** The shared-Ethernet recipe (Part 4) is unchanged and
      the board's MAC is the same, so the DHCP lease will likely still be `10.42.0.x`:

  ```bash
  ip neigh show dev enp6s0     # find the Jetson's IP
  ssh mike@10.42.0.217         # lowercase user now (adjust IP if the lease moved)
  ```
- [ ] **7. Set the hostname + confirm identity:**

  ```bash
  hostname                     # if it's not "jetson":
  sudo hostnamectl set-hostname jetson
  grep -n localhost /etc/hosts # point the 127.0.1.1 line at "jetson" if a stale name is there
  whoami && hostname           # expect: mike / jetson
  ```

  From the workstation, `ssh mike@jetson.local` should now resolve via mDNS.
- [ ] **8. Turn the GUI off (boot to console from now on):**

  ```bash
  sudo systemctl set-default multi-user.target
  sudo reboot
  ```

  The desktop stays installed but never starts — RAM and GPU stay free for the CI runner
  and Nav2. (Revert anytime: `sudo systemctl set-default graphical.target` + reboot.)
- [ ] **9. Verify the storage and OS state:**

  ```bash
  findmnt /                    # rootfs on /dev/nvme0n1p1 (or the installer's rootfs partition)
  df -h /                      # ~465 G visible
  cat /etc/nv_tegra_release    # R39 (release), REVISION: 2.0
  systemctl get-default        # multi-user.target
  ```
- [ ] **10. Re-pin the power mode** (the 25W pin died with the SD rootfs):

  ```bash
  sudo nvpmodel -m 1 && sudo nvpmodel -q    # expect mode 1 / 25W
  ```
- [ ] **11. Re-provision from this runbook — and log every gap, stale step, or surprise
      you hit; that's a deliverable of this migration, not an interruption.** In order:
      - **Part 4**: `ssh-copy-id mike@<ip>` (fresh home dir = fresh `authorized_keys`).
      - **Part 5**: smoke tests — rootfs on `nvme0n1p1` this time.
      - **Part 6**: ROS2 Jazzy.
      - **Part 7**: the timed `colcon build --base-paths src`, native pytest, and
        `docker pull` — **these ARE the NVMe-at-25W baseline numbers**; enter them in the
        Part 7 table and BLUEPRINT.md's comparison, with the old SD column flagged
        historical.
      - **Part 8**: CI runner — **first remove the old `jetson-orin` runner entry** in
        GitHub → Settings → Actions → Runners (its registration died with the SD install),
        then register fresh with a new token, same `jetson-orin` name and labels so
        `ci.yml` needs no changes.
      - **HIL prerequisites**: `docs/runbooks/Mission1HILSession15.md` Part 1
        (`ros-jazzy-navigation2`, `ros-jazzy-nav2-bringup`, `ros-jazzy-rmw-cyclonedds-cpp`,
        `python3-pil`, repo on `main`, `colcon build --base-paths src`).
- [ ] **12. Restore the backed-up data:**

  ```bash
  scp ~/jetson-backup-2026-07/fleet_runs.db mike@<ip>:autonomous-fleet-testbed/reports/
  scp -r ~/jetson-backup-2026-07/photos     mike@<ip>:autonomous-fleet-testbed/reports/
  ```
- [ ] **13. Prove it end to end.** Runner shows **Idle (green)** in GitHub → Settings →
      Actions → Runners; native pytest suite green (Part 7's command); then **one manual
      HIL run** (`docs/runbooks/Mission1HILSession15.md` Parts 2–3, ~10 min) — Nav2, the
      mission executor, and the fresh runner registration all proven on the new install.
- [ ] **14. Close out.** Part 10 (publish the baseline numbers, mark Session 14 ✅ in
      `Release1Todo.md`'s Session Index), plus the identity doc sweep: update `Mike@` →
      `mike@`, `localhost.localdomain` → `jetson`, and any leftover "SD→NVMe clone"
      phrasing in `CLAUDE.md` (Jetson state paragraph),
      `docs/runbooks/Mission1HILSession15.md` (SSH line),
      `docs/session15-hil-ci-stage-design.md` (its SSH commands say `Mike@` — Session 16
      implements `stage-4-hil` from that doc, so it must say `mike@` before then), and
      `Release1Todo.md` Session 14's "state to know" line. Leave dated files in
      `docs/superpowers/plans/` and `docs/superpowers/specs/` alone — historical records.
      Store the microSD untouched until `stage-4-hil` is 3× green; wipe or repurpose after.
- [ ] **15. If the flash or first boot fails:** microSD back in, boot — you're exactly
      where you started. Retry from step 3, or switch to the monitor-attached fallback
      below.

### Fallback — Jetson ISO USB installer (monitor-attached)

NVIDIA's recommended JetPack 7.2 install path (and on Orin Nano, 7.2 is the only JetPack
that supports it), kept as the fallback because it needs hardware the primary path doesn't:
a **USB stick (≥16 GB, wiped)**, a **DisplayPort monitor** (the dev kit has DP, not HDMI),
and a **USB keyboard**. The firmware prerequisite (JetPack 6.x-generation UEFI in QSPI) is
already satisfied — this board runs JetPack 7.2 now.

- [ ] Make the install USB on the workstation: download the **JetPack 7.2 Jetson ISO**
      from NVIDIA's JetPack downloads page, write with Balena Etcher or:

  ```bash
  lsblk   # identify the USB stick device — triple-check; dd on the wrong device is fatal
  sudo dd if=~/Downloads/<jetson-iso>.iso of=/dev/sdX bs=4M status=progress oflag=sync
  ```
- [ ] microSD out (steps 1–3 above still apply), monitor + keyboard + USB stick in.
      Power on holding **ESC** → UEFI menu → **Boot Manager** → the USB device. At the
      GRUB menu choose **Install Jetson ISO r39.2**; target storage: **`nvme0n1`** (with
      the SD out, the blank SSD is the only sane target).
- [ ] The board reboots into Ubuntu's first-boot wizard: username **`mike`**, hostname
      **`jetson`** (the wizard has a "computer's name" field — but verify per step 7
      anyway). Then rejoin the primary checklist at **step 6**.

### Retired — on-device clone (2026-07-12, never attempted)

For the record: this Part briefly recommended cloning the running SD to the NVMe with
JetsonHacks' [`migrate-jetson-to-ssd`](https://github.com/jetsonhacks/migrate-jetson-to-ssd)
scripts (`make_partitions.sh` / `copy_partitions.sh` / `configure_ssd_boot.sh`), preserving
the whole Sessions 14–15 install. It was retired by its own compatibility gate before any
hardware was touched — evidence in the decision note at the top of this Part (scripts tested
only on JetPack 6; this board's r39.2 boot config uses `root=PARTUUID` + a separate
`/boot/efi` ESP in a 15-partition layout the UUID-era scripts predate; open boot-hang
issues). If a future board ever genuinely needs a clone (e.g. an install too costly to
reproduce), re-verify those scripts against that JetPack version first — but the better fix
is keeping this runbook good enough that no install is ever too costly to reproduce.

> **SD hygiene reminder (from Release1Todo):** don't record rosbags/heavy logs to a microSD
> while it's the live rootfs — sustained writes wear SD cards. On NVMe this stops mattering.

---

## Part 10 — Close out Session 14

- [ ] Fill in the NVMe-at-25W numbers in the baseline table (Part 7) and drop them into
      `BLUEPRINT.md` where the QEMU-vs-native / SD-vs-NVMe comparison lives. Flag the
      original SD column as historical ("unrecorded power mode, pre-25W-pin") — the
      planned 25W SD re-baseline was skipped when Part 9 switched from clone to fresh
      install (2026-07-12), so the table is a record, not a controlled A/B.
- [ ] Mark **Session 14 ✅** in `Release1Todo.md`'s Session Index.
- [ ] **Correct the stale assumptions** this runbook uncovered, so the plan matches reality:
  - In `Release1Todo.md` Session 14, the "flash to MicroSD image" framing is obsolete —
    **JetPack 7.2 removed SD-card images**; the method is SDK Manager (USB-C recovery) or the
    Jetson ISO-on-USB installer. Update the flash step to reflect this.
  - The plan's "SDK Manager → select JetPack, recovery mode" is correct in spirit; the
    corrected specifics (P3767-0005/P3768-0000, pre-config for headless, microSD-as-target
    caveat) live in this doc — link to it from the session.
- [x] Note the optional Jetson-in-the-loop-with-sim stretch goal is **not** required for
      Session 14 completion (per the plan) — only attempt if time remains. **Update
      (2026-07-10): promoted to its own session** (Isaac Sim + real Jetson
      hardware-in-the-loop, a bigger version of this idea) — see `Release1Todo.md` Session 15.
      This block stays here as the historical record of the original idea.
- [x] **CI pipeline rewiring done tonight (2026-07-10), outside this runbook's original
      scope:** `stage-3-arm64` (renumbered — was `stage-2-arm64`) now requires
      `stage-2-gazebo` (renumbered — was `stage-3-gazebo`) to pass first (fail-fast — don't
      spend ~10 real minutes on a native arm64 build if the cheap Gazebo check already
      failed); `stage-4-isaac` now runs after `stage-3-arm64` (matches the original diagram's
      arm64→Isaac edge); and drift/report recording split into independent
      `stage-5-reports-sim` / `stage-5-reports-hw` paths. Full rationale and the exact
      `ci.yml` diff are in
      BLUEPRINT.md's decision log.
- [ ] Commit the doc updates:
  ```bash
  git add Release1Todo.md BLUEPRINT.md docs/runbooks/JetsonInstallSession14.md
  git commit -m "docs(session-14): Jetson Orin Nano install runbook + baseline; correct JetPack 7.2 flash method"
  ```

### Follow-ups for a later session (not blocking Session 14)
- **Hostname:** ~~still `localhost.localdomain`~~ — **resolved by Part 9**: the fresh NVMe
  install sets hostname `jetson` (and username `mike`), per the 2026-07-12 decision — via
  pre-config if the field appears, else `hostnamectl` at Part 9 step 7. (Original note: the
  SDK Manager pre-config screen only asked for username/password on the SD flash, hostname
  got skipped.)
- **GPU access for on-device inference:** this flash intentionally skipped CUDA/cuDNN/TensorRT
  (Part 3.2 Target Components, confirmed skipped in Part 5's `nvcc` check above). Fine for
  Parts 6–9 (ROS2 Jazzy, native build, CI runner — none need the GPU compute stack). Once
  autonomous-navigation work needs on-device inference (e.g. a perception model informing
  Nav2), install it with `sudo apt install nvidia-jetpack` (L4T apt sources are already present
  on the board) rather than re-flashing from scratch.

---

### Sources (verified 2026-07-08)
- NVIDIA — [JetPack SDK downloads & notes](https://developer.nvidia.com/embedded/jetpack/downloads)
- NVIDIA docs — [Orin Nano Dev Kit BSP Setup](https://docs.nvidia.com/jetson/orin-nano-devkit/user-guide/latest/setup_bsp.html) (Jetson ISO method; JetPack 6.x firmware prerequisite)
- NVIDIA Developer Forums — [Setting up the Orin Nano Super Dev Kit on JetPack 7.2 — practical guide, June 2026](https://forums.developer.nvidia.com/t/setting-up-the-nvidia-jetson-orin-nano-super-dev-kit-on-jetpack-7-2-a-practical-guide-june-2026/372490) (recovery-mode + SDK Manager specifics, headless pre-config)
- Cytron — [How to Install JetPack 7.2 on Jetson Orin Nano Super](https://my.cytron.io/tutorial/how-to-install-jetPack-7.2-on-jetson-orin-nano-super)

> **Not yet hardware-verified.** These steps are assembled from current NVIDIA docs + the
> June 2026 practical guide, not yet run against your specific board. Treat pin numbering and
> the exact SDK Manager screen labels as "confirm against the printed card / live UI" — flag
> anything that doesn't match and we'll correct the doc as you go.
