#include <stdio.h>
#include <string.h>
#include "common.h"
#include "item.h"
#include "room.h"
#include "logger.h"

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
