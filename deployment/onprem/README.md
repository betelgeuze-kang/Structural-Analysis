# On-Prem And Air-Gapped Packaging Contract

This directory is a packaging skeleton for controlled on-prem and air-gapped product evaluation. It is not a live deployment claim.

## Boundary

- Container runtime is represented by `Containerfile` and `compose.example.yml`.
- Offline entitlement is represented by `offline-license.example.json`.
- Signed update transfer is represented by `signed-update-package.example.json`.
- Runtime/package/support evidence is verified by `scripts/build_onprem_deployment_packaging_manifest.py`.

## Operator Flow

1. Build or import the container image in a controlled build environment.
2. Move the image, runtime artifacts, release manifest, offline license file, and signed update package through the approved artifact-transfer process.
3. Set `PROJECT_OPS_JWT_HMAC_SECRET` from the deployment secret store before starting the service.
4. Keep the deployment network isolated unless the site explicitly enables an outbound update mirror.
5. Generate a support bundle after smoke testing and attach it to the deployment handoff packet.

## Required Evidence

- Container definition and compose example are present.
- Offline license file has an explicit tenant, expiry, feature set, and signature placeholder.
- Update package manifest has artifact hashes, signature placeholder, rollback policy, and no implicit network dependency.
- Support bundle and runtime packaging manifests pass.

## Remaining Live-Deployment Work

- Replace example license and update signatures with production signing keys.
- Build and scan the image in the customer-approved environment.
- Capture gateway/TLS/WAF, backup/restore, tenant-delete, and incident response drill evidence.
