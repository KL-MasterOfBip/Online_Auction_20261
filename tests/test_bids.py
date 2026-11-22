"""TCP integration tests for requirements 9 and 10 (bidding and room broadcasts)."""
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

    def test_bid_at_maximum_buy_now_price_completes_sale(self):
        item = self.add_item(self.owner, self.room, 'Expensive', 999999990000, 1000000000000)
        self.start()
        self.owner.send(f'NEXT_ITEM {self.room}')
        self.owner.read_line()
        self.owner.read_line()
        self.buyer.read_line()
        self.buyer.read_line()
        self.assertEqual(self.bid(1000000000001, item=item), 'ERROR Invalid price')
        self.assertEqual(self.bid(1000000000000, item=item),
                         f'OK BUY_NOW {item} PRICE 1000000000000')
        self.assertEqual(self.bid(1000000000000, item=item),
                         'ERROR Item is not being auctioned')

    def test_bid_at_buy_now_price_closes_auction_even_below_minimum_increment(self):
        self.start()
        self.owner.cmd(f'JOIN_ROOM {self.room}')
        self.accepted(495000)
        self.assertEqual(self.owner.read_line(), self.event('buyer', 495000))
        self.assertEqual(self.bid(499999), 'ERROR Bid must be at least 505000')
        self.assertEqual(self.bid(500000), f'OK BUY_NOW {self.item} PRICE 500000')
        self.assertEqual(self.owner.read_line(),
                         f'EVENT ITEM_SOLD {self.item} buyer bought it now for 500000 VND.')
        self.assertFalse(self.owner.has_data(.5))
        self.assertEqual(self.bid(510000), 'ERROR Item is not being auctioned')
        self.assertEqual(self.buyer.cmd(f'BUY_NOW {self.item}'), 'ERROR Item is no longer available')
        self.assertEqual(self.owner.cmd(f'NEXT_ITEM {self.room}'), f'OK ITEM_ENDED {self.item} Laptop')
        self.assertEqual(self.owner.read_line(), 'OK AUCTION_FINISHED')
        self.assertEqual(self.buyer.read_line(), 'EVENT AUCTION_FINISHED')
        self.assertEqual(self.read_log().count('method=BUY_NOW'), 1)

    def test_two_clients_compete_against_latest_price(self):
        other = self.make_user('other')
        self.assertEqual(other.cmd(f'JOIN_ROOM {self.room}'), 'OK JOINED_ROOM Shop')
        self.start()
        other.read_line()
        self.buyer.send(f'BID {self.item} 110000')
        other.send(f'BID {self.item} 110000')
        responses = []
        events = []
        for client in (self.buyer, other):
            line = client.read_line()
            if line.startswith('EVENT '):
                events.append(line)
                line = client.read_line()
            responses.append(line)
            if line.startswith('ERROR ') and not events:
                events.append(client.read_line())
        self.assertCountEqual(responses, [f'OK BID_ACCEPTED {self.item} PRICE 110000',
                                          'ERROR Bid must be at least 120000'])
        winner = 'buyer' if responses[0].startswith('OK ') else 'other'
        self.assertEqual(events, [f'EVENT BID_PLACED {self.item} BIDDER {winner} PRICE 110000'])
        self.accepted(120000, other)
        self.assertEqual(self.buyer.read_line(),
                         f'EVENT BID_PLACED {self.item} BIDDER other PRICE 120000')
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

    def test_framing_non_member_owner_and_logging(self):
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


    def event(self, name, price):
        return f'EVENT BID_PLACED {self.item} BIDDER {name} PRICE {price}'

    def test_all_current_members_receive_events_without_sender_duplicate(self):
        self.start()
        viewers = [self.make_user('viewer' + str(i)) for i in range(5)]
        for viewer in viewers:
            viewer.cmd(f'JOIN_ROOM {self.room}')
        self.owner.cmd(f'JOIN_ROOM {self.room}')
        self.accepted(110000)
        for viewer in viewers + [self.owner]:
            self.assertEqual(viewer.read_line(), self.event('buyer', 110000))
            self.assertFalse(viewer.has_data(.03))
        self.assertFalse(self.buyer.has_data(.03))
        self.accepted(120000, viewers[0])
        for viewer in viewers[1:] + [self.owner, self.buyer]:
            self.assertEqual(viewer.read_line(), self.event('viewer0', 120000))
        self.assertFalse(viewers[0].has_data(.03))

    def test_other_rooms_guests_leavers_and_logout_do_not_receive(self):
        self.start()
        guest = self.connect()
        room2 = self.make_room(self.owner, 'Other')
        outsider = self.make_user('outsider')
        outsider.cmd(f'JOIN_ROOM {room2}')
        left = self.make_user('left')
        left.cmd(f'JOIN_ROOM {self.room}')
        left.cmd('LEAVE_ROOM')
        logged_out = self.make_user('logged_out')
        logged_out.cmd(f'JOIN_ROOM {self.room}')
        logged_out.cmd('LOGOUT')
        self.accepted(110000)
        for client in (guest, outsider, left, logged_out, self.owner):
            self.assertFalse(client.has_data(.05))
        left.cmd(f'JOIN_ROOM {self.room}')
        self.assertFalse(left.has_data(.03))
        self.accepted(120000)
        self.assertEqual(left.read_line(), self.event('buyer', 120000))

    def test_rejected_bids_do_not_broadcast_or_change_price(self):
        self.start()
        viewer = self.make_user('viewer')
        viewer.cmd(f'JOIN_ROOM {self.room}')
        self.assertEqual(self.bid(109999), 'ERROR Bid must be at least 110000')
        self.assertEqual(self.bid('abc'), 'ERROR Invalid price')
        self.assertFalse(viewer.has_data(.05))
        self.accepted(110000)
        self.assertEqual(viewer.read_line(), self.event('buyer', 110000))
        self.assertEqual(self.bid(110000), 'ERROR Bid must be at least 120000')
        self.assertFalse(viewer.has_data(.05))

    def test_events_order_after_multiple_commands_and_disconnected_member(self):
        self.start()
        viewer = self.make_user('viewer')
        viewer.cmd(f'JOIN_ROOM {self.room}')
        gone = self.make_user('gone')
        gone.cmd(f'JOIN_ROOM {self.room}')
        gone.close()
        self.buyer.send_raw(f'BID {self.item} 110000\nBID {self.item} 120000\n'.encode())
        for price in (110000, 120000):
            self.assertEqual(self.buyer.read_line(), f'OK BID_ACCEPTED {self.item} PRICE {price}')
            self.assertEqual(viewer.read_line(), self.event('buyer', price))
        self.assertEqual(viewer.cmd('PING'), 'OK PONG')



if __name__ == '__main__':
    unittest.main(verbosity=2)
