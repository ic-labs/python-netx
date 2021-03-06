#!/bin/bash
#
# Test NetX API calls against a test server. Run these tests against a newly
# upgraded NetX test server to ensure the new NetX version is working as
# expected for this module.
#
# Example: ./runtests.sh -u USERNAME -p PASSWORD -s http://example.com
#
usage()
{
    cat <<EOF

Test NetX API calls against a test server. Run these tests against a newly
upgraded NetX test server to ensure the new NetX version is working as
expected for this module.

Usage: $0 [-h] [-u <username>] [-p <password>] [-s <url>] [-a <assets_per_page>]

-h
    Print usage.

-u <username>
    NetX username.

-p <password>
    NetX password.

-s <url>
    NetX server URL.

-a <assets_per_page>
    Assets per page (optional).
EOF
}

while getopts ":u:p:s:a:" opt
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
            url=${OPTARG}
            ;;
        a)
            assets_per_page=${OPTARG}
            ;;
        ?)
            usage >& 2
            exit 1
            ;;
    esac
done

if [ -z ${username} ] || [ -z ${password} ] || [ -z ${url} ]
then
    usage
    exit 1
fi

if [ -z ${assets_per_page} ]
then
    assets_per_page=10
fi

echo "username = ${username}"
echo "password = ${password}"
echo "url = ${url}"
echo "assets_per_page = ${assets_per_page}"

export NETX_USERNAME="${username}"
export NETX_PASSWORD="${password}"
export NETX_URL="${url}"
export ASSETS_PER_PAGE="${assets_per_page}"

python -m unittest tests.test_netx
