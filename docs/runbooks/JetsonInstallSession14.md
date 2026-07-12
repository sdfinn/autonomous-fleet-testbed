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

### Execution sequence (agreed 2026-07-12 — run in this order)

The migration happens **before Session 16** (so Session 16's CI/HIL benchmarks and
reproducibility records land once, on the final configuration — see BLUEPRINT.md's
2026-07-12 sequencing entry). The Jetson was pinned to **25W power mode on 2026-07-12**;
all timings below are taken at that mode.

- [ ] **1. Re-record the SD baseline at 25W** (~15 min, over SSH): re-run Part 7's timed
      commands (`colcon build --base-paths src`, native pytest, `docker pull`) on the
      microSD. Session 14's original SD numbers were taken at an unrecorded (likely 15W)
      mode — without this re-baseline the SD-vs-NVMe table is storage+power confounded.
- [ ] **2. Clone to NVMe — Path A below** (A0 backup → A1 install SSD [physical] →
      A2 device check → A3 JetsonHacks JetPack-7.2 compatibility gate → A4 clone scripts →
      A5 first boot with SD removed → A6 verify → A7 SD disposition).
- [ ] **3. Re-run the same numbers on NVMe at 25W** (step A8): fill both columns of the
      Part 7 baseline table, publish it in BLUEPRINT.md, then do Part 10 closeout and mark
      Session 14 ✅ in `Release1Todo.md`'s Session Index.
- [ ] **4. One manual HIL run on NVMe** (~10 min): `docs/runbooks/Mission1HILSession15.md`
      Parts 2–3 — confirms Nav2, the mission executor, and the CI-runner registration all
      survived the migration.
- [ ] **5. Then Session 16** (`Release1Todo.md` — implement `stage-4-hil`, retire
      `stage-4-isaac`) on the final storage + power configuration.

> **Rewritten 2026-07-12.** The original Part 9 said "re-flash to NVMe via SDK Manager."
> That still works and is preserved below as **Path B (fallback)**, but the primary method is
> now an **on-device clone (Path A)**: same system, same data, only the storage changes. Why
> that's better for us specifically: (1) it preserves everything Sessions 14–15 installed on
> the SD — ROS2, the GitHub runner *registration*, the Session 15 HIL prerequisites
> (`docs/runbooks/Mission1HILSession15.md` Part 1), the repo build, even the Jetson-side telemetry rows —
> so there is no Part 4–8 redo; (2) it gives a true apples-to-apples SD-vs-NVMe baseline for
> the Part 7 table (identical bits, only storage differs); (3) no host PC, no recovery mode.
> Risk asymmetry favors trying it: if the clone won't boot, the SD is untouched — pull the
> NVMe or fix boot order and you're back where you started, with Path B still available.

**Why now:** the module is a bare board on the desk — swapping storage is trivial now and a
pain later (Session 16 puts it in the robot chassis). Faster/steadier storage also makes the
CI runner's builds quicker. The dev kit's M.2 Key-M slot is **PCIe Gen3 x4** — far below a
Gen4 SSD's ceiling but a large jump over microSD, especially for random I/O (builds, apt,
DDS discovery caches).

### Path A — on-device clone (recommended)

**How it works (learning note):** on Orin-generation Jetsons the early boot chain (UEFI)
lives in **QSPI flash on the module itself**, not on the storage device. So "migrating" is
just: copy the partitions to the SSD, point the SSD's boot config at itself, and tell UEFI
to prefer NVMe. Two files matter on the cloned rootfs: `/boot/extlinux/extlinux.conf`
(kernel command line's `root=` must become the NVMe partition) and `/etc/fstab` (the `/`
entry must reference the SSD, not the SD).

- [ ] **A0 — Backup the SD first (non-negotiable).** Power off the Jetson, move the microSD
      to the x86 workstation's reader, and image it (compressed — the card is 128 GB but only
      ~18 GB is used):

  ```bash
  lsblk   # identify the SD card device — triple-check; dd on the wrong device is fatal
  sudo dd if=/dev/sdX bs=4M status=progress | gzip > ~/jetson_orin_backup_$(date +%F).img.gz
  # Restore later, if ever needed:
  #   gunzip -c ~/jetson_orin_backup_YYYY-MM-DD.img.gz | sudo dd of=/dev/sdX bs=4M status=progress
  ```

  Put the SD back in the Jetson and boot normally.
- [ ] **A1 — Install the SSD.** Power off completely and unplug. Flip the carrier board:
      the **M.2 Key-M 2280** slot is on the underside (the short 2230 Key-E slot next to it
      is for wifi cards — wrong slot). Insert the NVMe SSD, secure with the standoff screw.
      Boot from the SD as normal.
- [ ] **A2 — Verify device names.** `lsblk` — on this board the SD rootfs is
      **`/dev/mmcblk0p1`** (confirmed over SSH 2026-07-11) and the SSD should appear as
      **`nvme0n1`**, ideally unpartitioned. If the SSD auto-mounted anything:
      `sudo umount /dev/nvme0n1*`.
- [ ] **A3 — Check script compatibility BEFORE running.** The clone uses JetsonHacks'
      `migrate-jetson-to-ssd` scripts. **This runbook has not verified them on JetPack 7.2 /
      L4T r39.2** (they were written in the JetPack 5/6 era). Read the repo README + open
      issues for r39/JetPack-7 reports first, and check each script's `-h`/README for the
      exact source/target flag syntax — the flags shown in A4 are the intent (source = SD,
      target = NVMe), not gospel. If the repo looks abandoned or r39-incompatible, use Path B.
- [ ] **A4 — Run the clone (on the Jetson, ~20–45 min for the copy step):**

  ```bash
  git clone https://github.com/jetsonhacks/migrate-jetson-to-ssd
  cd migrate-jetson-to-ssd
  sudo bash make_partitions.sh   -s /dev/mmcblk0 -t /dev/nvme0n1  # partition table on SSD, rootfs expanded
  sudo bash copy_partitions.sh   -s /dev/mmcblk0 -t /dev/nvme0n1  # the long step
  sudo bash configure_ssd_boot.sh -s /dev/mmcblk0 -t /dev/nvme0n1 # fixes extlinux.conf root= + fstab on the SSD
  ```

  Pass source/target explicitly even though our SD happens to match the scripts' default —
  explicit beats default when a wrong guess dd's over the wrong disk.
- [ ] **A5 — First NVMe boot, the safe way.** Power off, **remove the microSD entirely**,
      power on. UEFI falls through to the only bootable device — the NVMe. This proves the
      SSD boots standalone with zero risk to the SD. (Alternative: hold **ESC** at boot →
      UEFI → Boot Manager → move NVMe above SD/mmc — do this later anyway if you ever
      re-insert the SD.)
- [ ] **A6 — Verify:**

  ```bash
  findmnt /                     # must show /dev/nvme0n1p1
  df -h /                       # full SSD capacity — if it shows ~SD-size instead:
                                #   sudo resize2fs /dev/nvme0n1p1
  cat /etc/nv_tegra_release     # L4T r39.2 still intact (jetson_release needs jetson-stats, not stock)
  systemctl status actions.runner.* --no-pager   # runner registration survived the clone
  ip a                          # same MAC → usually the same 10.42.0.x lease; re-check with
                                # `ip neigh show dev enp6s0` on the workstation if SSH fails
  ```
- [ ] **A7 — What to do with the SD card.** Prefer keeping it **out of the Jetson**, stored
      as a known-good offline backup. **Caution:** the clone can leave both devices with
      identical filesystem UUIDs/PARTUUIDs (depends on how the scripts create the SSD
      filesystem) — with both inserted, UUID-based resolution in fstab/initrd can grab the
      *SD's* partition and silently put you back on slow storage. If you re-insert the SD,
      verify `findmnt /` says nvme afterwards; wipe or re-purpose the SD once confident.
- [ ] **A8 — Fill the NVMe column** of the Part 7 baseline table: same timed
      `colcon build --base-paths src`, same `docker pull`, same pytest run. This is the
      payoff number for BLUEPRINT.md's SD-vs-NVMe comparison (Part 10).
- [ ] **A9 — If it doesn't boot:** remove the NVMe (or restore SD-first boot order) → the SD
      boots exactly as before. Skim the script repo's issues for your symptom once, then cut
      losses and use Path B — don't sink a session into debugging a hybrid boot state.

### Path B — fallback: fresh re-flash to NVMe via SDK Manager

The original method. Known-good (it's exactly the Part 3 process we already executed once),
but it wipes everything — budget ~1–2 h of reinstalls afterwards.

- [ ] Power off; install the SSD (Path A's A1) if not already installed.
- [ ] Re-flash JetPack 7.2 with SDK Manager exactly as in **Part 3**, but choose **NVMe** as
      the storage target this time. (Recovery mode → SDK Manager → OS image → target = NVMe.)
- [ ] First boot, then re-establish the network (**Part 4** — the shared connection recipe is
      unchanged; the Jetson gets a fresh `10.42.0.x` lease).
- [ ] Re-run the **smoke tests** (Part 5) — confirm `lsblk` shows rootfs on `nvme0n1`.
- [ ] Re-install **ROS2 Jazzy** (Part 6) and re-do the **timed build + docker pull** (Part 7),
      filling in the **NVMe column** of the baseline table.
- [ ] Re-register / restart the **CI runner** (Part 8) on the NVMe install (fresh OS = fresh
      runner registration; remove the stale runner entry in GitHub if it lingers).
- [ ] Re-run the **HIL prerequisites** (`docs/runbooks/Mission1HILSession15.md` Part 1):
      `ros-jazzy-navigation2`, `ros-jazzy-nav2-bringup`, `ros-jazzy-rmw-cyclonedds-cpp`,
      `python3-pil`, repo on `main`, `colcon build --base-paths src`. The Session 15 HIL run
      was done on the microSD install, so a fresh NVMe flash loses all of it. (Path A
      preserves all of this — one of the reasons it's Path A.)

> **SD hygiene reminder (from Release1Todo):** don't record rosbags/heavy logs to a microSD
> while it's the live rootfs — sustained writes wear SD cards. On NVMe this stops mattering.

---

## Part 10 — Close out Session 14

- [ ] Fill in both columns of the baseline table (Part 7) and drop the numbers into
      `BLUEPRINT.md` where the QEMU-vs-native / SD-vs-NVMe comparison lives.
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
- **Hostname:** still `localhost.localdomain` — the SDK Manager pre-config screen only asked
  for username/password this run, hostname got skipped. Fix with `sudo hostnamectl
  set-hostname jetson-orin` (plus updating `/etc/hosts`) whenever it's convenient; not urgent
  since SSH works fine via the DHCP IP (`10.42.0.217`) in the meantime.
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
