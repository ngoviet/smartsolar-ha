"""Upload SmartSolar integration files to HA server via SSH exec."""
import paramiko
import os
import base64
import sys

HA_HOST = "192.168.10.15"
HA_USER = "vokupt"
HA_PASS = "qweszxc12"
SRC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "custom_components", "smartsolar_mppt")
DST_DIR = "/homeassistant/custom_components/smartsolar_mppt"


def run(ssh, cmd):
    """Run a command over SSH and check exit status."""
    stdin, stdout, stderr = ssh.exec_command(cmd)
    exit_status = stdout.channel.recv_exit_status()
    out = stdout.read().decode()
    err = stderr.read().decode()
    if exit_status != 0:
        raise RuntimeError(f"Command failed [{exit_status}]: {cmd}\n  stderr: {err.strip()}")
    return out, err


def upload_file(ssh, local_path, remote_path):
    """Upload a file by base64 encoding it over SSH."""
    with open(local_path, "rb") as f:
        content = base64.b64encode(f.read()).decode()

    # Upload base64 content in chunks via sudo tee
    chunk_size = 51200
    chunks = [content[i:i+chunk_size] for i in range(0, len(content), chunk_size)]

    for i, chunk in enumerate(chunks):
        if i == 0:
            run(ssh, f"echo '{chunk}' | sudo tee {remote_path}.b64 > /dev/null")
        else:
            run(ssh, f"echo '{chunk}' | sudo tee -a {remote_path}.b64 > /dev/null")

    # Decode and clean up using sudo sh to handle the pipeline
    run(ssh, f"sudo sh -c 'base64 -d {remote_path}.b64 > {remote_path} && rm {remote_path}.b64'")


def main():
    print(f"Connecting to {HA_HOST}...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(HA_HOST, username=HA_USER, password=HA_PASS, timeout=10)
    print("Connected!\n")

    # Ensure destination directory exists
    run(ssh, f"sudo mkdir -p {DST_DIR}")

    # Collect files (skip __pycache__, .pyc)
    files = []
    for root, dirs, fnames in os.walk(SRC_DIR):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fname in fnames:
            if fname.endswith(".pyc"):
                continue
            full_path = os.path.join(root, fname)
            rel_path = os.path.relpath(full_path, SRC_DIR).replace("\\", "/")
            files.append((full_path, f"{DST_DIR}/{rel_path}"))

    print(f"Uploading {len(files)} files...")

    for local, remote in files:
        remote_dir = os.path.dirname(remote).replace("\\", "/")
        run(ssh, f"sudo mkdir -p {remote_dir}")

        rel = os.path.relpath(local, SRC_DIR)
        try:
            upload_file(ssh, local, remote)
            print(f"  OK: {rel}")
        except RuntimeError as e:
            print(f"  FAIL: {rel}")
            print(f"  Error: {e}")
            ssh.close()
            sys.exit(1)

    ssh.close()
    print(f"\nAll {len(files)} files uploaded!")


if __name__ == "__main__":
    main()
