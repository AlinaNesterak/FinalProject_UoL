#!/usr/bin/env bash
#
# Deployment script for the Music Works Catalogue Portal.
# Run on a fresh Ubuntu 24.04 VM as a user with sudo rights.
#
#   bash deploy/setup.sh
#
# Idempotent: safe to re-run after a code update.

set -euo pipefail

APP_DIR="/opt/musicworks"
REPO="https://github.com/AlinaNesterak/FinalProject_UoL.git"
SERVICE_USER="${SUDO_USER:-$USER}"

echo "==> Installing system packages"
sudo apt-get update -qq
sudo apt-get install -y python3-venv python3-pip nginx git

echo "==> Preparing $APP_DIR"
sudo mkdir -p "$APP_DIR"
sudo chown "$SERVICE_USER:$SERVICE_USER" "$APP_DIR"

if [ -d "$APP_DIR/.git" ]; then
  echo "    existing checkout found, pulling latest"
  git -C "$APP_DIR" pull --ff-only
else
  echo "    cloning repository"
  git clone "$REPO" "$APP_DIR"
fi

# The application may sit at the repository root or inside a subfolder
# (this repository keeps it in final_work/). Locate it rather than assume.
if [ -f "$APP_DIR/api/main.py" ]; then
  APP_ROOT="$APP_DIR"
elif [ -f "$APP_DIR/final_work/api/main.py" ]; then
  APP_ROOT="$APP_DIR/final_work"
else
  echo "ERROR: could not find api/main.py in $APP_DIR or $APP_DIR/final_work" >&2
  echo "Contents of $APP_DIR:" >&2
  ls -la "$APP_DIR" >&2
  exit 1
fi
echo "    application root: $APP_ROOT"

cd "$APP_ROOT"

echo "==> Creating virtual environment and installing dependencies"
python3 -m venv venv
./venv/bin/pip install --upgrade pip --quiet
# Only the runtime dependencies are needed on the server; the test and
# lint tooling in requirements.txt is for development machines.
./venv/bin/pip install --quiet fastapi "uvicorn[standard]" lxml pydantic

echo "==> Building the catalogue database from MEI XML"
./venv/bin/python transform/pipeline.py data catalogue.db

echo "==> Installing systemd service"
# Substitute the real service user into the unit file before installing.
# Substitute the real service user and the detected application root, so
# the unit works regardless of where in the repository the app lives.
sed -e "s/^User=.*/User=$SERVICE_USER/" \
    -e "s/^Group=.*/Group=$SERVICE_USER/" \
    -e "s#^WorkingDirectory=.*#WorkingDirectory=$APP_ROOT#" \
    -e "s#^ExecStart=.*#ExecStart=$APP_ROOT/venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8000#" \
    deploy/musicworks.service | sudo tee /etc/systemd/system/musicworks.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable musicworks
sudo systemctl restart musicworks

echo "==> Configuring nginx"
sudo cp deploy/nginx.conf /etc/nginx/sites-available/musicworks
sudo ln -sf /etc/nginx/sites-available/musicworks /etc/nginx/sites-enabled/musicworks
# Remove the default site so it does not shadow ours on port 80.
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx

echo ""
echo "==> Done. Checking service status:"
sudo systemctl is-active musicworks && echo "    musicworks: running"
sudo systemctl is-active nginx && echo "    nginx: running"
echo ""
echo "The site should now be reachable at:"
echo "  http://elearning-alinanesterak.switzerlandnorth.cloudapp.azure.com/"
echo ""
echo "If it is not, check: sudo journalctl -u musicworks -n 50 --no-pager"
