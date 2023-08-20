#!/bin/bash
#Moving hubble source code logic in the shell script

# if ENTRYPOINT is given a CMD other than nothing
# abort here and do that other CMD
if [ $# -gt 0 ]
then exec "$@"
fi

set -x -e
if [ ! -d "${HUBBLE_SRC_PATH}" ]
then git clone "${HUBBLE_GIT_URL}" "${HUBBLE_SRC_PATH}"
fi

if [ -n "$OSQUERY_TAR_FILENAME" ]
then OSQUERY_TAR_FILENAMES=( /data/$OSQUERY_TAR_FILENAME )
else OSQUERY_TAR_FILENAMES=( /data/osquery_4hubble.$(uname -m).tar /data/osquery_4hubble.tar )
fi

if [ ! -d /opt/osquery ]
then mkdir -vp /opt/osquery
fi

for filename in "${OSQUERY_TAR_FILENAMES[@]}"; do
    if [ -e "$filename" ]; then
        tar -C /opt/osquery -xvvf "$filename"
        break
    fi
done

if [ ! -x /opt/osquery/osqueryi ]
then echo please provide a working osquery tarfile; exit 1
else /opt/osquery/osqueryi --version
fi

cd "${HUBBLE_SRC_PATH}"
git checkout "${HUBBLE_CHECKOUT}"

HUBBLE_VERSION="$( sed -e 's/^v//' -e 's/[_-]rc/rc/g' <<< "$HUBBLE_VERSION" )"

cp -rf "${HUBBLE_SRC_PATH}"/* /hubble_build
rm -rf /hubble_build/.git

cp /hubble_build/hubblestack/__init__.py /hubble_build/hubblestack/__init__.orig
sed -i -e "s/BRANCH_NOT_SET/${HUBBLE_CHECKOUT}/g" -e "s/COMMIT_NOT_SET/$(cd ${HUBBLE_SRC_PATH}; git describe --long --always --tags)/g" /hubble_build/hubblestack/__init__.py
cp /hubble_build/hubblestack/__init__.py /hubble_build/hubblestack/__init__.fixed

sed -i -e "s/'.*'/'$HUBBLE_VERSION'/g" /hubble_build/hubblestack/version.py

eval "$(pyenv init --path)"

# from now on, exit on error (rather than && every little thing)
PS4=$'-------------=: '

# possibly replace the version file
if [ -f /data/hubble_buildinfo ]; then
    echo >> /hubble_build/hubblestack/__init__.py
    cat /data/hubble_buildinfo >> /hubble_build/hubblestack/__init__.py
fi 2>/dev/null

cat > /data/pre_packaged_certificates.py << EOF
ca_crt = list()
public_crt = list()
EOF
do_pkg_crts=0
if [ -f /data/certs/ca-root.crt ]; then
    echo "ca_crt.append('''$(< /data/certs/ca-root.crt)''')" \
        >> /data/pre_packaged_certificates.py
        do_pkg_crts=$(( do_pkg_crts + 1 ))
    for item in /data/certs/int*.crt; do
        if [ -f "$item" ]
        then echo "ca_crt.append('''$(< "$item")''')" \
            >> /data/pre_packaged_certificates.py
            do_pkg_crts=$(( do_pkg_crts + 1 ))
        fi
    done
fi
for item in /data/certs/{pub,sign}*.crt; do
    if [ -f "$item" ]
    then echo "public_crt.append('''$(< "$item")''')" \
        >> /data/pre_packaged_certificates.py
        do_pkg_crts=$(( do_pkg_crts + 1 ))
    fi
done
if [ $do_pkg_crts -gt 0 ]
then cp /data/pre_packaged_certificates.py /hubble_build/hubblestack
fi

cd /hubble_build

# we may have preinstalled requirements that may need upgrading
# pip install . might not upgrade/downgrade the requirements
pip install wheel
python setup.py egg_info
pip install --upgrade \
    -r hubblestack.egg-info/requires.txt \
    -r optional-requirements.txt \
    -r package-requirements.txt
pip freeze > /data/requirements.txt

[ -f ${_HOOK_DIR:-./pkg}/hook-hubblestack.py ] || exit 1

rm -rf build dist /opt/hubble/hubble-libs /hubble_build/hubble.spec
export LD_LIBRARY_PATH=$(pyenv prefix)/lib:/opt/hubble/lib:/opt/hubble-libs
export LD_RUN_PATH=$LD_LIBRARY_PATH
pyinstaller --onedir --noconfirm --log-level ${_BINARY_LOG_LEVEL:-INFO} \
    --additional-hooks-dir ${_HOOK_DIR:-./pkg} \
    --runtime-hook pkg/runtime-hooks.py \
    ./hubble.py 2>&1 | tee /tmp/pyinstaller.log

cp -pr dist/hubble /opt/hubble/hubble-libs

cat > /opt/hubble/hubble << EOF
#!/bin/bash
exec /opt/hubble/hubble-libs/hubble "\$@"
exit 1
EOF
chmod 0755 /opt/hubble/hubble

[ -d /data/last-build.4 ] && rm -rf /data/last-build.4
[ -d /data/last-build.3 ] && mv -v /data/last-build.3 /data/last-build.4
[ -d /data/last-build.2 ] && mv -v /data/last-build.2 /data/last-build.3
[ -d /data/last-build.1 ] && mv -v /data/last-build.1 /data/last-build.2
cp -va build/ /data/last-build.1
mv /tmp/pyinstaller.log /data/last-build.1
cp -va /entrypoint.sh /data/last-build.1

mkdir -p /var/log/hubble_osquery/backuplogs

mkdir -p /usr/lib/systemd/system
mkdir -p /etc/profile.d
mkdir -p /etc/hubble/hubble.d

cp -v /hubble_build/pkg/hubble.service /usr/lib/systemd/system/
cp -v /hubble_build/conf/hubble-profile.sh /etc/profile.d/
cp -v /hubble_build/conf/hubble-d-conf /etc/hubble/hubble.d

if [ -f /data/hubble ]
then cp -v /data/hubble /etc/hubble/
else cp -v /hubble_build/conf/hubble /etc/hubble/
fi

if [ "X$TEST_BINARIES" = X1 ]; then
    # weakly test the new bin
    ./dist/hubble/hubble --version

    # does it still work if we call it in its new home?
    /opt/hubble/hubble-libs/hubble --version

    # how about if it's via non-home location?
    /opt/hubble/hubble --version

    # lastly, can we actually use salt grains and other lazy loader items?
    /opt/hubble/hubble-libs/hubble -vvv grains.get hubble_version
    /opt/hubble/hubble -vvv grains.get hubble_version
fi

if [ "X$NO_TAR" = X1 ]; then
    echo "exiting (as requested by NO_TAR=$NO_TAR) without pre-tar-ing package"
    exit 0
fi 2>/dev/null

# deb pkg start
tar -cSPvvzf /data/hubblestack-${HUBBLE_VERSION}.tar.gz \
    --exclude opt/hubble/pyenv \
    /etc/hubble /opt/hubble /opt/osquery \
    /etc/profile.d/hubble-profile.sh \
    /usr/lib/systemd/system/hubble.service \
    /var/log/hubble_osquery/backuplogs \
    2>&1 | tee /hubble_build/deb-pkg-start-tar.log

PKG_STRUCT_DIR=/hubble_build/debbuild/hubblestack-${HUBBLE_VERSION}
mkdir -p /hubble_build/debbuild/hubblestack-${HUBBLE_VERSION}
tar -xSzvvf /data/hubblestack-${HUBBLE_VERSION}.tar.gz -C $PKG_STRUCT_DIR

# also bring in anything from a /data/opt/ directory so we can bundle other executables if needed
if [ -d /data/opt ]
then cp -r /data/opt/* /hubble_build/debbuild/hubblestack-${HUBBLE_VERSION}/opt/
fi

# symlink to have hubble binary in path
cd /hubble_build/debbuild/hubblestack-${HUBBLE_VERSION}
mkdir -p usr/bin
ln -sf /opt/hubble/hubble usr/bin/hubble

if [ "X$NO_FPM" = X1 ]; then
    echo "exiting (as requested by NO_FPM=$NO_FPM) without building package"
    exit 0
fi

# for whatever reason, packages normally don't use the $(uname -m) name
# of the architecture, prefering misnomers like 'amd64' for 'x86_64'
# ... strange, but:
case "${ARCH:-$(uname -m)}" in
    aarch64) PACKAGE_NAME_ARCH=arm64 ;;
    *) PACKAGE_NAME_ARCH=amd64 ;;
esac

# edit to change iteration number, if necessary
PKG_BASE_NAME=hubblestack-${HUBBLE_VERSION}-${HUBBLE_ITERATION}
PKG_OUT_EXT=$PACKAGE_NAME_ARCH.deb
PKG_FIN_EXT=deb9.$PKG_OUT_EXT
PKG_FNAME=${PKG_BASE_NAME}.$PKG_FIN_EXT

# fpm start
fpm -s dir -t deb \
    -n hubblestack \
    --package /data/$PKG_FNAME --force \
    -v ${HUBBLE_VERSION} \
    --iteration ${HUBBLE_ITERATION} \
    --url ${HUBBLE_URL} \
    --deb-no-default-config-files \
    --after-install /hubble_build/conf/afterinstall-systemd.sh \
    --after-upgrade /hubble_build/conf/afterupgrade-systemd.sh \
    --before-remove /hubble_build/conf/beforeremove.sh \
    etc/hubble opt usr /var/log/hubble_osquery/backuplogs

openssl dgst -sha256 /data/$PKG_FNAME > /data/$PKG_FNAME.sha256
