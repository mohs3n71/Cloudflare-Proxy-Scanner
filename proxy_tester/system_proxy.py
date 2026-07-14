import os


INTERNET_SETTINGS = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def set_socks_proxy(port, host="127.0.0.1"):
    if os.name != "nt":
        return "System proxy changes are only supported on Windows."
    import winreg

    server = f"socks={host}:{port}"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
        winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
    refresh_windows_proxy()
    return f"System proxy set to {server}"


def clear_proxy():
    if os.name != "nt":
        return "System proxy changes are only supported on Windows."
    import winreg

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, INTERNET_SETTINGS, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
    refresh_windows_proxy()
    return "System proxy cleared."


def refresh_windows_proxy():
    import ctypes

    internet_option_settings_changed = 39
    internet_option_refresh = 37
    ctypes.windll.Wininet.InternetSetOptionW(0, internet_option_settings_changed, 0, 0)
    ctypes.windll.Wininet.InternetSetOptionW(0, internet_option_refresh, 0, 0)
