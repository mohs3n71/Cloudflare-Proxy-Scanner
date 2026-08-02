# Cloudflare Proxy Scanner

[![Tests](https://github.com/mohs3n71/Cloudflare-Proxy-Scanner/actions/workflows/tests.yml/badge.svg)](https://github.com/mohs3n71/Cloudflare-Proxy-Scanner/actions/workflows/tests.yml)

A complete desktop and CLI application for finding usable Cloudflare proxy IPs and managing direct proxy configurations. It supports VLESS, VMess, Trojan, and Shadowsocks, combining parallel IP scanning, a persistent proxy library, custom Xray fragment testing, latency and speed measurement, saved results, and a polished desktop GUI.

### What Makes It Different

To the best of our knowledge, this is the first Cloudflare proxy scanner designed to bring these capabilities together:

- **Custom fragment testing:** scan with 24 mode-specific defaults or supply your own Xray packet, interval, and length variations to find settings that work best on changing networks.
- **Built-in Xray runner:** the application launches, manages, and stops Xray itself, so a separate Xray client such as v2rayN is not required.
- **Mobile configuration import:** display any generated VLESS, VMess, or Trojan configuration as a QR code directly from the results table.
- **A polished, full-featured GUI:** scanning, live progress, sortable results, speed tests, fragment optimization, configuration management, logs, and a local SOCKS proxy are available in one interface.

The project also provides a CLI, Windows/Linux/macOS launch scripts, multi-platform standalone releases, persistent runner settings, CSV exports, and automated tests.

> Use this only with proxy accounts and servers you own or are allowed to test.

## English Guide

### What This App Does

- Generates random IPs from Cloudflare IPv4 ranges.
- Tests each IP by starting a temporary local Xray process.
- Checks whether your selected config works through that Cloudflare IP.
- Shows live scan progress and passed IPs sorted by ping.
- Saves scan results to CSV files.
- Loads saved results for later speed tests.
- Runs download, upload, or both speed tests.
- Lets you right-click selected IPs and speed-test only those rows.
- Generates replacement configs using the working IPs.
- Saves GUI logs to `logs`.
- Can publish standalone Windows, Linux, and macOS releases for x64, x86, and ARM64 targets where supported.
- Includes an About tab with the application version, bundled Xray version, and project GitHub link.
- Includes a persistent mild dark mode that can be enabled from the About tab.
- Includes a persistent Non-Cloudflare Tests tab for bulk-importing direct proxy links, testing them sequentially, and running a selected profile with Xray.

### Supported Config Types

The IP scanner supports WebSocket (`type=ws` / `net=ws`) and XHTTP (`type=xhttp` / `net=xhttp`) configs for:

- `vless://`
- `vmess://`
- `trojan://`

The older `splithttp` transport name is accepted as an alias for XHTTP. For XHTTP profiles, the app preserves `host`, `path`, `mode`, and the optional raw JSON `extra` object when scanning, running Xray, generating result configurations, and creating QR codes.

The Non-Cloudflare Tests tab and Xray Runner additionally support direct endpoints using TCP, gRPC, TLS, and Reality, plus native `ss://` Shadowsocks links. Shadowsocks links that require SIP003 plugins are rejected because Xray core does not run those external plugins.

Put config text files in:

```text
configs
```

Each config file must use the `.config` extension and can otherwise have any name, for example:

```text
configs/my-vless.config
configs/test-vmess.config
configs/trojan-server.config
```

Each file should contain at least one supported config line. If there is no valid config, scan and speed-test actions are disabled until you add one.

### Appearance

Open the `About` tab and enable `Dark mode` to switch the complete interface to a soft charcoal theme. The preference is saved in `settings.json` and restored the next time the app starts. Disable the same option to return to light mode.

### Project Folders

- `bin/xray`: local Xray runtime cache. Launch scripts download the correct official binary when missing; downloaded files are ignored by Git.
- `tools`: shared Xray download and native release-build tooling.
- `proxy_tester`: Python application code.
- `configs`: your config text files. Real configs are ignored by Git.
- `configs/proxy-library.json`: the saved bulk proxy library and its latest latency/speed results.
- `output`: scan CSVs and generated config files.
- `logs`: GUI scan and speed-test logs.
- `tests`: unit tests.
- `dist`: temporary PyInstaller output.
- `release`: final standalone release artifacts.
- `build`: PyInstaller temporary build folder.

### Requirements

For normal source usage:

- Python 3.10 or newer.
- Internet access the first time a launch script downloads Xray from the official XTLS/Xray-core release.

Install the Python dependency once:

```sh
python -m pip install -r requirements.txt
```

The launch scripts cache the current platform binary as:

```text
bin\xray\xray.exe   (Windows)
bin/xray/xray
```

On each launch, the app checks the full official Xray release list. If a newer published release exists, including a prerelease, it replaces the cached binary automatically. If GitHub is temporarily unreachable, the existing cached binary remains usable.

The GUI launcher shows a startup progress window while checking Xray. When an update is downloaded, the progress bar shows its percentage (or transferred megabytes when the server does not provide a total size). If checking or downloading the update fails and a local Xray binary already exists, the app continues with that binary. If no binary exists, an error explains where to copy it manually.

This startup check is used only when running from source through `run_gui.bat` or `run_gui.sh`. Standalone release executables use their bundled Xray version and do not check for or download Xray updates at startup.

You can also prepare Xray manually for the current machine:

```sh
python tools/xray_release.py --if-missing
```

### Run The GUI

Windows:

```bat
run_gui.bat
```

Linux:

```sh
chmod +x run_gui.sh
./run_gui.sh
```

macOS:

```sh
chmod +x run_gui.sh
./run_gui.sh
```

The Windows GUI launcher uses `pythonw.exe`, so it opens the GUI without keeping a console window beside it.

### GUI Sections

**Config**

- Select an existing config file from `configs`.
- Add a new `vless://`, `vmess://`, `trojan://`, or `ss://` config using the UI.
- Edit or rename the selected configuration. Changes are validated before the original file is replaced.
- Remove the selected configuration after confirming the deletion.
- If no config exists, scan and speed-test buttons stay disabled.

**Scan New IPs**

- Choose `Random from all CF ranges`.
- Choose `All IPs from all CF ranges` to scan every usable IP in every Cloudflare range.
- Choose `Random from one range` or `Every IP in one range`. The selector includes built-in Cloudflare ranges and saved custom ranges.
- Choose `Random IPs from custom ranges` to sample across all custom CIDRs together.
- Use `Edit Ranges` to add, edit, or clear persistent custom IPv4 CIDRs. Enter one CIDR per line; bare IP addresses are accepted as `/32` ranges.
- Set IP count for random modes. The default is `1000`; the count is ignored for full all-range scans.
- Set scan parallelism: `10`, `20`, `50`, `100`, or `200`. Default is `50`.
- Set scan timeout. Default is `2000ms`.
- Start or stop a scan.
- Optionally enable `Speed test after scan` to speed-test passed IPs immediately after a completed scan.
- `Optimized mode for restricted networks` runs every end-to-end IP check with the built-in `fingerprint: unsafe`, cipher-suite, and two-layer FinalMask preset. It requires a TLS configuration.
- The same preset is used for saved-result speed tests while this scanner option is active. Standard speed-test fragmentation controls are disabled and ignored.

**Saved Results and Speed Test**

- Select a saved output CSV.
- The table loads the IPs from that file.
- Run speed tests on the whole selected output.
- Create replacement configs from the selected output.

**Non-Cloudflare Tests**

- Paste multiple `vless://`, `vmess://`, `trojan://`, or `ss://` links at once. Duplicate links are ignored and invalid links are reported.
- Configurations and their latest latency, download, upload, status, and error state are saved in `configs/proxy-library.json`.
- Each run writes a diagnostic `proxy-library-speed-test-*.log` file in `logs`.
- Select one or more rows to test them, or leave the selection empty to test the complete library.
- Download, upload, and combined tests run sequentially to avoid competing for bandwidth.
- Fragmentation is disabled by default. Enable it to apply custom packets, interval, and length values to every selected proxy test through Xray's `dialerProxy`.
- Fragment defaults are `Packets: tlshello`, `Interval: 1-2`, and `Length: 5-10`; fragment controls are locked while testing.
- `tlshello` targets TLS-based profiles. For plain non-TLS Shadowsocks links, use a numeric packets range such as `1-3` when fragmentation is needed.
- The active row is highlighted and the table remains sortable by every column while testing.
- `Stop` terminates the active temporary Xray process immediately.
- Double-click a row, use the button, or choose `Run with Xray` from the context menu to start that original endpoint in Xray Runner.
- Clearing or rerunning one direction preserves the other direction's existing speed result.

**Xray Runner**

- Run Xray locally with one selected IP and the selected proxy config.
- Default SOCKS port is `1080`.
- Enable `Share on network (0.0.0.0)` if other devices on your LAN should use the SOCKS port.
- Choose how the runner handles Windows system proxy: `Set system proxy`, `Clear system proxy`, or `Do not touch system proxy`.
- Fragmentation is disabled by default in the Xray Runner.
- Fragment defaults are `Packets: tlshello`, `Interval: 1-2`, and `Length: 5-10`.
- Disable `Enable fragment` to run the selected IP without fragment settings. When enabled, Xray's `dialerProxy` fragments the real outer TLS ClientHello used to connect to the selected proxy IP.
- `Optimized mode for restricted networks` applies the built-in native-TLS preset: `fingerprint: unsafe`, an explicit cipher-suite list, and two ordered FinalMask fragment layers. It requires a TLS configuration.
- While optimized mode is enabled, standard fragment controls and the standard fragment scanner are disabled and their values are not included in runner, export, or runner speed-test configurations.
- Use `Start Xray` and `Stop Xray` to control the local runner.
- Use `Export Xray Config` to save the complete runner configuration as JSON, including fragmentation when enabled.
- While Xray is running, IP, port, sharing, and fragment controls are locked.
- Set runner speed-test size and timeout in this tab.
- Use `Test Download` or `Test Upload` to test the selected runner IP. Results are shown in separate result boxes.
- Use `Start Fragment Scan` to try 24 mode-specific fragment variations, or custom variations. Upload scans favor larger slices and shorter delays to reduce fragmentation overhead.
- Use `Stop Fragment Scan` to stop the fragment scanner and kill the active Xray test process immediately.
- Fragment scan results include ping plus speed, are shown in a sortable table, are saved as CSV in `output`, and the best result is saved per IP/config/mode for later reuse.
- Fragment scan CSVs are not shown in the first tab's saved-output selector because they are not normal IP scan/speed-test outputs.
- `Apply Best Saved Result` applies the saved fragment and restarts Xray automatically if the runner is already active.
- `Apply Best Saved Result` is disabled while a fragment scan is active.
- Custom fragment variations can be entered manually or loaded from a file. Supported line formats are `packets,interval,length` and `packets=..., interval=..., length=...`; JSON arrays of objects are also accepted.
- Xray stdout/stderr logs are shown live in the runner tab.

**About**

- Shows the application version, bundled Xray version, and GitHub repository.
- `Check for Updates` compares the installed version with the latest GitHub release and opens its download page when an update is available.

### Table Actions

The result table is sortable by clicking column headers:

- Ping
- IP
- Download Mbps
- Upload Mbps

Sorting stays active while scanning or speed testing.
The active sort header is marked with `▶` and shows `▲` for ascending or `▼` for descending order.

Use `Remove Failed Results (-1)` to remove any row where latency, download, or upload is `-1`.

Right-click selected rows to open actions:

- `Test Download Speed`
- `Test Upload Speed`
- `Test Download and Upload`
- `Run Selected IP with Xray`
- `Copy IP`
- `Copy Proxy Configuration`
- `Show Configuration QR Code`

You can select multiple rows with Ctrl/Shift and speed-test only those selected IPs. The IP currently being tested is highlighted.

### Mobile QR Code Import

The results table can generate a mobile-ready QR code for any tested IP:

1. Select a valid configuration in `Proxy Configuration`.
2. Select exactly one IP in the results table.
3. Right-click the row and choose `Show Configuration QR Code`.
4. Scan the displayed code with a compatible mobile proxy client.

The generated configuration supports VLESS, VMess, and Trojan over WebSocket or XHTTP. It preserves the active profile's credentials, port, TLS settings, SNI, fingerprint, ALPN, transport host/path, and XHTTP `mode`/`extra` settings while replacing the server address with the selected IP.

QR generation happens entirely on the local computer. The configuration and its credentials are not sent to an online QR service. The QR window also provides `Copy Configuration` as a text-import fallback. The menu action is disabled when no valid configuration is active or when more than one IP is selected.

Standalone releases include QR support. When running from source, install the dependency with `python -m pip install -r requirements.txt`.

### Scan Behavior

During a scan:

- The progress bar updates live.
- Passed IPs appear in the table.
- Rows are sorted by the current selected column.
- Stop kills active Xray processes and cancels pending tests.
- Completed passing results are saved.

Scan outputs are saved to:

```text
output/working-cloudflare-proxy-ips-YYYYMMDD-HHMMSS.csv
output/working-cloudflare-proxy-ips-latest.csv
```

### Speed Test Behavior

Speed tests run one IP at a time.

Available modes:

- Download
- Upload
- Both

Default speed settings:

- Size: `1 MB`
- Timeout: `7000ms`
- Fragmentation is disabled by default and can be enabled for speed tests.
- Speed-test fragment defaults are `Packets: tlshello`, `Interval: 1-2`, and `Length: 5-10`, targeting the actual TLS ClientHello with relatively low delay.

Speed test target:

```text
https://speed.cloudflare.com
```

If a speed test fails:

- The failed speed value becomes `-1`.
- If only upload fails, download is kept.
- If only download fails, upload is kept.
- The failure reason is written to the GUI log and the log file.

Upload tests first confirm a 256 KiB probe and then upload the remaining requested data under one overall timeout. If the remainder times out, the confirmed bytes are used to show a conservative partial upload speed and a warning is written to the log. A failure before the probe is confirmed still produces `-1`.

Download tests count each received chunk. If a download times out after data has arrived, those confirmed bytes are used to show a partial download speed with a log warning. A timeout before any data arrives still produces `-1`.

Speed-test outputs are saved to:

```text
output/speed-test-cloudflare-proxy-ips-YYYYMMDD-HHMMSS.csv
output/speed-test-cloudflare-proxy-ips-latest.csv
```

### Logs

Every GUI scan or speed test creates a log file in:

```text
logs
```

Logs include:

- Run start time.
- Selected source.
- Speed size and timeout.
- Passed and failed IPs.
- Upload/download failure details.
- Cloudflare HTTP status details when available.

If upload tests fail often, check the newest file in `logs`.

### Generate Configs From Working IPs

Select an output CSV and click:

```text
Generate Proxy Configurations
```

The generated file is saved in `output`.

The app preserves the selected protocol:

- VLESS input creates VLESS links.
- VMess input creates VMess links.
- Trojan input creates Trojan links.

### Run The CLI

Windows:

```bat
run_test.bat
```

You can also scan a fixed number of random IPs from all ranges:

```bat
run_test.bat 1000
```

CLI menu:

1. Random IPs from all Cloudflare ranges
2. Random IPs from one selected Cloudflare range
3. Speed test IPs from a saved output file
4. Create configs from a saved output file
5. Settings
6. Exit

Submenus accept:

```text
0
b
back
```

Set `NO_COLOR=1` if you want plain terminal output without colors.

### Run Tests

Windows:

```bat
run_tests.bat
```

Direct Python command:

```bat
python -m unittest discover -s tests
```

Install the development dependencies and run the same branch-coverage check used by CI:

```bat
python -m pip install -r requirements-dev.txt
python -m coverage run -m unittest discover -v
python -m coverage report
```

CI requires at least 70% branch coverage. Declarative Tk window construction is excluded, while GUI behavior, workers, runner lifecycle, QR handling, platform integration, and release tooling remain measured.

### Build A Standalone Executable

The project uses PyInstaller for native one-file builds. Every build downloads the matching official Xray release into `build/runtime`, then bundles it into the application. Xray binaries are not stored in Git.

Important:

- PyInstaller cannot cross-compile. Build each target on its matching operating system and CPU architecture.
- Windows x86 can be built on x64 Windows by using a 32-bit Python interpreter.
- macOS output is an unsigned `.app` packaged as a ZIP, so Gatekeeper may require manual approval.
- Runtime `configs`, `output`, and `logs` are created beside the executable.

Install PyInstaller first:

```sh
python -m pip install pyinstaller
```

Windows build:

```bat
build_windows.bat
set PYTHON_EXE=C:\path\to\32-bit-python.exe
build_windows.bat x86
build_windows.bat arm64
```

The x86 command requires a 32-bit Python interpreter. Run the ARM64 command on Windows ARM64 with ARM64 Python.

Linux build:

```sh
chmod +x build_linux.sh
./build_linux.sh
./build_linux.sh arm64
```

macOS build:

```sh
chmod +x build_macos.sh
./build_macos.sh
```

Final artifacts are written to `release`, for example:

```text
release/cloudflare-proxy-scanner-windows-x64.exe
release/cloudflare-proxy-scanner-linux-arm64
release/cloudflare-proxy-scanner-macos-arm64.zip
```

Set `XRAY_VERSION` to pin an Xray release; otherwise the newest published official release is used, including prereleases:

```sh
XRAY_VERSION=v26.3.27 ./build_linux.sh
```

### Publish Multi-Platform GitHub Releases

`.github/workflows/release.yml` builds these targets in parallel:

| Operating system | Architectures |
| --- | --- |
| Windows | x64, x86, ARM64 |
| Linux | x64, ARM64 |
| macOS | Intel x64, Apple Silicon ARM64 |

Push a version tag to build and publish a GitHub release automatically:

```sh
git tag v1.0.0
git push origin v1.0.0
```

You can also run `Build Release` manually from GitHub Actions and enter a release tag and optional Xray version. Linux x86 is supported by the downloader and local build tooling but is not included in the automatic matrix because GitHub does not provide a standard hosted Linux x86 runner.

### Running The Standalone App

Put the executable in a folder and run it. The app creates:

```text
configs
output
logs
```

Add your config file inside `configs`, then restart or refresh/use the app.

### v2rayN Compatibility

You do not need v2rayN while testing.

If v2rayN is open, it should not interfere if these are disabled:

- System Proxy
- TUN mode
- Global routing
- DNS hijack

The app uses its own temporary local Xray proxy for each tested IP.

### Troubleshooting

**No scan or speed-test button is enabled**

Add a valid configuration in `configs` or use the `Add Configuration` button.

**Upload speed tests fail**

Try:

- Use upload-only mode.
- Lower speed size to `0.25 MB`.
- Increase speed timeout above `7000ms`.
- Check the newest log file in `logs`.

**Xray download fails**

Check internet access and try the downloader directly to see the error:

```sh
python tools/xray_release.py --if-missing
```

**A native build says PyInstaller is missing**

Install it for the same Python used by the script:

```sh
python -m pip install -r requirements.txt pyinstaller
```

**Built app opens but cannot test**

Make sure you added a config file beside the executable:

```text
configs/your-config.config
```

---

# راهنمای فارسی

این برنامه برای تست IPهای کلادفلر با کانفیگ‌های Xray شما ساخته شده است. برنامه از کانفیگ‌های WebSocket و XHTTP با فرمت‌های `vless://`، `vmess://` و `trojan://` پشتیبانی می‌کند، IPهای رندوم کلادفلر را تست می‌کند، IPهای سالم را ذخیره می‌کند و بعدا می‌تواند روی همان خروجی‌ها تست سرعت انجام دهد.

> فقط روی اکانت‌ها و سرورهایی استفاده کنید که مالک آن‌ها هستید یا اجازه تست دارید.

## این برنامه چه کاری انجام می‌دهد؟

- تب «درباره برنامه» شماره نسخه برنامه، نسخه دقیق Xray و لینک مخزن GitHub را نمایش می‌دهد.
- از رنج‌های IPv4 کلادفلر IP رندوم می‌سازد.
- برای هر IP یک پردازش موقت Xray اجرا می‌کند.
- تست می‌کند کانفیگ انتخاب‌شده با آن IP کار می‌کند یا نه.
- پیشرفت اسکن و IPهای سالم را زنده نمایش می‌دهد.
- خروجی اسکن را در فایل CSV ذخیره می‌کند.
- خروجی‌های قبلی را برای تست سرعت دوباره لود می‌کند.
- تست سرعت دانلود، آپلود یا هر دو را انجام می‌دهد.
- با راست‌کلیک روی IPهای انتخاب‌شده می‌توانید فقط همان IPها را تست سرعت کنید.
- از روی IPهای سالم کانفیگ جدید می‌سازد.
- لاگ‌های GUI را داخل پوشه `logs` ذخیره می‌کند.
- می‌تواند به فایل اجرایی مستقل برای ویندوز یا لینوکس تبدیل شود.
- دارای حالت تاریک ملایم و دائمی است که از تب «درباره برنامه» فعال می‌شود.

## فرمت‌های پشتیبانی‌شده

برنامه از انتقال‌های WebSocket با مقدار `ws` و XHTTP با مقدار `xhttp` برای کانفیگ‌های زیر پشتیبانی می‌کند:

- `vless://`
- `vmess://`
- `trojan://`

نام قدیمی `splithttp` نیز به‌عنوان نام جایگزین XHTTP پذیرفته می‌شود. در کانفیگ XHTTP، برنامه مقادیر `host`، `path`، `mode` و شیء JSON اختیاری `extra` را هنگام اسکن، اجرای Xray، ساخت کانفیگ خروجی و QR Code حفظ می‌کند.

تب `Non-Cloudflare Tests` و بخش Xray Runner علاوه بر این موارد، آدرس‌های مستقیم با انتقال TCP یا gRPC و امنیت TLS یا Reality را نیز پشتیبانی می‌کنند. لینک‌های استاندارد `ss://` برای Shadowsocks هم قابل استفاده هستند؛ کانفیگ‌های Shadowsocks وابسته به پلاگین‌های خارجی SIP003 پشتیبانی نمی‌شوند، چون Xray Core آن پلاگین‌ها را اجرا نمی‌کند.

فایل‌های کانفیگ را داخل این پوشه قرار دهید:

```text
configs
```

اسم فایل‌ها می‌تواند هر چیزی باشد، مثلا:

```text
configs/my-vless.config
configs/test-vmess.config
configs/trojan-server.config
```

داخل هر فایل باید حداقل یک خط کانفیگ معتبر وجود داشته باشد. اگر هیچ کانفیگ معتبری وجود نداشته باشد، دکمه‌های اسکن و تست سرعت غیرفعال می‌شوند تا کانفیگ اضافه کنید.

## ظاهر برنامه

در تب `About` گزینه `Dark mode` را فعال کنید تا تمام رابط کاربری به حالت تاریک ملایم تغییر کند. انتخاب شما در فایل `settings.json` ذخیره می‌شود و در اجرای بعدی برنامه نیز باقی می‌ماند. با غیرفعال کردن همین گزینه، حالت روشن دوباره فعال می‌شود.

## پوشه‌های پروژه

- `bin/xray`: کش محلی Xray. اسکریپت اجرا در صورت نبود فایل، نسخه رسمی مناسب سیستم را دانلود می‌کند.
- `tools`: ابزار مشترک دانلود Xray و ساخت نسخه‌های مستقل.
- `proxy_tester`: کد اصلی برنامه.
- `configs`: فایل‌های کانفیگ شما. کانفیگ‌های واقعی توسط Git نادیده گرفته می‌شوند.
- `output`: خروجی‌های CSV و کانفیگ‌های ساخته‌شده.
- `logs`: لاگ‌های اسکن و تست سرعت.
- `tests`: تست‌های یونیت.
- `dist`: خروجی موقت PyInstaller.
- `release`: فایل‌های نهایی آماده انتشار.
- `build`: پوشه موقت PyInstaller.

## پیش‌نیازها

برای اجرای سورس:

- Python نسخه 3.10 یا جدیدتر.
- دسترسی اینترنت در اولین اجرا برای دانلود Xray از ریلیز رسمی XTLS/Xray-core.

وابستگی Python را یک‌بار نصب کنید:

```sh
python -m pip install -r requirements.txt
```

اسکریپت اجرا فایل مناسب سیستم فعلی را در این مسیرها کش می‌کند:

```text
bin\xray\xray.exe   (Windows)
bin/xray/xray
```

در هر اجرا، برنامه فهرست کامل ریلیزهای رسمی Xray را بررسی می‌کند. اگر ریلیز جدیدتری منتشر شده باشد، حتی اگر prerelease باشد، فایل کش‌شده به‌صورت خودکار جایگزین می‌شود. اگر GitHub موقتا در دسترس نباشد، برنامه از فایل موجود استفاده می‌کند.

برای دانلود دستی نسخه مناسب سیستم فعلی:

```sh
python tools/xray_release.py --if-missing
```

## اجرای GUI

ویندوز:

```bat
run_gui.bat
```

لینوکس:

```sh
chmod +x run_gui.sh
./run_gui.sh
```

macOS:

```sh
chmod +x run_gui.sh
./run_gui.sh
```

در ویندوز، لانچر GUI از `pythonw.exe` استفاده می‌کند؛ بنابراین کنار برنامه پنجره کنسول باز نمی‌ماند.

لانچر هنگام بررسی Xray یک پنجره پیشرفت نمایش می‌دهد. اگر نسخه جدیدی دانلود شود، درصد دانلود یا حجم دریافت‌شده نمایش داده می‌شود. در صورت خطای شبکه، اگر فایل Xray موجود باشد برنامه با همان فایل اجرا می‌شود؛ اگر فایل موجود نباشد، مسیر دقیق برای کپی دستی Xray نمایش داده خواهد شد.

این بررسی فقط هنگام اجرای سورس با `run_gui.bat` یا `run_gui.sh` انجام می‌شود. نسخه‌های اجرایی منتشرشده از Xray همراه خود برنامه استفاده می‌کنند و هنگام اجرا Xray را بررسی یا دانلود نمی‌کنند.

## بخش‌های GUI

**Config**

- انتخاب فایل کانفیگ از پوشه `configs`.
- اضافه کردن کانفیگ جدید با فرمت `vless://`، `vmess://`، `trojan://` یا `ss://`.
- ویرایش یا تغییر نام کانفیگ انتخاب‌شده؛ محتوای جدید قبل از جایگزینی فایل اصلی اعتبارسنجی می‌شود.
- حذف کانفیگ انتخاب‌شده بعد از تأیید کاربر.
- اگر کانفیگ وجود نداشته باشد، دکمه‌های اسکن و تست سرعت غیرفعال می‌شوند.

**Scan New IPs**

- اسکن IP رندوم از تمام رنج‌های کلادفلر.
- اسکن رندوم یا تمام IPهای یک رنج انتخاب‌شده؛ رنج‌های سفارشی نیز داخل همین فهرست نمایش داده می‌شوند.
- اسکن رندوم از مجموع تمام رنج‌های سفارشی ذخیره‌شده.
- افزودن و ویرایش رنج‌های IPv4 سفارشی با دکمه `Edit Ranges`. هر CIDR را در یک خط وارد کنید؛ IP تکی به‌صورت رنج `/32` ذخیره می‌شود.
- انتخاب تعداد IP؛ مقدار پیش‌فرض `1000` است.
- تنظیم تعداد تست موازی: `10`، `20`، `50`، `100` یا `200`. مقدار پیش‌فرض `50` است.
- تنظیم timeout اسکن. مقدار پیش‌فرض `2000ms` است.
- شروع یا توقف اسکن.
- گزینه `Optimized mode for restricted networks` تمام تست‌های سرتاسری IP را با اثرانگشت `unsafe`، فهرست cipher suiteها و FinalMask دولایه داخلی اجرا می‌کند. این حالت به کانفیگ TLS نیاز دارد.
- تا وقتی این گزینه فعال است، تست سرعت خروجی‌ها نیز از همین تنظیم داخلی استفاده می‌کند و کنترل‌های فرگمنت معمولی تست سرعت غیرفعال و نادیده گرفته می‌شوند.

**Saved Results and Speed Test**

- انتخاب فایل CSV ذخیره‌شده.
- لود شدن IPها داخل جدول.
- تست سرعت روی کل خروجی انتخاب‌شده.
- ساخت کانفیگ جدید از خروجی انتخاب‌شده.

**Non-Cloudflare Tests**

- وارد کردن هم‌زمان چند کانفیگ VLESS، VMess، Trojan یا Shadowsocks؛ کانفیگ‌های تکراری نادیده گرفته می‌شوند و کانفیگ‌های نامعتبر گزارش داده می‌شوند.
- کانفیگ‌ها و آخرین نتیجه پینگ، دانلود و آپلود در فایل `configs/proxy-library.json` ذخیره می‌شوند.
- هر بار تست، یک فایل لاگ مستقل با نام `proxy-library-speed-test-*.log` داخل پوشه `logs` می‌سازد.
- می‌توانید چند ردیف را انتخاب کنید؛ اگر هیچ ردیفی انتخاب نشده باشد، تمام کانفیگ‌های کتابخانه به‌ترتیب تست می‌شوند.
- تست دانلود، آپلود یا هر دو به‌صورت تک‌به‌تک انجام می‌شود تا تست‌ها پهنای باند یکدیگر را خراب نکنند.
- فرگمنت به‌صورت پیش‌فرض غیرفعال است. با فعال کردن آن، مقادیر packets، interval و length از طریق `dialerProxy` روی تست تمام کانفیگ‌های انتخاب‌شده اعمال می‌شوند.
- مقادیر پیش‌فرض فرگمنت `Packets: tlshello`، `Interval: 1-2` و `Length: 5-10` هستند و هنگام تست، کنترل‌های فرگمنت قفل می‌شوند.
- مقدار `tlshello` مخصوص کانفیگ‌های دارای TLS است. برای Shadowsocks ساده و بدون TLS، در صورت نیاز از مقدار عددی مثل `1-3` برای packets استفاده کنید.
- ردیف در حال تست هایلایت می‌شود و تمام ستون‌ها هنگام تست نیز قابل مرتب‌سازی هستند.
- دکمه `Stop` پردازش Xray مربوط به تست فعال را بلافاصله متوقف می‌کند.
- با دوبار کلیک، دکمه اجرا یا گزینه `Run with Xray` می‌توانید همان کانفیگ و آدرس اصلی را داخل Xray Runner اجرا کنید.
- تست دوباره یک جهت، نتیجه ذخیره‌شده جهت دیگر را پاک نمی‌کند.

**Xray Runner**

- با دکمه `Export Xray Config` می‌توانید کانفیگ کامل Xray را با فرمت JSON ذخیره کنید. اگر فرگمنت فعال باشد، تنظیمات آن نیز داخل فایل قرار می‌گیرد.
- هنگام فعال بودن فرگمنت، برنامه با `dialerProxy` همان ClientHello واقعی اتصال TLS به IP پراکسی انتخاب‌شده را فرگمنت می‌کند؛ ترافیک TLS سایت‌های داخل تونل هدف فرگمنت نیست.
- گزینه `Optimized mode for restricted networks` یک تنظیم داخلی ویژه شبکه‌های محدودشده را اعمال می‌کند: اثرانگشت TLS برابر `unsafe`، فهرست مشخص cipher suiteها و دو لایه مرتب FinalMask. این حالت فقط برای کانفیگ‌های TLS قابل استفاده است.
- وقتی این حالت فعال باشد، تنظیمات فرگمنت معمولی و اسکنر فرگمنت استاندارد غیرفعال می‌شوند و مقادیر آن‌ها در اجرای Xray، خروجی JSON یا تست سرعت این تب استفاده نمی‌شوند.
- با قرار دادن مقدار `Packets` روی `tlshello` می‌توانید ClientHello واقعی را هدف بگیرید. مقادیر عددی مثل `1-3` روی شماره writeهای جریان TCP اعمال می‌شوند.
- هنگام اجرای اسکن فرگمنت، دکمه `Apply Best Saved Result` تا پایان یا توقف اسکن غیرفعال می‌ماند.

**About**

- نسخه برنامه، نسخه Xray و لینک مخزن GitHub را نمایش می‌دهد.
- دکمه `Check for Updates` آخرین نسخه منتشرشده را بررسی می‌کند و در صورت وجود نسخه جدید، صفحه دانلود را باز می‌کند.

## کار با جدول

با کلیک روی عنوان ستون‌ها می‌توانید جدول را مرتب کنید:

- Ping
- IP
- Download Mbps
- Upload Mbps

مرتب‌سازی حتی هنگام اسکن یا تست سرعت حفظ می‌شود.
ستون فعال با علامت `▶` مشخص می‌شود و جهت مرتب‌سازی صعودی با `▲` یا نزولی با `▼` نمایش داده می‌شود.

با راست‌کلیک روی ردیف‌های انتخاب‌شده این گزینه‌ها را دارید:

- `Test Download Speed`
- `Test Upload Speed`
- `Test Download and Upload`
- `Run Selected IP with Xray`
- `Copy IP`
- `Copy Proxy Configuration`
- `Show Configuration QR Code`

می‌توانید با Ctrl/Shift چند IP را انتخاب کنید و فقط همان‌ها را تست سرعت کنید. IP که در حال تست شدن است در جدول هایلایت می‌شود.

## انتقال کانفیگ با QR Code به موبایل

از داخل جدول نتایج می‌توانید برای هر IP تست‌شده یک QR Code آماده موبایل بسازید:

1. در بخش `Proxy Configuration` یک کانفیگ معتبر انتخاب کنید.
2. دقیقا یک IP را از جدول نتایج انتخاب کنید.
3. روی ردیف راست‌کلیک کنید و `Show Configuration QR Code` را بزنید.
4. QR Code نمایش‌داده‌شده را با یک کلاینت سازگار روی موبایل اسکن کنید.

این قابلیت از VLESS، VMess و Trojan روی WebSocket یا XHTTP پشتیبانی می‌کند. کانفیگ ساخته‌شده اطلاعات ورود، پورت، تنظیمات TLS، SNI، fingerprint، ALPN، آدرس و مسیر انتقال و تنظیمات `mode` و `extra` در XHTTP را از پروفایل فعال حفظ می‌کند و فقط آدرس سرور را با IP انتخاب‌شده جایگزین می‌کند.

ساخت QR Code کاملا روی کامپیوتر شما انجام می‌شود و کانفیگ یا اطلاعات ورود آن برای هیچ سرویس آنلاین QR ارسال نمی‌شود. داخل پنجره QR دکمه `Copy Configuration` نیز برای انتقال متنی کانفیگ وجود دارد. اگر کانفیگ معتبری فعال نباشد یا بیشتر از یک IP انتخاب شده باشد، گزینه QR غیرفعال خواهد بود.

نسخه‌های اجرایی مستقل، قابلیت QR را داخل خود دارند. برای اجرای سورس، وابستگی لازم را با فرمان `python -m pip install -r requirements.txt` نصب کنید.

## رفتار اسکن

هنگام اسکن:

- progress bar زنده آپدیت می‌شود.
- IPهای سالم داخل جدول نمایش داده می‌شوند.
- جدول بر اساس ستون انتخاب‌شده مرتب می‌ماند.
- دکمه Stop پردازش‌های فعال Xray را می‌کشد و تست‌های در صف را لغو می‌کند.
- نتایج سالمی که کامل شده‌اند ذخیره می‌شوند.

خروجی اسکن اینجا ذخیره می‌شود:

```text
output/working-cloudflare-proxy-ips-YYYYMMDD-HHMMSS.csv
output/working-cloudflare-proxy-ips-latest.csv
```

## رفتار تست سرعت

تست سرعت همیشه یک IP در لحظه تست می‌کند.

حالت‌های تست:

- Download
- Upload
- Both

تنظیمات پیش‌فرض:

- حجم تست: `1 MB`
- timeout تست سرعت: `7000ms`
- فرگمنت به‌صورت پیش‌فرض غیرفعال است و در صورت نیاز می‌توانید آن را فعال کنید.
- برای فرگمنت کردن ClientHello واقعی اتصال پراکسی، مقدار `Packets` را روی `tlshello` قرار دهید.
- مقادیر پیش‌فرض فرگمنت تست سرعت `Packets: tlshello`، `Interval: 1-2` و `Length: 5-10` هستند.

آدرس تست سرعت:

```text
https://speed.cloudflare.com
```

اگر تست سرعت fail شود:

- مقدار همان ستون `-1` می‌شود.
- اگر فقط آپلود fail شود، مقدار دانلود حفظ می‌شود.
- اگر فقط دانلود fail شود، مقدار آپلود حفظ می‌شود.
- دلیل خطا داخل لاگ GUI و فایل لاگ نوشته می‌شود.

در تست آپلود ابتدا یک بخش ۲۵۶ کیلوبایتی تأیید می‌شود و سپس باقی داده با همان مهلت زمانی کلی ارسال می‌شود. اگر ارسال بخش باقی‌مانده به پایان نرسد، سرعت تقریبی بر اساس داده تأییدشده نمایش داده می‌شود و در لاگ هشدار ثبت می‌شود. اگر همان بخش اولیه هم تأیید نشود، مقدار `-1` نمایش داده خواهد شد.

در تست دانلود، حجم هر بخش دریافت‌شده شمرده می‌شود. اگر پس از دریافت مقداری داده مهلت تست تمام شود، سرعت تقریبی دانلود بر اساس همان داده نمایش داده شده و در لاگ هشدار ثبت می‌شود. اگر پیش از دریافت هرگونه داده مهلت تمام شود، مقدار `-1` نمایش داده خواهد شد.

خروجی تست سرعت اینجا ذخیره می‌شود:

```text
output/speed-test-cloudflare-proxy-ips-YYYYMMDD-HHMMSS.csv
output/speed-test-cloudflare-proxy-ips-latest.csv
```

## لاگ‌ها

هر بار اسکن یا تست سرعت در GUI اجرا شود، یک فایل لاگ داخل این پوشه ساخته می‌شود:

```text
logs
```

لاگ‌ها شامل این موارد هستند:

- زمان شروع اجرا.
- منبع IPها.
- حجم و timeout تست سرعت.
- IPهای موفق و ناموفق.
- جزئیات خطای آپلود یا دانلود.
- وضعیت HTTP کلادفلر، اگر موجود باشد.

اگر تست آپلود زیاد fail می‌شود، جدیدترین فایل داخل `logs` را بررسی کنید.

## ساخت کانفیگ از IPهای سالم

یک فایل خروجی CSV انتخاب کنید و روی این دکمه بزنید:

```text
Generate Proxy Configurations
```

فایل ساخته‌شده داخل `output` ذخیره می‌شود.

برنامه پروتکل کانفیگ انتخاب‌شده را حفظ می‌کند:

- ورودی VLESS خروجی VLESS می‌سازد.
- ورودی VMess خروجی VMess می‌سازد.
- ورودی Trojan خروجی Trojan می‌سازد.

## اجرای CLI

ویندوز:

```bat
run_test.bat
```

برای اسکن مستقیم تعداد مشخصی IP از تمام رنج‌ها:

```bat
run_test.bat 1000
```

منوی CLI:

1. IP رندوم از همه رنج‌های کلادفلر
2. IP رندوم از یک رنج انتخاب‌شده
3. تست سرعت IPها از فایل خروجی ذخیره‌شده
4. ساخت کانفیگ از فایل خروجی ذخیره‌شده
5. تنظیمات
6. خروج

در زیرمنوها برای برگشت می‌توانید وارد کنید:

```text
0
b
back
```

اگر خروجی بدون رنگ می‌خواهید:

```text
NO_COLOR=1
```

## اجرای تست‌ها

ویندوز:

```bat
run_tests.bat
```

اجرای مستقیم با Python:

```bat
python -m unittest discover -s tests
```

برای نصب وابستگی‌های توسعه و اجرای همان بررسی پوشش شاخه‌ای که در CI استفاده می‌شود:

```bat
python -m pip install -r requirements-dev.txt
python -m coverage run -m unittest discover -v
python -m coverage report
```

حداقل پوشش شاخه‌ای در CI برابر ۷۰ درصد است. ساخت ظاهری و توصیفی پنجره Tk محاسبه نمی‌شود، اما رفتار GUI، workerها، چرخه اجرای Xray، QR، یکپارچه‌سازی سیستم‌عامل و ابزارهای انتشار همگی اندازه‌گیری می‌شوند.

## ساخت فایل اجرایی مستقل

برای ساخت فایل اجرایی مستقل از PyInstaller استفاده می‌شود. هر بیلد، نسخه رسمی و مناسب Xray را به‌صورت خودکار دانلود و داخل برنامه bundle می‌کند؛ فایل‌های باینری Xray داخل Git نگهداری نمی‌شوند.

نکات مهم:

- PyInstaller قابلیت cross-compile ندارد؛ هر نسخه باید روی همان سیستم‌عامل و معماری ساخته شود.
- نسخه Windows x86 را می‌توان روی Windows x64 با Python سی‌ودودوبیتی ساخت.
- خروجی macOS بدون امضای دیجیتال است و به‌صورت ZIP منتشر می‌شود.
- پوشه‌های `configs`، `output` و `logs` کنار فایل اجرایی ساخته می‌شوند.

اول PyInstaller را نصب کنید:

```sh
python -m pip install pyinstaller
```

بیلد ویندوز:

```bat
build_windows.bat
set PYTHON_EXE=C:\path\to\32-bit-python.exe
build_windows.bat x86
build_windows.bat arm64
```

برای بیلد x86 باید از Python نسخه 32 بیتی استفاده کنید. فرمان ARM64 نیز باید روی Windows ARM64 و با Python نسخه ARM64 اجرا شود.

بیلد لینوکس:

```sh
chmod +x build_linux.sh
./build_linux.sh
./build_linux.sh arm64
```

بیلد macOS:

```sh
chmod +x build_macos.sh
./build_macos.sh
```

فایل‌های نهایی داخل پوشه `release` ساخته می‌شوند:

```text
release/cloudflare-proxy-scanner-windows-x64.exe
release/cloudflare-proxy-scanner-linux-arm64
release/cloudflare-proxy-scanner-macos-arm64.zip
```

در حالت پیش‌فرض جدیدترین ریلیز منتشرشده Xray، شامل prerelease، استفاده می‌شود. برای ثابت نگه داشتن یک نسخه مشخص می‌توانید `XRAY_VERSION` را تنظیم کنید:

```sh
XRAY_VERSION=v26.7.11 ./build_linux.sh
```

workflow موجود در `.github/workflows/release.yml` نسخه‌های Windows x64/x86/ARM64، Linux x64/ARM64 و macOS Intel/Apple Silicon را می‌سازد. با push کردن یک tag نسخه، GitHub Release به‌صورت خودکار منتشر می‌شود:

```sh
git tag v1.0.0
git push origin v1.0.0
```

## اجرای نسخه ساخته‌شده

فایل اجرایی را داخل یک پوشه قرار دهید و اجرا کنید. برنامه این پوشه‌ها را کنار آن می‌سازد:

```text
configs
output
logs
```

کانفیگ خود را داخل `configs` قرار دهید و برنامه را اجرا یا دوباره باز کنید.

## سازگاری با v2rayN

برای تست نیازی به v2rayN ندارید.

اگر v2rayN باز است، معمولا مشکلی ایجاد نمی‌کند به شرطی که این موارد خاموش باشند:

- System Proxy
- TUN mode
- Global routing
- DNS hijack

این برنامه برای هر IP یک پراکسی موقت Xray مخصوص خودش می‌سازد.

## رفع مشکل

**دکمه‌های اسکن یا تست سرعت فعال نیستند**

یک کانفیگ معتبر داخل `configs` اضافه کنید یا از دکمه `Add Configuration` استفاده کنید.

**تست آپلود fail می‌شود**

این کارها را امتحان کنید:

- فقط حالت upload را تست کنید.
- حجم تست را به `0.25 MB` کاهش دهید.
- timeout تست سرعت را بیشتر از `7000ms` کنید.
- جدیدترین فایل داخل `logs` را بررسی کنید.

**دانلود Xray fail می‌شود**

اینترنت را بررسی کنید و دانلودر را مستقیم اجرا کنید تا متن خطا نمایش داده شود:

```sh
python tools/xray_release.py --if-missing
```

**بیلد ویندوز می‌گوید PyInstaller نصب نیست**

آن را برای همان Python نصب کنید:

```sh
python -m pip install -r requirements.txt pyinstaller
```

**برنامه ساخته‌شده باز می‌شود ولی تست انجام نمی‌دهد**

مطمئن شوید فایل کانفیگ کنار فایل اجرایی اضافه شده است:

```text
configs/your-config.config
```
