#!/bin/bash -e
#
# Run make targets (default: check unittest) inside the same tests image the
# CI uses, with the working tree mounted.
#
#   automation/run_tests_in_container.sh
#   IMAGE_TAG=almalinux-10 automation/run_tests_in_container.sh lint
#   CONTAINER_CMD=docker CONTAINER_ARGS="--platform linux/amd64" \
#       automation/run_tests_in_container.sh

CONTAINER_CMD=${CONTAINER_CMD:=podman}
IMAGE_TAG=${IMAGE_TAG:=centos-9}
TESTS_IMG=${TESTS_IMG:=quay.io/ovirt/ovirt-provider-ovn-tests}
TARGETS=${*:-check unittest}

PROJECT_ROOT=$(git rev-parse --show-toplevel)
CONTAINER_SRC_CODE_PATH=/ovirt-provider-ovn

# shellcheck disable=SC2086
${CONTAINER_CMD} run --rm ${CONTAINER_ARGS} \
    -v "$PROJECT_ROOT":"$CONTAINER_SRC_CODE_PATH":Z \
    -w "$CONTAINER_SRC_CODE_PATH" \
    "$TESTS_IMG:$IMAGE_TAG" \
    /bin/bash -c "
        git config --global --add safe.directory $CONTAINER_SRC_CODE_PATH &&
        make $TARGETS
    "
