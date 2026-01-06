#!/usr/bin/env python3
"""
RDP Launcher for Windows instances.
Opens an RDP connection using the system's default RDP client.

Supports:
- macOS: Microsoft Remote Desktop, open rdp:// URL, or .rdp file
- Linux: xfreerdp, remmina, rdesktop
- Windows: mstsc
"""
import sys
import os
import platform
import subprocess
import tempfile


def create_rdp_file(address, user, port=3389, password=None):
    """Create a temporary .rdp file with connection settings."""
    rdp_content = f"""screen mode id:i:2
use multimon:i:0
desktopwidth:i:1920
desktopheight:i:1080
session bpp:i:32
winposstr:s:0,3,0,0,800,600
compression:i:1
keyboardhook:i:2
audiocapturemode:i:0
videoplaybackmode:i:1
connection type:i:7
networkautodetect:i:1
bandwidthautodetect:i:1
displayconnectionbar:i:1
enableworkspacereconnect:i:0
disable wallpaper:i:0
allow font smoothing:i:0
allow desktop composition:i:0
disable full window drag:i:1
disable menu anims:i:1
disable themes:i:0
disable cursor setting:i:0
bitmapcachepersistenable:i:1
full address:s:{address}:{port}
audiomode:i:0
redirectprinters:i:1
redirectcomports:i:0
redirectsmartcards:i:1
redirectclipboard:i:1
redirectposdevices:i:0
autoreconnection enabled:i:1
authentication level:i:2
prompt for credentials:i:0
negotiate security layer:i:1
remoteapplicationmode:i:0
alternate shell:s:
shell working directory:s:
gatewayhostname:s:
gatewayusagemethod:i:4
gatewaycredentialssource:i:4
gatewayprofileusagemethod:i:0
promptcredentialonce:i:0
gatewaybrokeringtype:i:0
use redirection server name:i:0
rdgiskdcproxy:i:0
kdcproxyname:s:
username:s:{user}
"""
    fd, rdp_file = tempfile.mkstemp(suffix='.rdp', text=True)
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(rdp_content)
    except:
        os.close(fd)
        raise
    return rdp_file


def launch_rdp_macos(address, user, port=3389, password=None):
    print(f"Opening RDP connection to {address}:{port} as {user}...")
    rdp_url = f"rdp://full%20address=s:{address}:{port}&username=s:{user}"
    if password:
        # Not working on macos for some reason, but included for completeness and future fix
        rdp_url += f"&password=s:{password}"
    
    try:
        result = subprocess.run(
            ['open', rdp_url],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"Connection: {address}:{port}")
            print(f"Username: {user}")
            return True
    except Exception as e:
        print(f"Microsoft Remote Desktop URL failed: {e}")

    try:
        rdp_file = create_rdp_file(address, user, port, password)
        print(f"Created RDP file: {rdp_file}")
        result = subprocess.run(
            ['open', rdp_file],
            capture_output=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"Connection: {address}:{port}")
            print(f"Username: {user}")
            subprocess.Popen(['sh', '-c', f'sleep 3600 && rm -f {rdp_file}'])
            return True
        else:
            os.unlink(rdp_file)
    except Exception as e:
        print(f"RDP file method failed: {e}")
        try:
            os.unlink(rdp_file)
        except:
            pass

    return False


def launch_rdp_linux(address, user, port=3389, password=None):
    print(f"Opening RDP connection to {address}:{port} as {user}...")

    rdp_clients = [
        ['xfreerdp', f'/v:{address}:{port}', f'/u:{user}', '/cert:ignore', '/dynamic-resolution', '+clipboard'] + ([f'/p:{password}'] if password else []),
        ['remmina', '-c', f'rdp://{user}{":" + password if password else ""}@{address}:{port}'],
        ['rdesktop', f'{address}:{port}', '-u', user] + (['-p', password] if password else []) + ['-g', '1920x1080'],
    ]

    for cmd in rdp_clients:
        try:
            client_name = cmd[0]
            if subprocess.run(['which', client_name], capture_output=True).returncode == 0:
                print(f"Using {client_name}...")
                subprocess.Popen(cmd)
                print("RDP client launched")
                print(f"Connection: {address}:{port}")
                print(f"Username: {user}")
                return True
        except Exception as e:
            continue

    return False


def launch_rdp_windows(address, user, port=3389, password=None):
    print(f"Opening RDP connection to {address}:{port} as {user}...")

    try:
        rdp_file = create_rdp_file(address, user, port, password)
        print(f"Created RDP file: {rdp_file}")

        subprocess.Popen(['mstsc', rdp_file])
        print("Microsoft Remote Desktop Connection launched")
        print(f"Connection: {address}:{port}")
        print(f"Username: {user}")

        subprocess.Popen(['timeout', '/t', '3600', '/nobreak', '&&', 'del', rdp_file], shell=True)
        return True
    except Exception as e:
        print(f"Error launching RDP: {e}")
        try:
            os.unlink(rdp_file)
        except:
            pass
        return False


def main():
    if len(sys.argv) < 3:
        print("Usage: rdp_launcher.py <address> <user> [port] [password]")
        print("\nOpens an RDP connection using the system's default RDP client.")
        print("\nExamples:")
        print("  rdp_launcher.py 192.168.1.100 Administrator")
        print("  rdp_launcher.py 192.168.1.100 Administrator 3389")
        print("  rdp_launcher.py 192.168.1.100 Administrator 3389 MyPassword")
        sys.exit(1)

    address = sys.argv[1]
    user = sys.argv[2]
    port = int(sys.argv[3]) if len(sys.argv) > 3 else 3389
    password = sys.argv[4] if len(sys.argv) > 4 else None

    system = platform.system()
    success = False
    if system == 'Darwin':
        success = launch_rdp_macos(address, user, port, password)
    elif system == 'Linux':
        success = launch_rdp_linux(address, user, port, password)
    elif system == 'Windows':
        success = launch_rdp_windows(address, user, port, password)
    else:
        print(f"Unsupported platform: {system}")
        sys.exit(1)

    if not success:
        print("\nFailed to launch RDP client")
        print("\nPlease install an RDP client:")
        print(f"\nManual connection:")
        print(f"  Server: {address}:{port}")
        print(f"  Username: {user}")
        sys.exit(1)

if __name__ == '__main__':
    main()

