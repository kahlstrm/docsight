# Image delivery for this fork

The image workflow tests the exact source revision before publishing to
`ghcr.io/kahlstrm/docsight`. It runs on image changes merged to main, version tags,
manual dispatch, and Mondays at 05:41 UTC. Weekly builds disable the build cache
and refresh the base image so available OS updates are installed.

Main builds publish `main`, `latest`, and a full commit-SHA tag. Version tags and
manual branch builds also publish a commit-SHA tag; a branch build does not move
`main` or `latest`. The workflow summary records the immutable manifest digest.
A rebuild of the same source can produce a new digest, so deploy by digest.

The infra repository keeps the desired image in the DOCSight Kustomization.
Renovate proposes digest updates for `main`; merging that PR lets Argo CD deploy.
Application code is public, and the GHCR package should be public for anonymous
cluster pulls. Credentials belong in runtime Kubernetes secrets, never the image.

Upstream code updates remain reviewed merges into this fork. Rebuilding an image
does not fetch upstream source or change pinned Python dependencies. Review
upstream changes and preserve the fork's monitoring and authentication tests.
