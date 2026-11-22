"""TCP integration tests for requirement 9 (no bid broadcast or timer)."""
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests' / 'ADD_ITEM tests 02'))
import item_test_base as base

# The existing helper was moved into a subfolder; resolve source from this file.
base.ROOT = str(ROOT)
base.SRC = str(ROOT / 'src')


class BidTests(base.ServerTestCase):
    def setUp(self):
        super().setUp()
        self.owner = self.make_user('seller')
        self.room = self.make_room(self.owner, 'Shop')
        self.item = self.add_item(self.owner, self.room, 'Laptop', 100000, 500000)
        self.buyer = self.make_user('buyer')
        self.assertEqual(self.buyer.cmd(f'JOIN_ROOM {self.room}'), 'OK JOINED_ROOM Shop')

    def start(self):
        self.assertTrue(self.owner.cmd(f'START_AUCTION {self.room}').startswith('OK AUCTION_STARTED'))
        self.assertTrue(self.buyer.read_line().startswith('EVENT ITEM_STARTED'))

    def bid(self, price, client=None, item=None):
        return (client or self.buyer).cmd(f'BID {item or self.item} {price}')

    def accepted(self, price, client=None, item=None):
        self.assertEqual(self.bid(price, client, item),
                         f'OK BID_ACCEPTED {item or self.item} PRICE {price}')

    def test_first_bid_requires_start_price_plus_10000(self):
        self.start()
        for price in (90000, 100000, 109999):
            self.assertEqual(self.bid(price), 'ERROR Bid must be at least 110000')
        self.accepted(110000)

    def test_rejected_bid_does_not_change_price_or_leader(self):
        self.start()
        self.accepted(110000)
        for price in (100000, 110000, 119999):
            self.assertEqual(self.bid(price), 'ERROR Bid must be at least 120000')
        self.accepted(120000)
        self.accepted(200000)
        self.assertEqual(self.bid(209999), 'ERROR Bid must be at least 210000')

    def test_auth_membership_and_seller_checks(self):
        self.start()
        guest = self.connect()
        self.assertEqual(self.bid(110000, guest), 'ERROR Not logged in')
        outsider = self.make_user('outsider')
        self.assertEqual(self.bid(110000, outsider), 'ERROR Not in item room')
        self.assertEqual(self.owner.cmd(f'JOIN_ROOM {self.room}'), 'OK JOINED_ROOM Shop')
        self.assertEqual(self.bid(110000, self.owner), 'ERROR Cannot bid on own item')
        self.assertEqual(self.buyer.cmd('LEAVE_ROOM'), 'OK LEFT_ROOM')
        self.assertEqual(self.bid(110000), 'ERROR Not in item room')
        self.assertEqual(self.buyer.cmd(f'JOIN_ROOM {self.room}'), 'OK JOINED_ROOM Shop')
        self.accepted(110000)
        self.assertEqual(self.buyer.cmd('LOGOUT'), 'OK Logout successful')
        self.assertEqual(self.bid(120000), 'ERROR Not logged in')

    def test_only_current_auctioning_item_can_receive_bids(self):
        self.assertEqual(self.bid(110000), 'ERROR Item is not being auctioned')
        next_id = self.add_item(self.owner, self.room, 'Phone', 200000, 600000)
        self.start()
        self.assertEqual(self.bid(210000, item=next_id), 'ERROR Item is not being auctioned')
        self.owner.send(f'NEXT_ITEM {self.room}')
        self.owner.read_line()
        self.owner.read_line()
        self.buyer.read_line()
        self.buyer.read_line()
        self.assertEqual(self.bid(110000), 'ERROR Item is not being auctioned')
        self.accepted(210000, item=next_id)

    def test_invalid_arguments_and_numeric_boundaries(self):
        self.start()
        for cmd in ('BID', 'BID 1', 'BID 1 110000 extra'):
            self.assertEqual(self.buyer.cmd(cmd), 'ERROR Invalid command or arguments')
        for item in ('abc', '0', '-1', '2147483648'):
            self.assertEqual(self.buyer.cmd(f'BID {item} 110000'), 'ERROR Invalid item ID')
        self.assertEqual(self.bid(110000, item=999), 'ERROR Item not found')
        for price in ('0', '-1', '+110000', '1.5', 'abc', '1e6', '1000000000001', '9' * 40):
            self.assertEqual(self.bid(price), 'ERROR Invalid price')
        self.accepted(110000)

    def test_maximum_price_cannot_overflow_or_wrap(self):
        item = self.add_item(self.owner, self.room, 'Expensive', 999999990000, 1000000000000)
        self.start()
        self.owner.send(f'NEXT_ITEM {self.room}')
        self.owner.read_line()
        self.owner.read_line()
        self.buyer.read_line()
        self.buyer.read_line()
        self.accepted(1000000000000, item=item)
        self.assertEqual(self.bid(1000000000000, item=item),
                         'ERROR Bid must be at least 1000000010000')
        self.assertEqual(self.bid('1000000010000', item=item), 'ERROR Invalid price')

    def test_two_clients_compete_against_latest_price(self):
        other = self.make_user('other')
        self.assertEqual(other.cmd(f'JOIN_ROOM {self.room}'), 'OK JOINED_ROOM Shop')
        self.start()
        other.read_line()
        self.buyer.send(f'BID {self.item} 110000')
        other.send(f'BID {self.item} 110000')
        responses = [self.buyer.read_line(), other.read_line()]
        self.assertCountEqual(responses, [f'OK BID_ACCEPTED {self.item} PRICE 110000',
                                          'ERROR Bid must be at least 120000'])
        self.accepted(120000, other)
        self.assertEqual(self.bid(120000), 'ERROR Bid must be at least 130000')

    def test_different_rooms_have_independent_prices(self):
        room2 = self.make_room(self.owner, 'OtherRoom')
        item2 = self.add_item(self.owner, room2, 'Phone', 200000, 900000)
        other = self.make_user('other')
        other.cmd(f'JOIN_ROOM {room2}')
        self.start()
        self.owner.cmd(f'START_AUCTION {room2}')
        other.read_line()
        self.accepted(110000)
        self.assertEqual(self.bid(210000, item=item2), 'ERROR Not in item room')
        self.accepted(210000, other, item2)
        self.accepted(120000)

    def test_framing_no_broadcast_and_logging(self):
        self.start()
        self.buyer.send_raw(f'BID {self.item} 110'.encode())
        self.buyer.send_raw(f'000\nBID {self.item} 120000\n'.encode())
        self.assertEqual(self.buyer.read_line(), f'OK BID_ACCEPTED {self.item} PRICE 110000')
        self.assertEqual(self.buyer.read_line(), f'OK BID_ACCEPTED {self.item} PRICE 120000')
        self.assertFalse(self.owner.has_data())
        self.assertEqual(self.read_log().count('BID_ACCEPTED'), 2)
        self.assertIn('username=buyer price=120000', self.read_log())

    def test_next_item_cannot_report_no_sale_after_a_bid_or_reconnect(self):
        self.start()
        self.accepted(110000)
        self.assertEqual(self.owner.cmd(f'NEXT_ITEM {self.room}'), 'ERROR Cannot skip item with bids')
        self.assertEqual(self.buyer.cmd('LOGOUT'), 'OK Logout successful')
        self.buyer.close()
        again = self.connect()
        self.assertEqual(again.cmd('LOGIN buyer ' + self.password), 'OK Login successful')
        again.cmd(f'JOIN_ROOM {self.room}')
        self.assertEqual(self.bid(110000, again), 'ERROR Bid must be at least 120000')
        self.accepted(120000, again)
        self.assertEqual(self.owner.cmd(f'NEXT_ITEM {self.room}'), 'ERROR Cannot skip item with bids')


if __name__ == '__main__':
    unittest.main(verbosity=2)
