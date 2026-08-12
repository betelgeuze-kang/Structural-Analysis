# Archived React Pages Deployment

`deploy-pages.yml` is retained only as rollback and deprecation evidence. It was removed from
`.github/workflows`, so GitHub Actions cannot dispatch it and it has no active Pages permission.
The active product deployment entrypoint is `deployment/onprem/Containerfile`, which packages the
Rust-native Workbench. Removal remains disallowed until the deprecation window and final C6 audit
are complete.
