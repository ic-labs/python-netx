"""
Backend implementation for NetX Digital Asset Management.
"""

import json
import logging
import random
import requests
import time
from contextlib import closing
requests.packages.urllib3.disable_warnings()

from . import __version__

DEFAULT_ASSETS_PER_PAGE = 10
DEFAULT_TIMEOUT = 60  # Requests timeout in seconds
DEFAULT_REQUESTS_PER_SECOND = 1

#
# Constants for JSON-RPC X7 API
#

# Sort order
SORT_ORDER_ASCENDING = 0
SORT_ORDER_DESCENDING = 1

# Search types
SEARCH_TYPE_KEYWORDS = 1
SEARCH_TYPE_CONTENTS = 2
SEARCH_TYPE_METADATA = 3
SEARCH_TYPE_DATE = 4
SEARCH_TYPE_CATEGORY = 5
SEARCH_TYPE_FILE_FORMAT = 6
SEARCH_TYPE_FILE_SIZE = 7
SEARCH_TYPE_RAW = 8
SEARCH_TYPE_CUSTOM = 9
SEARCH_TYPE_CART = 10
SEARCH_TYPE_RELATED_ASSETS = 11
SEARCH_TYPE_LAST_SEARCH = 12
SEARCH_TYPE_CHECKOUT = 13
SEARCH_TYPE_THESAURUS = 14
SEARCH_TYPE_BRANCH_CHILDREN = 15
SEARCH_TYPE_REVIEWS = 16
SEARCH_TYPE_EXPIRE = 17
SEARCH_TYPE_METADATA_HISTORY = 18
SEARCH_TYPE_RATING = 19
SEARCH_TYPE_LOCATION = 20
SEARCH_TYPE_PROOF = 21
SEARCH_TYPE_FILE_ASPECT = 22

# Keyword/contents/metadata sub-types
QUERY_TYPE_AND = 0
QUERY_TYPE_EXACT = 1
QUERY_TYPE_OR = 2
QUERY_TYPE_NOT = 3
QUERY_TYPE_AND_FRAG = 4
QUERY_TYPE_OR_FRAG = 5
QUERY_TYPE_RANGE = 6
QUERY_TYPE_PHRASE = 7
QUERY_TYPE_RAW = 8
QUERY_TYPE_EMPTY = 9

# Category sub-types 1
CATEGORY_TYPE_ONLY_RECURSIVE = 0
CATEGORY_TYPE_EXCLUDE_RECURSIVE = 1
CATEGORY_TYPE_ONLY = 2
CATEGORY_TYPE_EXCLUDE = 3
CATEGORY_TYPE_RECURSIVE = 4

# Notify types
NOTIFY_TYPE_NONE = 0
NOTIFY_TYPE_WEEKLY = 1
NOTIFY_TYPE_DAILY = 2
NOTIFY_TYPE_IMMEDIATELY = 3

LOGGER = logging.getLogger(__name__)


class SettingsError(Exception):
    """
    Exception used when backend settings are not configured.
    """
    pass


class ResponseError(Exception):
    """
    Exception used when we receive unexpected response from origin server.
    """
    pass


class NetX(object):
    """
    Implements the API endpoints for this backend.

    Target URL: http://API_URL/DATA_TYPE

    DATA_TYPE
    1) json/x7/ (JSON-RPC X7 API, IN DRAFT)
    """
    def __init__(self, settings):
        """
        Initialises authenticated instance of this class.
        Requires settings dict containing the root URL for the API endpoints,
        username and password.
        """
        self.root_url = settings.get('URL', None)
        self.username = settings.get('USERNAME', None)
        self.password = settings.get('PASSWORD', None)
        self.assets_per_page = settings.get(
            'ASSETS_PER_PAGE', DEFAULT_ASSETS_PER_PAGE)
        self.timeout = settings.get('TIMEOUT', DEFAULT_TIMEOUT)
        self.requests_per_second = settings.get(
            'REQUESTS_PER_SECOND', DEFAULT_REQUESTS_PER_SECOND)
        data_type = settings.get('DATA_TYPE', 'x7/json/')
        self.label = self.__class__.__name__.lower()
        self.sent_nonce = None  # For use in JSON-RPC calls
        self.api_url = None
        self.last_request = None  # Epoch in ms for use to limit requests/sec
        if self.root_url:
            self.api_url = '%s/%s' % (self.root_url, data_type)

    @property
    def session_key(self):
        if not getattr(self, '_session_key', None):
            self._session_key = self.login()
        return self._session_key

    @property
    def user(self):
        if not getattr(self, '_user', None):
            self._user = self.get_user()
        return self._user

    def _restore_connection(self):
        delattr(self, '_session_key')
        delattr(self, '_user')
        _ = self.session_key
        _ = self.user

    def _nonce(self):
        """
        Generates and returns a new nonce for use in JSON-RPC calls.
        """
        self.sent_nonce = str(random.getrandbits(64))
        return self.sent_nonce

    def _get_endpoint(self):
        """
        Returns validated endpoint for making an API call.
        Endpoints for JSON-RPC X7 API are the same as the root URL.
        """
        if self.api_url is None:
            raise SettingsError("URL is not set in settings.")
        return self.api_url

    def _requests_limiter(self):
        """
        Limit number of outgoing requests per second.
        """
        if self.last_request is None:
            return
        rps = float(self.requests_per_second)
        min_elapsed_ms = 1000 / rps
        elapsed_ms = 0
        while elapsed_ms < min_elapsed_ms:
            time.sleep(0.001)  # Sleep for 1 ms
            now_ms = int(time.time() * 1000)
            elapsed_ms = now_ms - self.last_request
        return

    def _get(self, url, params=None, **kwargs):
        """
        Wraps HTTP GET request with the specified params. Returns the HTTP
        response.
        """
        headers = {
            'user-agent': 'python-netx/%s' % __version__,
        }
        cookies = {
            'sessionKey': self.session_key,
        }
        kwargs.update(dict(
            headers=headers,
            params=params,
            cookies=cookies,
            verify=False,
            timeout=self.timeout,
        ))
        response_headers = None
        response_content = None
        self._requests_limiter()
        with closing(requests.get(url, **kwargs)) as response:
            if response.status_code != 200:
                raise ResponseError(
                    '%s returned HTTP%d' % (url, response.status_code))
            self.last_request = int(time.time() * 1000)
            if kwargs.get('stream'):
                filesize = float(response.headers['content-length']) / 1024
                LOGGER.info('streaming %s: %.2fKB', url, filesize)
            response_headers = response.headers
            response_content = response.content  # Read or stream now.
        return (response_headers, response_content)

    def _json_post(self, context, retries=3):
        """
        Wraps HTTP POST request with the specified data. Returns dict decoded
        from the JSON response.
        """
        cookies = None
        if context['method'] != 'authenticate':
            cookies = {
                'sessionKey': self.session_key,
            }
        data = {
            'id': self._nonce(),
            'dataContext': 'json',
            'jsonrpc': '2.0',
        }
        data.update(context)
        data = json.dumps(data)  # Origin server expects JSON-encoded POST data
        url = self._get_endpoint()
        headers = {
            'user-agent': 'python-netx/%s' % __version__,
            'content-type': 'application/json',
        }

        # Retry if we get intermittent connection error
        self._requests_limiter()
        try:
            response = requests.post(
                url, headers=headers, data=data, cookies=cookies, verify=False,
                timeout=self.timeout)
        except requests.exceptions.ConnectionError as err:
            if context['method'] != 'authenticate' and retries > 1:
                LOGGER.info('retry (%d): %s', retries - 1, context)
                self._json_post(context, retries=retries - 1)
            else:
                raise ResponseError(err)

        if response.status_code != 200:
            raise ResponseError(
                '%s returned HTTP%d' % (url, response.status_code))
        self.last_request = int(time.time() * 1000)
        response = response.json()
        nonce = response.get('id', None)
        if nonce != self.sent_nonce:
            raise ResponseError(
                'Mismatched nonce: %s != %s\n'
                'Request: %s\n'
                'Response: %s' % (nonce, self.sent_nonce, data, response))
        # Reraise exception returned by origin server
        error = response.get('error', None)
        if error:
            msg = '%s returned %s, self.user=%s, self.session_key=%s' % (
                url, error, self.user, self.session_key)
            # Retry if we have a stale connection
            if context['method'] != 'authenticate' and retries > 1:
                self._restore_connection()
                return self._json_post(context, retries=retries - 1)
            else:
                raise ResponseError(msg)

        return response

    def login(self):
        """
        Sends authenticate command to authenticate a user based on the supplied
        credential and returns the session key for use by subsequent API calls.
        """
        context = {
            'method': 'authenticate',
            'params': [self.username, self.password],
        }
        response = self._json_post(context=context)
        session_key = response.get('result', None)
        if session_key is None or session_key == "-1":
            raise SettingsError("Invalid USERNAME or PASSWORD in settings.")
        return session_key

    def get_user(self):
        """
        Sends getSelf command to get user dict for authenticated user.
        """
        context = {
            'method': 'getSelf',
            'params': [],
        }
        response = self._json_post(context=context)
        return response.get('result')

    def categories(self, category_id=1):
        """
        Sends getCategories command to list all available sub categories.
        category_id=1 returns the list of top-level categories.
        Returns list of sub categories.
        """
        category_id = int(category_id)

        keyword = ''  # Unused
        context = {
            'method': 'getCategories',
            'params': [keyword, category_id],
        }
        response = self._json_post(context=context)

        categories = []
        raw_categories = response.get('result', [])
        for category in raw_categories:
            assert category['parentid'] == category_id
            categories.append({
                'id': category['categoryid'],
                'parent_id': category['parentid'],
                'name': category['name'],
                'children': category['children'],
            })
        return categories

    def category_assets(self, category_path, page_num=1, filters=None):
        """
        Sends searchAssetBeanObjects command to list assets in the given
        category. Results are paginated.
        """
        # page_num  start_index  assets
        #        1            1  [ 1  2  3  4  5  6  7  8  9 10]
        #        2           11  [11 12 13 14 15 16 17 18 19 20]
        #        3           21  [21 22 23 24 25 26 27 28 29 30]
        #        4           31  [31 32 33 34 35 36 37 38 39 40]
        start_index = ((page_num - 1) * self.assets_per_page) + 1

        values_1 = '/'.join([entry['name'] for entry in category_path][1:])

        # Example filters to exclude assets with:
        # '<some filter value>' = '<some filter>'
        # filters = [
        #     [
        #         SEARCH_TYPE_CATEGORY,
        #         SEARCH_TYPE_METADATA,
        #     ],                          # types
        #     [
        #         CATEGORY_TYPE_ONLY,
        #         QUERY_TYPE_NOT,
        #     ],                          # sub-types 1
        #     [0, 0],                     # sub-types 2
        #     [
        #         values_1,
        #         '<some filter value>',
        #     ],                          # values 1 (path to category)
        #     [
        #         '',
        #         '<some filter>',
        #     ],                          # values 2
        #     ['', ''],                   # values 3
        # ]
        if filters is None:  # Use default filters
            filters = [
                [SEARCH_TYPE_CATEGORY],     # types
                [CATEGORY_TYPE_ONLY],       # sub-types 1
                [0],                        # sub-types 2
                [values_1],                 # values 1 (path to category)
                [''],                       # values 2
                [''],                       # values 3
            ]

        params = [
            'name',                     # sort by name
            SORT_ORDER_DESCENDING,
            QUERY_TYPE_AND,
        ] + filters + [
            None,                       # name of saved search
            NOTIFY_TYPE_NONE,
            0,                          # don't record in stats
            start_index,
            self.assets_per_page,
        ]

        context = {
            'method': 'searchAssetBeanObjects',
            'params': params,
        }
        response = self._json_post(context=context)
        return response.get('result')

    def carts(self):
        """
        Sends getUserCarts command to list all carts available to current user.
        """
        context = {
            'method': 'getUserCarts',
            'params': [self.user['userId'], 'all'],
        }
        response = self._json_post(context=context)
        return response.get('result')

    def cart_assets(self, cart_id, page_num=1, filters=None):
        """
        Sends searchAssetBeanObjects command to list assets in the given cart.
        Results are paginated.
        """
        start_index = ((page_num - 1) * self.assets_per_page) + 1

        # Example filters to exclude assets with:
        # '<some filter value>' = '<some filter>'
        # filters = [
        #     [
        #         SEARCH_TYPE_CART,
        #         SEARCH_TYPE_METADATA,
        #     ],                              # types
        #     [
        #         QUERY_TYPE_AND_FRAG,
        #         QUERY_TYPE_NOT,
        #     ],                              # sub-types 1
        #     [0, 0],                         # sub-types 2
        #     [
        #         cart_id,
        #         '<some filter value>',
        #     ],                              # values 1 (cart ID)
        #     [
        #         '',
        #         '<some filter>',
        #     ],                              # values 2
        #     ['', ''],                       # values 3
        # ]
        if filters is None:  # Use default filters
            filters = [
                [SEARCH_TYPE_CART],             # types
                [QUERY_TYPE_AND_FRAG],          # sub-types 1
                [0],                            # sub-types 2
                [cart_id],                      # values 1 (cart ID)
                [''],                           # values 2
                [''],                           # values 3
            ]

        params = [
            'name',                     # sort by name
            SORT_ORDER_DESCENDING,
            QUERY_TYPE_AND,
        ] + filters + [
            None,                       # name of saved search
            NOTIFY_TYPE_NONE,
            0,                          # don't record in stats
            start_index,
            self.assets_per_page,
        ]

        context = {
            'method': 'searchAssetBeanObjects',
            'params': params,
        }
        response = self._json_post(context=context)
        return response.get('result')

    def get_asset_info(self, asset_id):
        """
        Sends getAssetBean command to get asset info with `attributeNames` and
        `attributeValues` appearing in key-value format instead of two separate
        lists.
        """
        context = {
            'method': 'getAssetBean',
            'params': [asset_id],
        }
        response = self._json_post(context=context)
        result = response.get('result', {})
        attrs = dict(zip(result['attributeNames'], result['attributeValues']))
        del result['attributeNames']
        del result['attributeValues']
        result['attributes'] = attrs
        return result

    def search(self, keyword, page_num=1, filters=None):
        """
        Sends searchAssetBeanObjects command to search assets based on the
        given keyword. Results are paginated.
        """
        start_index = ((page_num - 1) * self.assets_per_page) + 1

        # Example filters to exclude assets with:
        # '<some filter value>' = '<some filter>'
        # filters = [
        #     [
        #         SEARCH_TYPE_KEYWORDS,
        #         SEARCH_TYPE_THESAURUS,
        #         SEARCH_TYPE_METADATA,
        #     ],                              # types
        #     [
        #         QUERY_TYPE_AND_FRAG,
        #         QUERY_TYPE_OR,
        #         QUERY_TYPE_NOT,
        #     ],                              # sub-types 1
        #     [0, 0, 0],                      # sub-types 2
        #     [
        #         keyword,
        #         keyword,
        #         '<some filter value>',
        #     ],                              # values 1 (keywords)
        #     [
        #         '',
        #         '',
        #         '<some filter>',
        #     ],                              # values 2
        #     ['', '', ''],                   # values 3
        # ]
        if filters is None:  # Use default filters
            filters = [
                [
                    SEARCH_TYPE_KEYWORDS,
                    SEARCH_TYPE_THESAURUS,
                ],                              # types
                [
                    QUERY_TYPE_AND_FRAG,
                    QUERY_TYPE_OR,
                ],                              # sub-types 1
                [0, 0],                         # sub-types 2
                [keyword, keyword],             # values 1 (keywords)
                ['', ''],                       # values 2
                ['', ''],                       # values 3
            ]

        params = [
            'name',                     # sort by name
            SORT_ORDER_DESCENDING,
            QUERY_TYPE_AND,
        ] + filters + [
            None,                       # name of saved search
            NOTIFY_TYPE_NONE,
            0,                          # don't record in stats
            start_index,
            self.assets_per_page,
        ]

        context = {
            'method': 'searchAssetBeanObjects',
            'params': params,
        }
        response = self._json_post(context=context)
        return response.get('result')

    def file_url(self, asset_id, data='zoom'):
        return self.root_url + '/file/asset/' + str(asset_id) + '/' + data

    def file(self, asset_id, data='zoom', stream=False):
        """
        Downloads the asset using file command. Asset must be an image.
        Returns a tuple containing the response header and content of the file
        in bytes.

        data can be one of the following:
        1) original - the Asset original file.
        2) thumb - the thumbnail of the Asset (150 pixels)
        3) preview - the preview of the Asset (500 pixels)
        4) zoom - the zoom file for the Asset (default is 1000 pixels)
        """
        url = self.file_url(asset_id, data)
        headers, content = self._get(url, stream=stream)
        return (headers, content)

    def prepare_asset_with_preset(self, asset_id, preset=2):
        """
        Sends repurposeAssetsWithPresetProcess command to initiate creation
        of large JPEG file (preset=2) for the asset on origin server.
        Returns True if job is started successfully.
        """
        context = {
            'method': 'repurposeAssetsWithPresetProcess',
            'params': [
                [asset_id],  # asset ids
                [],          # other ids
                preset,      # preset id, 2 for 'Large JPEG (5x7)'
                '',          # download override, e.g. 'thumb', 'preview'
            ],
        }
        response = self._json_post(context=context)
        result = response.get('result', {})
        return result

    def prepare_asset_with_params(self, asset_id, params, values):
        """
        Sends repurposeAssetsWithPresetProcess command to initiate creation
        of large JPEG file (preset=2) for the asset on origin server.
        Returns True if job is started successfully.
        """
        # first check whether repurpose is available
        context = {
            'method': 'getAssetObjects',
            'params': [[asset_id]],
        }
        response = self._json_post(context=context)
        result = response.get('result', {})
        try:
            can_repurpose = result[0]['repurposeAvailability']
        except (KeyError, IndexError):
            raise ResponseError("NetX did not tell me whether it can repurpose asset %s" % asset_id)

        if not can_repurpose:
            # inject "HTTP405" so as to trigger deletion in the ResponseError catcher
            raise ResponseError("Pseudo HTTP405: Repurpose of asset %s not available (usually because the image isn't available)" % asset_id)

        context = {
            'method': 'repurposeAssets',
            'params': [
                [asset_id],  # asset ids
                [],          # other ids
                params,      # ex: ['height', 'dpi']
                values,      # ex: [1000, 300]
            ],
        }
        response = self._json_post(context=context)
        result = response.get('result', {})
        if not result:
            # inject "HTTP403" so as to trigger deletion in the ResponseError catcher
            raise ResponseError("Pseudo HTTP403: NetX did not want to repurpose asset %s" % asset_id)
        return result

    def progress(self):
        """
        Sends getProgressReport command to get progress of the last job, e.g.
        triggered by repurposeAssetsWithPresetProcess command. Returns dict
        containing the progress.

        Example:
        {
            'completeUrl': '',
            'details': 'Processing (1/1) : 0.0%',
            'estimatedTime': '',
            'increment': 0,
            'jobTitle': 'Processing Asset',
            'notifyOnComplete': False,
            'percentComplete': 0,
            'runningTime': 0,
            'runningTimeLabel': '',
            'secondsToReload': 0,
            'startTime': 1451979500852,
            'userId': 0
        }
        """
        context = {
            'method': 'getProgressReport',
            'params': [0],
        }
        response = self._json_post(context=context)
        result = response.get('result', {})
        return result

    def get_prepared_asset(self):
        """
        Sends getShareBean command to get prepared asset. Returns dict
        containing path to download the prepared asset.

        Example:
        {
            'appendMetadata': True,
            'errorCatastrophe': '',
            'errorMessage': '',
            'fileSize': 93336,
            'hoursToLive': 24,
            'messages': [],
            'name': 'PGPH03.144 01_d04.jpg',
            'path': '/session/22901041f9a54bebddf385bba147ed03/PGPH03.144%2001_d04.jpg',
            'realPath': 'M:\\appFiles\\session\\22901041f9a54bebddf385bba147ed03\\PGPH03.144 01_d04.jpg',
            'size': '93 KB',
            'sizeUncompressed': '93 KB',
            'warningMessage': ''
        }
        """
        context = {
            'method': 'getShareBean',
            'params': [],
        }
        response = self._json_post(context=context)
        result = response.get('result', {})
        return result

    def get_prepared_asset_content(self, path, stream=True):
        """
        Downloads the prepared asset denoted by `path`. The asset must be an image.

        Returns a tuple containing the response header and content of the file
        in bytes.

        Usage example:
        ```
            prepared_asset = api.get_prepared_asset()
            prepared_asset_path = prepared_asset['path']
            original_headers, original_content = api.get_prepared_asset_content(prepared_asset_path)
        ```
        """
        url = self.root_url + path
        return self._get(url, stream=stream)

    def get_preset_process_ids(self):
        context = {
            'method': 'getAllPresetProcesses',
            'params': []
        }

        response = self._json_post(context=context)
        return response['result']

    def get_preset_process_data(self, preset_id):
        context = {
            'method': 'getPresetProcessData',
            'params': [preset_id]
        }

        response = self._json_post(context=context)
        return response['result']
