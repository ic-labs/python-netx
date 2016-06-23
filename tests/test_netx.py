import os
import time
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
        self.assets_per_page = os.environ.get('ASSETS_PER_PAGE')
        config = {
            'URL': self.url,
            'USERNAME': self.username,
            'PASSWORD': self.password,
            'ASSETS_PER_PAGE': int(self.assets_per_page),
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

    def test_file(self):
        asset = self.api.category_assets(self.category_path)[0]

        headers, content = self.api.file(asset.get('assetId'))
        self.assertEqual(len(content), int(headers.get('Content-Length')))

        headers, content = self.api.file(asset.get('assetId'), stream=True)
        self.assertEqual(len(content), int(headers.get('Content-Length')))

        headers, original_content = \
            self.api.file(asset.get('assetId'), data='original')
        self.assertEqual(
            len(original_content), int(headers.get('Content-Length')))
        self.assertTrue(len(original_content) > len(content))

    def test_prepare_jpeg(self):
        asset = self.api.category_assets(self.category_path)[0]

        job_started = self.api.prepare_asset_with_preset(asset.get('assetId'))
        self.assertTrue(job_started)

        percent = 0
        while percent < 100:
            progress = self.api.progress()
            percent = progress.get('percentComplete')
            time.sleep(0.2)

        result = self.api.get_prepared_asset()
        jpeg_name = result.get('name')
        self.assertTrue(jpeg_name.endswith('.jpg'))
        self.assertEqual(asset.get('name'), jpeg_name.rstrip('.jpg'))
        path = result.get('path')
        self.assertTrue(len(path) > 0)


if __name__ == '__main__':
    unittest.main()
