import os
import unittest
from netx import NetX


class NetXTests(unittest.TestCase):
    """
    Test NetX API calls against a test server. Run these tests against a newly
    upgraded NetX test server to ensure the new NetX version is working as
    expected for this module.
    """
    def setUp(self):
        self.username = os.environ.get('NETX_USERNAME')
        self.password = os.environ.get('NETX_PASSWORD')
        self.url = os.environ.get('NETX_URL')
        config = {
            'URL': self.url,
            'USERNAME': self.username,
            'PASSWORD': self.password,
        }
        self.api = NetX(config)

        # Tweak this accordingly for your test server. The first category, i.e.
        # root category, and the last category, i.e. category with assets, are
        # both required.
        self.category_path = [
            {'id': 1, 'name': u'netx'},  # Root category
            {'id': 10, 'name': u'Artworks'},
            {'id': 14, 'name': u'Artists M-Q'},
            {'id': 15148, 'name': u'Maar, Dora'},
            {'id': 15149, 'name': u'Double Portrait'},  # Category with assets.
        ]

    def test_login(self):
        session_key = self.api.login()
        self.assertTrue(len(session_key) > 0)

    def test_get_user(self):
        user = self.api.get_user()
        self.assertEqual(user.get('login'), self.username)

    def test_categories(self):
        categories = self.api.categories()
        self.assertTrue(len(categories) > 0)
        self.assertEqual(categories[0].get('parent_id'), 1)

    def test_category_assets(self):
        assets = self.api.category_assets(self.category_path)
        self.assertTrue(len(assets) > 0)
        required_asset_keys = set([
            'assetId',
            'attributeNames',
            'attributeValues',
            'creationdate',
            'filesize',
            'filetypelabel',
            'name',
            'thumbUrl',
        ])
        asset_keys = set(assets[0].keys())
        self.assertTrue(required_asset_keys.issubset(asset_keys))

    def test_carts(self):
        carts = self.api.carts()
        self.assertTrue(len(carts) > 0)
        required_cart_keys = set([
            'cartId',
            'cartName',
            'count',
        ])
        cart_keys = set(carts[0].keys())
        self.assertTrue(required_cart_keys.issubset(cart_keys))

    def test_cart_assets(self):
        cart = self.api.carts()[0]
        assets = self.api.cart_assets(cart.get('cartId'))
        self.assertTrue(len(assets) > 0)
        required_asset_keys = set([
            'assetId',
            'attributeNames',
            'attributeValues',
            'creationdate',
            'filesize',
            'filetypelabel',
            'name',
            'thumbUrl',
        ])
        asset_keys = set(assets[0].keys())
        self.assertTrue(required_asset_keys.issubset(asset_keys))

    def test_get_asset_info(self):
        asset = self.api.category_assets(self.category_path)[0]
        asset_info = self.api.get_asset_info(asset.get('assetId'))
        asset_info_keys = set(asset_info.keys())
        self.assertFalse('attributeNames' in asset_info_keys)
        self.assertFalse('attributeValues' in asset_info_keys)
        required_asset_info_keys = set([
            'assetId',
            'creationdate',
            'filesize',
            'filetypelabel',
            'name',
            'thumbUrl',
        ])
        self.assertTrue(required_asset_info_keys.issubset(asset_info_keys))

    def test_search(self):
        keyword = 'test'
        assets = self.api.search(keyword)
        self.assertTrue(len(assets) == 10)
        for asset in assets:
            self.assertTrue('test' in str(asset).lower())

    def test_file(self):
        asset = self.api.category_assets(self.category_path)[0]
        headers, content = self.api.file(asset.get('assetId'))
        self.assertEqual(len(content), int(headers.get('Content-Length')))


if __name__ == '__main__':
    unittest.main()
