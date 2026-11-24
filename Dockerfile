# Standalone ovirt-provider-ovn image.
#
# Build:  docker build -t ovirt-provider-ovn .
# Run:    docker run -d -p 9696:9696 -p 35357:35357 \
#             -v /path/to/conf.d:/etc/ovirt-provider-ovn/conf.d:ro \
#             ovirt-provider-ovn
#
# Configuration goes to /etc/ovirt-provider-ovn/conf.d/*.conf, at least
# [OVN REMOTE] ovn-remote pointing at the OVN north database. Logs are
# written to the container's stdout.
ARG BASE_IMAGE=quay.io/centos/centos:stream9
FROM ${BASE_IMAGE}
LABEL maintainer="devel@ovirt.org" purpose="ovirt_provider_ovn"

ARG COPR_CHROOT=centos-stream-9-x86_64

RUN dnf -y install dnf-plugins-core epel-release \
    && \
    dnf copr enable -y ovirt/ovirt-master-snapshot ${COPR_CHROOT} \
    && \
    dnf install -y ovirt-release-master \
    && \
    dnf install -y \
        findutils \
        git \
        make \
        ovirt-python-openvswitch \
        python3 \
        python3-netaddr \
        python3-ovsdbapp \
        python3-requests \
    && \
    dnf clean all

COPY . /build
RUN cd /build \
    && \
    make PYTHON=python3 version.py install \
    && \
    rm -rf /build \
    && \
    useradd --system --no-create-home --shell /sbin/nologin ovirt-provider-ovn \
    && \
    ln -sf /dev/stdout /var/log/ovirt-provider-ovn.log

USER ovirt-provider-ovn
WORKDIR /usr/share/ovirt-provider-ovn

EXPOSE 9696/tcp 35357/tcp

# Protocol agnostic, works with both http and https.
HEALTHCHECK --interval=30s --timeout=3s \
    CMD python3 -c "import socket; socket.create_connection(('127.0.0.1', 9696), 2)"

ENTRYPOINT ["python3", "/usr/share/ovirt-provider-ovn/ovirt_provider_ovn.py"]
