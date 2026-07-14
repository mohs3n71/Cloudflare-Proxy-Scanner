import argparse
import importlib.util
import os
import shutil
import subprocess
import sys

try:
    from .xray_release import detect_arch, detect_os, download_xray, normalize_arch, normalize_os
except ImportError:
    from xray_release import detect_arch, detect_os, download_xray, normalize_arch, normalize_os


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_NAME = "cloudflare-proxy-scanner"
BUILD_DEPENDENCIES = ("PyInstaller", "qrcode")


def release_name(target_os, target_arch):
    return f"{APP_NAME}-{normalize_os(target_os)}-{normalize_arch(target_arch)}"


def validate_native_target(target_os, target_arch, current_os=None, current_arch=None):
    current_os = current_os or detect_os()
    current_arch = current_arch or detect_arch()
    target_os = normalize_os(target_os)
    target_arch = normalize_arch(target_arch)
    if (target_os, target_arch) != (current_os, current_arch):
        raise RuntimeError(
            f"PyInstaller cannot cross-compile {target_os}-{target_arch} from "
            f"{current_os}-{current_arch}. Run this build on the target platform."
        )


def validate_build_dependencies():
    missing = [name for name in BUILD_DEPENDENCIES if importlib.util.find_spec(name) is None]
    if missing:
        raise RuntimeError(
            f"Missing build dependencies: {', '.join(missing)}. Run: "
            f"{sys.executable} -m pip install -r requirements.txt pyinstaller"
        )


def pyinstaller_command(target_os, target_arch, runtime_dir, dist_dir, work_dir, spec_dir):
    name = release_name(target_os, target_arch)
    return [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name",
        name,
        "--distpath",
        dist_dir,
        "--workpath",
        work_dir,
        "--specpath",
        spec_dir,
        "--add-data",
        f"{runtime_dir}{os.pathsep}bin/xray",
        os.path.join(PROJECT_ROOT, "proxy_tester", "gui_entry.py"),
    ]


def collect_release_artifact(target_os, name, dist_dir, release_dir):
    os.makedirs(release_dir, exist_ok=True)
    if target_os == "windows":
        source = os.path.join(dist_dir, name + ".exe")
        destination = os.path.join(release_dir, name + ".exe")
        shutil.copy2(source, destination)
        return destination
    if target_os == "macos":
        app_path = os.path.join(dist_dir, name + ".app")
        archive_base = os.path.join(release_dir, name)
        return shutil.make_archive(archive_base, "zip", root_dir=dist_dir, base_dir=os.path.basename(app_path))
    source = os.path.join(dist_dir, name)
    destination = os.path.join(release_dir, name)
    shutil.copy2(source, destination)
    return destination


def build_release(target_os, target_arch, xray_version):
    target_os = normalize_os(target_os)
    target_arch = normalize_arch(target_arch)
    validate_native_target(target_os, target_arch)
    validate_build_dependencies()

    name = release_name(target_os, target_arch)
    runtime_dir = os.path.join(PROJECT_ROOT, "build", "runtime", name, "xray")
    work_dir = os.path.join(PROJECT_ROOT, "build", "pyinstaller", name)
    spec_dir = os.path.join(PROJECT_ROOT, "build", "spec")
    dist_dir = os.path.join(PROJECT_ROOT, "dist")
    release_dir = os.path.join(PROJECT_ROOT, "release")
    shutil.rmtree(runtime_dir, ignore_errors=True)
    os.makedirs(spec_dir, exist_ok=True)

    binary_path, resolved_version = download_xray(
        target_os,
        target_arch,
        runtime_dir,
        version=xray_version,
    )
    print(f"Bundling {binary_path} from Xray {resolved_version}.")
    command = pyinstaller_command(target_os, target_arch, runtime_dir, dist_dir, work_dir, spec_dir)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)
    artifact = collect_release_artifact(target_os, name, dist_dir, release_dir)
    print(f"Release artifact: {artifact}")
    return artifact


def build_parser():
    parser = argparse.ArgumentParser(description="Build a native standalone Proxy Scanner release.")
    parser.add_argument("--os", dest="target_os", default=detect_os())
    parser.add_argument("--arch", dest="target_arch", default=detect_arch())
    parser.add_argument("--xray-version", default=os.environ.get("XRAY_VERSION", "latest"))
    return parser


def main():
    args = build_parser().parse_args()
    try:
        build_release(args.target_os, args.target_arch, args.xray_version)
    except Exception as exc:
        raise SystemExit(f"Build failed: {exc}") from exc


if __name__ == "__main__":
    main()
