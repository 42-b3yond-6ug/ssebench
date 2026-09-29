#!/bin/bash -eu
export PATH=$(echo $PATH | tr ':' '\n' | grep -v '/opt/venv/' | tr '\n' ':' | sed 's/:$//')
./configure --with-pydebug
make -j$(nproc)
make test TESTOPTS="-x test_socket -x test_cmd_line -x test_timeout -x test_urllib -x test_urllib2 -x test_urllibnet -x test_asyncio -x test_embed -x test_fcntl -x test_resource -x test_posix -x test_termios -x test_pathlib -x test_os -x test_shutil -x test_curses -x test_asyncore -x test_xml_etree_c -x test_generators -x test_pyrepl -x test_signal" -j$(nproc)
