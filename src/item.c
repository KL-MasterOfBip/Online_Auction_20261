#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <string.h>
#include <time.h>
#include "common.h"
#include "item.h"
#include "room.h"
#include "logger.h"

#ifndef BID_IDLE_MS
#define BID_IDLE_MS 180000LL
#endif
#ifndef BID_CALL_INTERVAL_MS
#define BID_CALL_INTERVAL_MS 60000LL
#endif

static long long monotonic_ms(void) {
    struct timespec now;
    if (clock_gettime(CLOCK_MONOTONIC, &now) < 0) {
        return -1;
    }
    return (long long)now.tv_sec * 1000 + now.tv_nsec / 1000000;
}

int find_item_by_id(int item_id) {
    for (int i = 0; i < MAX_ITEMS; i++) {
        if (items[i].is_active && items[i].item_id == item_id) {
            return i;
        }
    }

    return -1;
}

const char *item_status_name(ItemStatus status) {
    if (status == ITEM_AUCTIONING) {
        return "AUCTIONING";
    }
    if (status == ITEM_ENDED) {
        return "ENDED";
    }
    return "PENDING";
}

int count_room_items(int room_id) {
    int count = 0;

    for (int i = 0; i < MAX_ITEMS; i++) {
        if (items[i].is_active && items[i].room_id == room_id) {
            count++;
        }
    }

    return count;
}

static int find_next_item(int room_id, int after_id) {
    int best = -1;

    for (int i = 0; i < MAX_ITEMS; i++) {
        if (!items[i].is_active || items[i].room_id != room_id ||
            items[i].item_id <= after_id) {
            continue;
        }
        if (best < 0 || items[i].item_id < items[best].item_id) {
            best = i;
        }
    }

    return best;
}

static int find_first_pending_item(int room_id) {
    int best = -1;

    for (int i = 0; i < MAX_ITEMS; i++) {
        if (!items[i].is_active || items[i].room_id != room_id ||
            items[i].status != ITEM_PENDING) {
            continue;
        }
        if (best < 0 || items[i].item_id < items[best].item_id) {
            best = i;
        }
    }

    return best;
}

static void describe_item(const AuctionItem *item, char *output, size_t size) {
    snprintf(output, size, "%d %s START %lld BUYNOW %lld",
             item->item_id, item->name, item->start_price,
             item->buy_now_price);
}

static void begin_item(int room_index, int item_index) {
    items[item_index].status = ITEM_AUCTIONING;
    rooms[room_index].current_item_id = items[item_index].item_id;

    log_event("AUCTION_ITEM_STARTED room_id=%d item_id=%d name=%s",
              rooms[room_index].room_id, items[item_index].item_id,
              items[item_index].name);
}

void add_item(int client_index,
              int room_id,
              const char *name,
              long long start_price,
              long long buy_now_price) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    int room_index = find_room_by_id(room_id);
    if (room_index < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    if (!is_room_owner(client->user_index, room_index)) {
        send_message(client->socket_fd, "ERROR Not room owner\n");
        return;
    }

    if (start_price <= 0 || start_price > MAX_PRICE ||
        buy_now_price <= 0 || buy_now_price > MAX_PRICE) {
        send_message(client->socket_fd, "ERROR Invalid price\n");
        return;
    }

    if (buy_now_price <= start_price) {
        send_message(client->socket_fd,
                     "ERROR Buy-now price must be greater than start price\n");
        return;
    }

    if (count_room_items(room_id) >= MAX_ITEMS_PER_ROOM) {
        send_message(client->socket_fd,
                     "ERROR Item limit reached (maximum 20 items per room)\n");
        return;
    }

    int slot = -1;
    for (int i = 0; i < MAX_ITEMS; i++) {
        if (!items[i].is_active) {
            slot = i;
            break;
        }
    }

    if (slot < 0) {
        send_message(client->socket_fd, "ERROR Item database is full\n");
        return;
    }

    AuctionItem *item = &items[slot];
    item->item_id = next_item_id++;
    item->room_id = room_id;
    snprintf(item->name, sizeof(item->name), "%s", name);
    item->start_price = start_price;
    item->buy_now_price = buy_now_price;
    item->current_price = start_price;
    item->highest_bidder = -1;
    item->next_call_ms = 0;
    item->calls_sent = 0;
    item->status = ITEM_PENDING;
    item->is_active = 1;

    log_event("ITEM_ADDED id=%d room_id=%d name=%s owner=%s start=%lld buy_now=%lld",
              item->item_id, room_id, item->name,
              users[client->user_index].username,
              item->start_price, item->buy_now_price);

    char response[128];
    snprintf(response, sizeof(response), "OK ITEM_ADDED ID: %d\n",
             item->item_id);
    send_message(client->socket_fd, response);
}

void list_items(int client_index, int room_id) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    if (find_room_by_id(room_id) < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    int item_count = 0;
    int last_id = 0;
    int index;

    send_message(client->socket_fd, "OK ITEM_LIST\n");

    while ((index = find_next_item(room_id, last_id)) >= 0) {
        char response[256];
        snprintf(response, sizeof(response),
                 "ITEM %d %s START %lld BUYNOW %lld STATUS %s\n",
                 items[index].item_id,
                 items[index].name,
                 items[index].start_price,
                 items[index].buy_now_price,
                 item_status_name(items[index].status));
        if (send_message(client->socket_fd, response) < 0) {
            return;
        }
        last_id = items[index].item_id;
        item_count++;
    }

    if (item_count == 0) {
        send_message(client->socket_fd, "NO_ITEMS\n");
    }

    send_message(client->socket_fd, "END_ITEM_LIST\n");
}

void remove_item(int client_index, int item_id) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    int item_index = find_item_by_id(item_id);
    if (item_index < 0) {
        send_message(client->socket_fd, "ERROR Item not found\n");
        return;
    }

    int room_index = find_room_by_id(items[item_index].room_id);
    if (room_index < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    if (!is_room_owner(client->user_index, room_index)) {
        send_message(client->socket_fd, "ERROR Not room owner\n");
        return;
    }

    if (items[item_index].status != ITEM_PENDING) {
        send_message(client->socket_fd,
                     "ERROR Item already put up for auction\n");
        return;
    }

    log_event("ITEM_REMOVED id=%d room_id=%d name=%s owner=%s",
              items[item_index].item_id, items[item_index].room_id,
              items[item_index].name, users[client->user_index].username);

    memset(&items[item_index], 0, sizeof(items[item_index]));

    char response[128];
    snprintf(response, sizeof(response), "OK ITEM_REMOVED ID: %d\n", item_id);
    send_message(client->socket_fd, response);
}

void start_auction(int client_index, int room_id) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    int room_index = find_room_by_id(room_id);
    if (room_index < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    if (!is_room_owner(client->user_index, room_index)) {
        send_message(client->socket_fd, "ERROR Not room owner\n");
        return;
    }

    if (rooms[room_index].current_item_id != 0) {
        send_message(client->socket_fd, "ERROR Auction already running\n");
        return;
    }

    int item_index = find_first_pending_item(room_id);
    if (item_index < 0) {
        send_message(client->socket_fd, "ERROR No pending items\n");
        return;
    }

    begin_item(room_index, item_index);

    char info[192];
    char message[256];
    describe_item(&items[item_index], info, sizeof(info));

    snprintf(message, sizeof(message), "OK AUCTION_STARTED %s\n", info);
    send_message(client->socket_fd, message);

    snprintf(message, sizeof(message), "EVENT ITEM_STARTED %s\n", info);
    broadcast_to_room(room_id, message, client_index);
}

void next_item(int client_index, int room_id) {
    Client *client = &clients[client_index];

    if (client->user_index < 0) {
        send_message(client->socket_fd, "ERROR Not logged in\n");
        return;
    }

    int room_index = find_room_by_id(room_id);
    if (room_index < 0) {
        send_message(client->socket_fd, "ERROR Room not found\n");
        return;
    }

    if (!is_room_owner(client->user_index, room_index)) {
        send_message(client->socket_fd, "ERROR Not room owner\n");
        return;
    }

    int current_index = -1;
    if (rooms[room_index].current_item_id != 0) {
        current_index = find_item_by_id(rooms[room_index].current_item_id);
    }

    if (current_index < 0) {
        rooms[room_index].current_item_id = 0;
        send_message(client->socket_fd, "ERROR No item is being auctioned\n");
        return;
    }

    AuctionItem *current = &items[current_index];
    if (current->status == ITEM_AUCTIONING && current->highest_bidder >= 0) {
        send_message(client->socket_fd, "ERROR Cannot skip item with bids\n");
        return;
    }

    char message[256];
    rooms[room_index].current_item_id = 0;
    snprintf(message, sizeof(message), "OK ITEM_ENDED %d %s\n",
             current->item_id, current->name);
    send_message(client->socket_fd, message);

    /* Vat pham da ban da duoc cong bo, khong phat lai ket qua. */
    if (current->status != ITEM_ENDED) {
        current->status = ITEM_ENDED;
        log_event("AUCTION_ITEM_ENDED room_id=%d item_id=%d name=%s result=NO_SALE",
                  room_id, current->item_id, current->name);
        snprintf(message, sizeof(message), "EVENT ITEM_ENDED %d %s NO_SALE\n",
                 current->item_id, current->name);
        broadcast_to_room(room_id, message, client_index);
    }

    int next_index = find_first_pending_item(room_id);
    if (next_index < 0) {
        log_event("AUCTION_FINISHED room_id=%d", room_id);
        send_message(client->socket_fd, "OK AUCTION_FINISHED\n");
        broadcast_to_room(room_id, "EVENT AUCTION_FINISHED\n", client_index);
        return;
    }

    begin_item(room_index, next_index);

    char info[192];
    describe_item(&items[next_index], info, sizeof(info));

    snprintf(message, sizeof(message), "OK ITEM_STARTED %s\n", info);
    send_message(client->socket_fd, message);

    snprintf(message, sizeof(message), "EVENT ITEM_STARTED %s\n", info);
    broadcast_to_room(room_id, message, client_index);
}

/* Ca dat gia va mua ngay deu yeu cau nguoi mua o trong phong cua vat pham. */
static AuctionItem *find_item_for_buyer(int client_index, int item_id,
                                       const char *owner_error, int *room_index_out) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;
    int item_index = find_item_by_id(item_id);
    if (item_index < 0) {
        send_message(socket_fd, "ERROR Item not found\n");
        return NULL;
    }
    AuctionItem *item = &items[item_index];
    int room_index = find_room_by_id(item->room_id);
    if (room_index < 0) {
        send_message(socket_fd, "ERROR Room not found\n");
        return NULL;
    }
    if (client->current_room_id != item->room_id) {
        send_message(socket_fd, "ERROR Not in item room\n");
        return NULL;
    }
    if (is_room_owner(client->user_index, room_index)) {
        send_message(socket_fd, owner_error);
        return NULL;
    }
    if (room_index_out != NULL) {
        *room_index_out = room_index;
    }
    return item;
}

static void complete_buy_now(int client_index, AuctionItem *item) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;
    /* Chot giao dich truoc khi gui phan hoi va huy cac lan goi gia con lai. */
    item->current_price = item->buy_now_price;
    item->highest_bidder = client->user_index;
    item->status = ITEM_ENDED;
    item->next_call_ms = 0;
    item->calls_sent = 0;
    const char *buyer = users[client->user_index].username;
    log_event("AUCTION_ITEM_ENDED room_id=%d item_id=%d name=%s result=SOLD buyer=%s price=%lld method=BUY_NOW",
              item->room_id, item->item_id, item->name, buyer, item->buy_now_price);

    char message[256];
    snprintf(message, sizeof(message), "OK BUY_NOW %d PRICE %lld\n",
             item->item_id, item->buy_now_price);
    send_message(socket_fd, message);
    snprintf(message, sizeof(message), "EVENT ITEM_SOLD %d %s bought it now for %lld VND.\n",
             item->item_id, buyer, item->buy_now_price);
    broadcast_to_room(item->room_id, message, client_index);
}

/* Server kiem tra gia va cap nhat trang thai trong cung vong lap select(). */
void place_bid(int client_index, int item_id, long long price) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;

    if (client->user_index < 0) {
        send_message(socket_fd, "ERROR Not logged in\n");
        return;
    }
    if (price <= 0 || price > MAX_PRICE) {
        send_message(socket_fd, "ERROR Invalid price\n");
        return;
    }
    int room_index;
    AuctionItem *item = find_item_for_buyer(client_index, item_id,
                                           "ERROR Cannot bid on own item\n", &room_index);
    if (item == NULL) {
        return;
    }
    if (item->status != ITEM_AUCTIONING ||
        rooms[room_index].current_item_id != item_id) {
        send_message(socket_fd, "ERROR Item is not being auctioned\n");
        return;
    }

    /* Dung gia mua ngay thi chot luon, khong ap dung buoc gia BID. */
    if (price == item->buy_now_price) {
        complete_buy_now(client_index, item);
        return;
    }

    /* Gia duoc gioi han boi MAX_PRICE nen phep cong khong tran long long. */
    long long minimum = item->current_price + MIN_BID_INCREMENT;
    if (price < minimum) {
        char response[128];
        snprintf(response, sizeof(response), "ERROR Bid must be at least %lld\n", minimum);
        send_message(socket_fd, response);
        return;
    }

    long long now = monotonic_ms();
    if (now < 0) {
        send_message(socket_fd, "ERROR Auction clock unavailable\n");
        return;
    }

    item->next_call_ms = now + BID_IDLE_MS;
    item->calls_sent = 0;
    item->current_price = price;
    item->highest_bidder = client->user_index;
    log_event("BID_ACCEPTED item_id=%d room_id=%d username=%s price=%lld",
              item_id, item->room_id, users[client->user_index].username, price);

    char response[128];
    snprintf(response, sizeof(response), "OK BID_ACCEPTED %d PRICE %lld\n", item_id, price);
    send_message(socket_fd, response);

    /* Gia da duoc cap nhat; cac thanh vien khac nhan cung mot su kien. */
    char event[192];
    snprintf(event, sizeof(event), "EVENT BID_PLACED %d BIDDER %s PRICE %lld\n",
             item_id, users[client->user_index].username, item->current_price);
    broadcast_to_room(item->room_id, event, client_index);
}

void buy_now(int client_index, int item_id) {
    Client *client = &clients[client_index];
    int socket_fd = client->socket_fd;
    if (client->user_index < 0) {
        send_message(socket_fd, "ERROR Not logged in\n");
        return;
    }
    AuctionItem *item = find_item_for_buyer(client_index, item_id,
                                           "ERROR Cannot buy own item\n", NULL);
    if (item == NULL) {
        return;
    }
    if (item->status == ITEM_ENDED) {
        send_message(socket_fd, "ERROR Item is no longer available\n");
        return;
    }

    complete_buy_now(client_index, item);
}

long long process_auction_timers(void) {
    static const char *const calls[] = {"Going once", "Going twice", "Going three times"};
    long long now = monotonic_ms();
    if (now < 0) {
        return 1000;
    }
    long long next_deadline = -1;

    for (int i = 0; i < MAX_ITEMS; i++) {
        AuctionItem *item = &items[i];
        if (item->status != ITEM_AUCTIONING || item->next_call_ms == 0) {
            continue;
        }
        if (item->next_call_ms <= now) {
            char message[256];
            int call = item->calls_sent++;
            snprintf(message, sizeof(message), "EVENT AUCTION_CALL %d %lld VND, %s (%d/3).\n",
                     item->item_id, item->current_price, calls[call], call + 1);
            if (item->calls_sent == 3) {
                /* Giu current_item_id de cho chu phong dung NEXT_ITEM. */
                item->status = ITEM_ENDED;
                item->next_call_ms = 0;
                broadcast_to_room(item->room_id, message, -1);

                const char *winner = users[item->highest_bidder].username;
                snprintf(message, sizeof(message),
                         "EVENT ITEM_SOLD %d %s won the auction for %lld VND.\n",
                         item->item_id, winner, item->current_price);
                broadcast_to_room(item->room_id, message, -1);
                log_event("AUCTION_ITEM_ENDED room_id=%d item_id=%d name=%s result=SOLD winner=%s price=%lld",
                          item->room_id, item->item_id, item->name, winner, item->current_price);
                continue;
            }
            broadcast_to_room(item->room_id, message, -1);
            long long sent_at = monotonic_ms();
            item->next_call_ms = (sent_at < 0 ? now : sent_at) + BID_CALL_INTERVAL_MS;
        }
        if (next_deadline < 0 || item->next_call_ms < next_deadline) {
            next_deadline = item->next_call_ms;
        }
    }
    if (next_deadline < 0) {
        return -1;
    }
    long long current_ms = monotonic_ms();
    if (current_ms < 0) {
        current_ms = now;
    }
    return next_deadline > current_ms ? next_deadline - current_ms : 0;
}
