#!/bin/sh
# Deploy a tagged release of the randomizer site: check the tag out in /opt/golf-site,
# install its locked dependencies, restart the service and wait for it to answer.
# Rolling back is deploying the previous tag, which this prints first.
#
#   /opt/golf-site/deploy/deploy.sh v1.0.0
#
# Run on the server as the user who owns the checkout; restarting asks for sudo.
# See docs/deployment.md.

set -eu

CHECKOUT=/opt/golf-site
# uv's interpreters live outside any home directory, where the golf user can reach them.
export UV_PYTHON_INSTALL_DIR=/opt/uv/python
HEALTH_URL=http://127.0.0.1:8000/healthz

# Everything runs from this function, so the whole script is read before the checkout
# replaces the file it is reading.
main() {
    tag=${1:?usage: deploy.sh <tag>}
    cd "$CHECKOUT"

    if ! git diff --quiet HEAD; then
        echo "error: $CHECKOUT has local changes" >&2
        exit 1
    fi

    git fetch --quiet --tags --force origin
    if ! git rev-parse --quiet --verify "refs/tags/$tag^{commit}" >/dev/null; then
        echo "error: no tag $tag" >&2
        exit 1
    fi

    previous=$(git describe --tags --always HEAD)
    echo "deploying $tag (was $previous; roll back with: $0 $previous)"
    git -c advice.detachedHead=false checkout --quiet "refs/tags/$tag"
    uv sync --frozen --no-dev

    sudo systemctl restart golf-site
    for _ in $(seq 30); do
        if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
            echo "deployed $tag"
            exit 0
        fi
        sleep 1
    done
    echo "error: the site did not answer $HEALTH_URL; see journalctl -u golf-site" >&2
    exit 1
}

main "$@"
