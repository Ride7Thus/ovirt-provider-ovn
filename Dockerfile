FROM rockylinux:8
HEALTHCHECK --interval=5m --timeout=3s \
   CMD curl -f http://localhost:9696/ || exit 1
EXPOSE 35357/tcp
EXPOSE 9696/tcp


COPY . /build
WORKDIR /build

RUN dnf update -y && \
    dnf install -y make epel-release curl &&\
    dnf install -y python3.9 &&\
    dnf clean all && \
    update-alternatives --set python /usr/bin/python3.9 && \
    mkdir -p /etc/ovirt-provider-ovn/conf.d/ /usr/share/ovirt-provider-ovn
RUN pip3 install -r requirements.txt && make compile && make install && make version.py
WORKDIR /usr/share/ovirt-provider-ovn
RUN cp -fr /build/provider/. /usr/share/ovirt-provider-ovn/ && rm -rf /build

ENTRYPOINT /usr/bin/python /usr/share/ovirt-provider-ovn/ovirt_provider_ovn.py
