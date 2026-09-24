# Athena Knowledge Portal Agent Instructions

## Cloudflare cost policy

- The Cloudflare spending ceiling for this project is **USD 0.00**.
- Use only Free-tier Cloudflare products that stop or reject requests when their included limit is reached.
- Before any Cloudflare create, configure, or deploy action, verify the current official pricing and the account plan.
- Never enable R2, a paid plan, a paid add-on, or another metered resource that can exceed its free allowance.
- Never accept a checkout, add a payment method, or upgrade a plan for this project.
- Budget alerts are informational and are not a spending cap.
- If a Cloudflare action has an uncertain price or any possibility of a charge, stop before the action and report the risk.
- Downloadable files live on the VPS under `/var/lib/athena/media/downloads/` and are served by Django to signed-in users only (decision 2026-09-23). Do not add Pages Functions, Workers, R2, or another metered download service. OneDrive is no longer a download source.
