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
- [ ] Jetson Orin Nano Super Developer Kit (module + carrier board)
- [ ] Included DC power supply (**use the real supply, not a random USB-C charger** — sustained
      loads want the full wattage)
- [ ] **USB-C cable that carries data** (many cables are charge-only — a charge-only cable is
      the #1 cause of "recovery mode not detected"). Connects Jetson ⇄ workstation.
- [ ] microSD card, **64 GB or larger**, decent brand (Session 7 baseline lives here)
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

- [ ] Unpack the kit. Set the carrier board on something non-conductive (the antistatic bag or
      the cardboard tray — **not** bare metal or carpet).
- [ ] Locate and mentally label, using the printed card:
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
- [ ] Optional visual firmware clue: a brand-new **Super** kit ships with recent firmware, so
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

- [ ] Confirm the host OS is 24.04 (it is — this is your dev box):
  ```bash
  cat /etc/os-release   # expect: VERSION="24.04..."
  ```
- [ ] Download **SDK Manager** (`.deb`) from <https://developer.nvidia.com/sdk-manager> and
      install it:
  ```bash
  cd ~/Downloads
  sudo apt install ./sdkmanager_*_amd64.deb
  ```
- [ ] Launch it once to confirm it opens and log in with your NVIDIA Developer account:
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

---

## Part 3 — Flash JetPack 7.2 to microSD (SDK Manager)

> **This is the one part with a physically risky step (shorting header pins). Go slowly and
> confirm pin numbers against the printed card.**

### 3.1 Put the Jetson into recovery mode
- [ ] Make sure the Jetson is **fully powered off and unplugged** from DC. Wait ~10 s for
      capacitors to discharge.
- [ ] Insert the **microSD** into the module slot (if not already in from Part 1).
- [ ] Connect the **USB-C cable** from the Jetson's device-mode USB-C port to a USB port on the
      workstation.
- [ ] **Short the recovery pins:** using a jumper/paperclip, bridge **`FC REC` to `GND`** on the
      J14 header (the two pins you noted in Part 1). Hold the short.
- [ ] **While holding the short**, plug the **DC power** back in. Keep the short for ~2–3 s
      after power comes on, then remove the jumper.
  > Some Super carriers have a labeled **FC REC push-button** instead — if so, the sequence is:
  > hold FC REC, apply power, keep holding 2–3 s, release. Same idea, no jumper.
- [ ] Verify from the **workstation** that the board enumerated in recovery mode:
  ```bash
  lsusb | grep -i nvidia
  # expect a line like: ID 0955:7523 NVIDIA Corp. APX
  ```
  If you see `0955:7523`, you're in recovery mode. If nothing shows: unplug, wait, re-seat the
  USB-C cable (try a known-good data cable), and retry the short-then-power sequence.

### 3.2 Flash with SDK Manager
- [ ] In SDK Manager (already logged in):
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
- [ ] **Storage device** (critical): select **microSD** as the target runtime device — **not**
      NVMe, not eMMC, for this first pass. (You migrate to NVMe in Part 9.)
  > **If microSD is *not* offered as a target device** in your SDK Manager build: SDK Manager
  > on some releases only targets NVMe/USB. In that case, either (a) use the **Jetson ISO on
  > USB** fallback below to install to microSD, or (b) accept flashing straight to **NVMe now**
  > and treat NVMe as your baseline (you were going there anyway — you'd just lose the
  > microSD-vs-NVMe comparison). Decide based on how much you care about the SD baseline number.
- [ ] **Pre-configure the OS account (this is what makes first boot headless):** SDK Manager
      will offer a **"Pre-Config" / manual OEM setup** option before flashing. Fill in:
  - Username (e.g. `mike`)
  - Password
  - **Hostname** — set something memorable, e.g. `jetson-orin` (you'll use `jetson-orin.local`)
  - Timezone / locale / keyboard
  > Skipping this leaves the board waiting at the interactive **OEM setup wizard** on first
  > boot, which needs a monitor+keyboard. Filling it in = the board boots straight to a
  > login-ready, SSH-able system.
- [ ] Start the flash. **OS-only flash to microSD ≈ 20–30 min.** Do not disturb the USB-C
      cable or power during this.
- [ ] When SDK Manager reports success: **disconnect the USB-C cable.**

### 3.3 First boot
- [ ] Power-cycle the Jetson **without** the recovery short: unplug DC, wait 10 s, plug DC back
      in. (No jumper this time.)
- [ ] Give it ~60 s to boot. Proceed to Part 4 to reach it over the network.
- [ ] *(Fallback)* If anything looks wrong, attach the monitor (DisplayPort) + USB keyboard now
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

- [ ] Cable the Jetson's Ethernet port directly to the workstation's Ethernet port.
- [ ] On the **workstation**, create a shared connection on the Ethernet interface (replace
      `enp5s0` with the name you found in Part 2):
  ```bash
  nmcli connection add type ethernet ifname enp5s0 con-name jetson-share ipv4.method shared
  nmcli connection up jetson-share
  ```
  This assigns the workstation `10.42.0.1` and starts handing out DHCP + NAT on that port.
  Your Wi-Fi connection is untouched and remains the internet source.
- [ ] Find the Jetson's IP (it will be something like `10.42.0.x`):
  ```bash
  # Option A — mDNS by the hostname you set in SDK Manager:
  ping jetson-orin.local

  # Option B — scan the shared subnet:
  ip neigh show dev enp5s0            # shows learned neighbors
  # or, if nmap is installed:
  nmap -sn 10.42.0.0/24
  ```
- [ ] SSH in (use `.local` if mDNS works, otherwise the numeric IP):
  ```bash
  ssh mike@jetson-orin.local
  # or: ssh mike@10.42.0.<n>
  ```
- [ ] Once in, confirm the Jetson has **internet through the shared link**:
  ```bash
  ping -c 3 nvidia.com
  ```
  If ping fails but SSH worked, the NAT/DNS side of sharing isn't up — see troubleshooting.
- [ ] **(Recommended) set up passwordless SSH** so later steps and the CI runner are smooth:
  ```bash
  # on the workstation:
  ssh-copy-id mike@jetson-orin.local
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

- [ ] **OS is what we expect:**
  ```bash
  cat /etc/os-release          # VERSION="24.04..."; UBUNTU_CODENAME=noble
  uname -a                     # aarch64
  ```
- [ ] **JetPack / L4T version:**
  ```bash
  cat /etc/nv_tegra_release    # expect R39 (revision 2...) == L4T r39.2 == JetPack 7.2
  # If installed: dpkg-query --show nvidia-jetpack
  ```
- [ ] **GPU / SoC live stats (Jetson's equivalent of nvidia-smi):**
  ```bash
  sudo tegrastats            # live CPU/GPU/EMC/thermal; Ctrl-C to stop
  # nicer TUI if you install it:
  sudo pip3 install jetson-stats && sudo reboot   # then run: jtop
  ```
- [ ] **Power mode / clocks** (Super kit supports a higher "MAXN SUPER" mode):
  ```bash
  sudo nvpmodel -q            # show current power model
  sudo nvpmodel -m 0          # max performance (confirm mode number via -q list)
  sudo jetson_clocks          # pin clocks to max (optional, for benchmarking Part 7)
  ```
- [ ] **CUDA present (only if you added SDK components):**
  ```bash
  nvcc --version              # or: ls /usr/local/cuda*/bin
  ```
- [ ] **Thermals sane at idle:** in `tegrastats`/`jtop`, confirm temps are reasonable (tens of
      °C idle, not thermal-throttling).
- [ ] **Storage — confirm you're actually on the microSD** and note free space:
  ```bash
  lsblk                       # rootfs should be on mmcblk* (microSD), not nvme*
  df -h /                     # note total/free
  ```
- [ ] **Networking basics:** `hostname`, `ip -br addr`, `ping -c3 8.8.8.8`.

Record anything odd here before continuing.

---

## Part 6 — Install ROS2 Jazzy

**Why Jazzy:** matches the workstation and the stage-2 Docker image exactly — one distro across
sim, CI, and hardware. Run on the Jetson over SSH.

- [ ] Enable the `universe` repo and prerequisites:
  ```bash
  sudo apt update && sudo apt install -y software-properties-common curl
  sudo add-apt-repository universe -y
  ```
- [ ] Add the ROS2 apt source (current `ros-apt-source` package method):
  ```bash
  export ROS_APT_SOURCE_VERSION=$(curl -s https://api.github.com/repos/ros-infrastructure/ros-apt-source/releases/latest \
    | grep -F "tag_name" | awk -F\" '{print $4}')
  curl -L -o /tmp/ros2-apt-source.deb \
    "https://github.com/ros-infrastructure/ros-apt-source/releases/download/${ROS_APT_SOURCE_VERSION}/ros2-apt-source_${ROS_APT_SOURCE_VERSION}.$(. /etc/os-release && echo $VERSION_CODENAME)_all.deb"
  sudo apt install -y /tmp/ros2-apt-source.deb
  sudo apt update
  ```
- [ ] Install ROS2 Jazzy base + dev tools + CycloneDDS (matching this project's RMW):
  ```bash
  sudo apt install -y ros-jazzy-ros-base ros-dev-tools ros-jazzy-rmw-cyclonedds-cpp
  ```
  > `ros-base` (not `desktop`) — the Jetson is headless; we don't want RViz/Gazebo GUI stacks
  > on it. It's a runtime/build target and a CI runner, not a visualization host.
- [ ] Wire the environment to match the workstation's `.bashrc` conventions:
  ```bash
  echo 'source /opt/ros/jazzy/setup.bash' >> ~/.bashrc
  echo 'export RMW_IMPLEMENTATION=rmw_cyclonedds_cpp' >> ~/.bashrc
  source ~/.bashrc
  ```
- [ ] Sanity check:
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

- [ ] Get the repo onto the Jetson and install build deps:
  ```bash
  sudo apt install -y git python3-colcon-common-extensions python3-pip
  git clone https://github.com/sdfinn/autonomous-fleet-testbed.git ~/autonomous-fleet-testbed
  cd ~/autonomous-fleet-testbed
  # If the package has rosdep-managed deps:
  sudo apt install -y python3-rosdep && sudo rosdep init 2>/dev/null; rosdep update
  rosdep install --from-paths src --ignore-src -r -y || true
  ```
- [ ] **Timed native colcon build** (this is a recorded number):
  ```bash
  cd ~/autonomous-fleet-testbed
  time colcon build --symlink-install
  source install/setup.bash
  ```
  Record the `real` time. This is the number that retires QEMU: compare it to the
  "Stage 2 arm64 build time (QEMU)" line CI currently prints (~24–29 min emulated).
- [ ] **Timed first `docker pull` of the stage-2 arm64 image** (proves the Jetson can pull and
      run the CI image natively):
  ```bash
  sudo apt install -y docker.io && sudo usermod -aG docker $USER   # then re-login (SSH out/in)
  time docker pull ghcr.io/sdfinn/autonomous-fleet-testbed:latest
  ```
- [ ] Run the Python unit tests natively (same command the x86 loop uses):
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
  | `apt install ros-jazzy-ros-base` wall time | | |
  | `colcon build --symlink-install` (`real`) | | |
  | first `docker pull` of stage-2 image | | |
  | `df -h /` free space | | |

---

## Part 8 — Add the Jetson as a self-hosted CI runner

> **Only start this if Part 7's native build was clean.** The point is to replace the slow
> emulated `stage-2-arm64` (QEMU on `ubuntu-latest`) with a *native* arm64 build on the Jetson.

**Current state (for reference):** `stage-2-arm64` in `.github/workflows/ci.yml` runs on
`ubuntu-latest` and cross-builds for `linux/arm64` via `docker/setup-qemu-action` — that's the
~24–29 min emulated build we're retiring.

### 8.1 Register the runner (on the Jetson)
- [ ] In a browser: repo → **Settings → Actions → Runners → New self-hosted runner** → pick
      **Linux / ARM64**. GitHub shows a download + `config.sh` snippet with a **registration
      token** (tokens expire — generate it right before you use it).
- [ ] On the Jetson, follow that snippet, but set **labels** so CI can target it precisely:
  ```bash
  mkdir -p ~/actions-runner && cd ~/actions-runner
  # curl the runner tarball URL from the GitHub page, then:
  tar xzf actions-runner-linux-arm64-*.tar.gz
  ./config.sh --url https://github.com/sdfinn/autonomous-fleet-testbed \
    --token <TOKEN_FROM_GITHUB> \
    --labels self-hosted,arm64,jetson,orin-nano \
    --name jetson-orin
  ```
- [ ] Install it as a service so it survives reboots (mirrors the x86 runner setup):
  ```bash
  sudo ./svc.sh install
  sudo ./svc.sh start
  sudo ./svc.sh status
  ```
- [ ] Confirm it shows **Idle** under Settings → Actions → Runners.

### 8.2 Point `stage-2-arm64` at the Jetson (native, no QEMU)
- [ ] Edit `.github/workflows/ci.yml`, `stage-2-arm64` job:
  - Change `runs-on: ubuntu-latest` → `runs-on: [self-hosted, arm64, jetson]`
  - **Remove the QEMU step** (native arm64 doesn't need emulation):
    ```yaml
    # DELETE these two lines — native arm64 build needs no emulation:
    # - name: Set up QEMU
    #   uses: docker/setup-qemu-action@v3
    ```
  - Keep buildx, GHCR login, and the build-push step. `platforms: linux/arm64` is now native.
  - Update the timing echo text from "(QEMU)" to "(native Jetson)" so the summary reads true.
- [ ] Commit on a branch and push; watch the run:
  ```bash
  git checkout -b session-14-jetson-runner
  git add .github/workflows/ci.yml
  git commit -m "ci(session-14): build stage-2-arm64 natively on Jetson runner, retire QEMU"
  git push -u origin session-14-jetson-runner
  gh run watch
  ```
- [ ] Confirm `stage-2-arm64` ran **on the Jetson** and the native build time roughly matches
      your Part 7 `colcon`/`docker` numbers (and beats the old QEMU time). If it's flaky, revert
      the `runs-on` change and keep QEMU until the hardware path is solid — don't leave CI red.

---

## Part 9 — Migrate microSD → NVMe SSD

**Why now:** the module is a bare board on the desk — swapping storage is trivial now and a
pain later (Session 15 puts it in the robot chassis). Faster/steadier storage also makes the
CI runner's builds quicker.

- [ ] Power off the Jetson. Install the **NVMe M.2 2280 SSD** into the Key-M slot (screw it
      down at the standoff).
- [ ] Re-flash JetPack 7.2 with SDK Manager exactly as in **Part 3**, but choose **NVMe** as the
      storage target this time. (Recovery mode → SDK Manager → OS image → target = NVMe.)
- [ ] First boot, then re-establish the network (**Part 4** — the shared connection recipe is
      unchanged; the Jetson gets a fresh `10.42.0.x` lease).
- [ ] Re-run the **smoke tests** (Part 5) — confirm `lsblk` now shows rootfs on `nvme0n1`, not
      `mmcblk*`.
- [ ] Re-install **ROS2 Jazzy** (Part 6) and re-do the **timed build + docker pull** (Part 7),
      filling in the **NVMe column** of the baseline table. Expect meaningfully faster build and
      pull times than microSD.
- [ ] Re-register / restart the **CI runner** (Part 8) on the NVMe install (fresh OS = fresh
      runner registration; remove the stale runner entry in GitHub if it lingers).

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
- [ ] Note the optional Jetson-in-the-loop-with-sim stretch goal is **not** required for
      Session 14 completion (per the plan) — only attempt if time remains.
- [ ] Commit the doc updates:
  ```bash
  git add Release1Todo.md BLUEPRINT.md JetsonInstallSession14.md
  git commit -m "docs(session-14): Jetson Orin Nano install runbook + baseline; correct JetPack 7.2 flash method"
  ```

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
