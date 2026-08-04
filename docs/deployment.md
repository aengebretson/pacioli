# Deployment

## Public website

The public website lives in `apps/web` and is intended to deploy as a Vercel project connected to this GitHub repository.

Recommended Vercel project settings:

- Framework preset: Next.js
- Root directory: `apps/web`
- Install command: `cd ../.. && pnpm install --frozen-lockfile=false`
- Build command: `cd ../.. && pnpm --filter @pacioli/web build`
- Node.js: 22

Vercel should create preview deployments for pull requests and deploy `main` to production.

## Cloudflare DNS

Keep the public zone in Cloudflare and point the chosen website hostname to the Vercel project after Vercel provides its domain target. Use Cloudflare for DNS, DNSSEC, redirects, and optional traffic controls; let Vercel terminate the website deployment and certificates.

Do not proxy the initial DNS record through Cloudflare until Vercel domain verification and certificate issuance succeed. After verification, decide whether Cloudflare proxying provides a concrete benefit; using DNS-only avoids layering two CDNs without a reason.

## Managed services

The marketing website is not the Pacioli data plane. Future managed services should be independently deployed components:

- API/control plane
- durable job queue
- stateless native worker pools
- metadata database
- immutable object storage
- optional analytical serving database

Self-hosted and managed deployments should use the same engine binaries and versioned calculation contracts.

## Build infrastructure

GitHub-hosted Actions runners are the default build fleet. Add self-hosted runners only when one of these becomes true:

- dependency builds exceed practical hosted-runner limits;
- specialized hardware is required;
- signed desktop artifacts require controlled key access;
- integration tests need private infrastructure;
- build volume makes dedicated capacity economically compelling.

A self-hosted runner is build capacity, not a general-purpose pet server. It should be ephemeral or tightly isolated and should never accept untrusted pull-request jobs with production credentials.
