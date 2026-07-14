# Xray Runtime Cache

Xray executables are downloaded from official XTLS/Xray-core releases when a launch or build script needs them. The launcher checks for the newest published release, including prereleases, and stores platform/version metadata here so current binaries are reused. Downloaded files in this directory are intentionally ignored by Git.

Manual download for the current machine:

```sh
python tools/xray_release.py --if-missing
```

Release builds use a separate temporary copy under `build/runtime` and bundle it into the standalone application.
