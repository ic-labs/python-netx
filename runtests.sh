#!/bin/bash
#
# Test NetX API calls against a test server. Run these tests against a newly
# upgraded NetX test server to ensure the new NetX version is working as
# expected for this module.
#
# Example: ./runtests.sh -u USERNAME -p PASSWORD -s netxtest.sfmoma.org
#
usage()
{
    cat <<EOF

Test NetX API calls against a test server. Run these tests against a newly
upgraded NetX test server to ensure the new NetX version is working as
expected for this module.

Usage: $0 [-h] [-u <username>] [-p <password>] [-s <server>]

-h
    Print usage.

-u <username>
    NetX username.

-p <password>
    NetX password.

-s <server>
    NetX hostname.

EOF
}

while getopts ":u:p:s:" opt
do
    case "$opt" in
        h)
            usage
            exit 0
            ;;
        u)
            username=${OPTARG}
            ;;
        p)
            password=${OPTARG}
            ;;
        s)
            server=${OPTARG}
            ;;
        ?)
            usage >& 2
            exit 1
            ;;
    esac
done

if [ -z ${username} ] || [ -z ${password} ] || [ -z ${server} ]
then
    usage
    exit 1
fi

echo "username = ${username}"
echo "password = ${password}"
echo "server = ${server}"

export NETX_USERNAME="${username}"
export NETX_PASSWORD="${password}"
export NETX_URL="http://${server}"

python -m unittest tests.test_netx
