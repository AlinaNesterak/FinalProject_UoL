# Deployment

These notes deploy the Music Works Catalogue Portal to an Ubuntu 24.04 VM.
They were written for an Azure "Standard B2ats v2" instance (2 vCPU, 1 GiB RAM),
which is small enough that the deployment choices matter — see *Why not Docker*
below.

The application runs under `systemd` and is fronted by `nginx`, which handles
public traffic on port 80 and proxies to uvicorn on localhost. The application
itself is never bound to a public interface.

```
internet ──▶ nginx :80 ──▶ uvicorn 127.0.0.1:8000 ──▶ SQLite (single file)
```

---

## Step 1 — Open port 80 in the Azure firewall

This is done in the Azure portal, not on the VM. Without it, everything below
will appear to work while the site remains unreachable.

1. Open your VM → **Networking** → **Network settings**
2. **Add inbound port rule**
3. Set:
   - Source: `Any`
   - Destination port ranges: `80`
   - Protocol: `TCP`
   - Action: `Allow`
   - Priority: `310` (any free number below 65000)
   - Name: `Allow-HTTP`
4. **Add**

Leave the existing SSH rule (port 22) in place or you will lock yourself out.

## Step 2 — Connect to the VM

```bash
ssh azureuser@elearning-alinanesterak.switzerlandnorth.cloudapp.azure.com
```

Substitute your own username if it is not `azureuser`. The Azure portal shows it
under **Connect**.

## Step 3 — Run the setup script

```bash
git clone https://github.com/AlinaNesterak/FinalProject_UoL.git /tmp/mw
bash /tmp/mw/deploy/setup.sh
```

The script installs dependencies, clones the repository to `/opt/musicworks`,
creates a virtual environment, builds the catalogue database from the MEI XML,
installs the systemd service, and configures nginx. It is safe to re-run.

## Step 4 — Check it

Open the DNS name in a browser:

```
http://elearning-alinanesterak.switzerlandnorth.cloudapp.azure.com/
```

You should see the catalogue with 24 works. The API documentation is at `/docs`
and the research findings page at `/#/research`.

---

## Updating after a code change

```bash
cd /opt/musicworks
git pull
./venv/bin/python transform/pipeline.py data catalogue.db   # only if data changed
sudo systemctl restart musicworks
```

## Troubleshooting

| Symptom | Check |
|---|---|
| Browser times out | Port 80 rule missing in Azure (Step 1) |
| 502 Bad Gateway | uvicorn is not running: `sudo journalctl -u musicworks -n 50` |
| 404 on every page | nginx default site still enabled: `sudo rm /etc/nginx/sites-enabled/default` |
| "Database not built" | Run the pipeline command above |

Useful commands:

```bash
sudo systemctl status musicworks      # is the app running?
sudo journalctl -u musicworks -f      # live application logs
sudo nginx -t                         # is the nginx config valid?
```

---

## Optional — HTTPS

Azure's `cloudapp.azure.com` DNS name works with Let's Encrypt, so a
certificate can be obtained without owning a domain:

```bash
sudo apt-get install -y certbot python3-certbot-nginx
sudo certbot --nginx -d elearning-alinanesterak.switzerlandnorth.cloudapp.azure.com
```

Certbot edits the nginx config in place and sets up automatic renewal. Port 443
must also be opened in the Azure firewall, following Step 1 with port `443`.

---

## Why not Docker

The repository includes a working `Dockerfile`, and on a larger host that would
be the more reproducible option. It is not used here for two reasons specific to
this deployment.

The VM has 1 GiB of RAM. The Docker daemon consumes a meaningful share of that
before the application starts, and this workload — read-only queries against a
small SQLite file — gains nothing from containerisation at runtime.

More importantly, the project's argument (Chapter 6 of the report) is that
software should be built to survive the loss of institutional support. A
deployment that a future maintainer can inspect with `systemctl status` and
`journalctl`, using tools present on every Ubuntu system, is more likely to
remain maintainable than one requiring a container runtime to be installed,
running and understood. The Dockerfile remains available for hosts where it is
the better fit.
