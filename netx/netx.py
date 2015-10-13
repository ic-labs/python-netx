"""
Backend implementation for NetX Digital Asset Management.
"""

import json
import random
import requests
from . import __version__

DEFAULT_ASSETS_PER_PAGE = 10

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

    API_URL
    1) http://netx.sfmoma.org (production)
    2) http://netxtest.sfmoma.org (staging)

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
        data_type = settings.get('DATA_TYPE', 'x7/json/')
        self.label = self.__class__.__name__.lower()
        self.sent_nonce = None  # For use in JSON-RPC calls
        self.api_url = None
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

    def _get(self, url, params=None):
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
        response = requests.get(
            url, headers=headers, params=params, cookies=cookies)
        if response.status_code != 200:
            raise ResponseError(
                '%s returned HTTP%d' % (url, response.status_code))
        return response

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
        response = requests.post(
            url, headers=headers, data=data, cookies=cookies)
        if response.status_code != 200:
            raise ResponseError(
                '%s returned HTTP%d' % (url, response.status_code))
        response = response.json()
        nonce = response.get('id', None)
        if nonce != self.sent_nonce:
            raise ResponseError("""Mismatched nonce: %s != %s
Request:  %s
Response: %s"""
                % (nonce, self.sent_nonce, data, response)
            )

        # Reraise exception returned by origin server
        error = response.get('error', None)
        if error:
            msg = '%s returned %s, self.user=%s, self.session_key=%s' % (
                url, error, self.user, self.session_key)
            # Retry if we have a stale connection
            if context['method'] != 'authenticate' and retries > 1:
                self._restore_connection()
                self._json_post(context, retries=retries - 1)
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
        # 'ask Source Department' = 'Can SFMOMA use it?'
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
        #         'ask Source Department',
        #     ],                          # values 1 (path to category)
        #     [
        #         '',
        #         'Can SFMOMA use it?',
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
        # 'ask Source Department' = 'Can SFMOMA use it?'
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
        #         'ask Source Department',
        #     ],                              # values 1 (cart ID)
        #     [
        #         '',
        #         'Can SFMOMA use it?',
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

        context = {
            'method': 'getAssetBean',
            'params': [asset_id],
        }

        response = self._json_post(context=context)

        result = response.get('result', {})

        attrs = dict(
            zip(
                result['attributeNames'],
                result['attributeValues']
            )
        )

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
        # 'ask Source Department' = 'Can SFMOMA use it?'
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
        #         'ask Source Department',
        #     ],                              # values 1 (keywords)
        #     [
        #         '',
        #         '',
        #         'Can SFMOMA use it?',
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

    def file(self, asset_id, data='zoom'):
        """
        Downloads the asset using file command. Asset must be an image.
        Returns a tuple containing the response header and content of the file
        in bytes.

        data can be one of the following:
        1) original - the Asset original file.
        2) thumb - the thumbnail of the Asset (150 pixels)
        3) preview - the preview of the Asset (500 pixels)
        4) zoom - the zoom file for the Asset (default is 2000 pixels)
        """
        url = self.root_url + '/file/asset/' + str(asset_id) + '/' + data
        response = self._get(url)
        return (response.headers, response.content)
