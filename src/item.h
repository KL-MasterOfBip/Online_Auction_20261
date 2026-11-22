#ifndef ITEM_H
#define ITEM_H

#include "common.h"

int find_item_by_id(int item_id);
const char *item_status_name(ItemStatus status);
int count_room_items(int room_id);
void add_item(int client_index,
              int room_id,
              const char *name,
              long long start_price,
              long long buy_now_price);
void list_items(int client_index, int room_id);
void remove_item(int client_index, int item_id);
void start_auction(int client_index, int room_id);
void next_item(int client_index, int room_id);
void place_bid(int client_index, int item_id, long long price);
void buy_now(int client_index, int item_id);

/* Xu ly cac moc den han va tra ve so ms toi moc ke tiep (-1 neu khong co). */
long long process_auction_timers(void);

#endif
